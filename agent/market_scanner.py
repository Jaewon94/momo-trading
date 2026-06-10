"""시장 스캔 + 종목 선별 통합 — MCP 데이터 병렬 수집 → AI 한 번에 분석+선별"""
import asyncio
from datetime import timedelta

from loguru import logger
from sqlalchemy import and_, select

from analysis.feedback.performance_tracker import PerformanceTracker
from analysis.llm.llm_factory import llm_factory
from analysis.llm.prompts.market_scan import MARKET_SCAN_PROMPT, MARKET_SCAN_SYSTEM
from core.config import settings
from core.database import AsyncSessionLocal
from models.decision_event import DecisionEvent
from services.activity_logger import activity_logger
from services.candidate_scoring_service import candidate_scoring_service
from services.decision_event_service import decision_event_service
from services.news_signal_service import news_signal_service
from strategy.horizon_scan_policy import horizon_scan_profile, normalize_scan_horizon
from strategy.news_intelligence_policy import news_horizon_policy
from strategy.trade_horizon import TradeHorizon
from trading.adapters.base import BrokerAdapter
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType

# 모의투자 매매불가 종목 필터 키워드
_EXCLUDE_NAME_KEYWORDS = ("ETN", "스팩", "SPAC")
_MID_LONG_PREFERRED_MAX_CHANGE_PCT = 12.0
_POLICY_FALLBACK_BUY_TARGET = 3


class MarketScanner:
    """
    MCP를 통해 시장 데이터 수집 → AI가 시장 국면 판단 + 최종 종목 선별을 한 번에 수행.
    (기존 scan → screening 2단계를 1단계로 통합하여 LLM 호출 1건 절약)
    """

    def __init__(self, broker_adapter: BrokerAdapter | None = None):
        self._broker_adapter = broker_adapter or get_broker_adapter()
        self._untradeable_symbols: set[str] = set()

    def add_untradeable(self, symbol: str) -> None:
        """매매불가 종목을 런타임 블록리스트에 등록 (당일 스캔에서 제외)"""
        self._untradeable_symbols.add(symbol)
        logger.debug("매매불가 블록리스트 등록: {} (총 {}건)", symbol, len(self._untradeable_symbols))

    def _filter_untradeable(self, stocks: list[dict]) -> list[dict]:
        """매매불가 종목 필터링 (런타임 블록리스트 + 이름 키워드)"""
        filtered = []
        for s in stocks:
            name = s.get("name", "")
            symbol = s.get("symbol", "")
            if symbol in self._untradeable_symbols:
                continue
            if any(kw in name for kw in _EXCLUDE_NAME_KEYWORDS):
                continue
            filtered.append(s)
        if len(filtered) < len(stocks):
            logger.debug("매매불가 종목 필터: {}건 → {}건", len(stocks), len(filtered))
        return filtered

    def _build_price_lookup(self, *data_lists: list[dict]) -> dict[str, float]:
        """스캔 데이터에서 종목코드→현재가 매핑"""
        lookup: dict[str, float] = {}
        for data in data_lists:
            for item in data:
                sym = item.get("symbol", item.get("code", ""))
                if not sym:
                    continue
                raw = item.get("price", item.get("current_price", 0))
                try:
                    price = float(str(raw).replace(",", ""))
                    if price > 0:
                        lookup[sym] = price
                except (ValueError, TypeError):
                    continue
        return lookup

    def _build_market_data_lookup(
        self,
        scored_candidates: list[dict],
        *,
        volume_rank: list[dict] | None = None,
        surge_data: list[dict] | None = None,
        drop_data: list[dict] | None = None,
    ) -> dict[str, dict]:
        """LLM 선정 결과에 스캔 원천 수치를 다시 붙이기 위한 매핑."""
        lookup: dict[str, dict] = {}
        raw_sources = (
            ("volume_rank", volume_rank or []),
            ("surge_data", surge_data or []),
            ("drop_data", drop_data or []),
        )
        for source_name, data in raw_sources:
            for item in data:
                symbol = str(item.get("symbol", item.get("code", "")) or "").strip()
                if not symbol:
                    continue
                entry = lookup.setdefault(symbol, {"scanner_sources": []})
                entry.setdefault("price", item.get("price", item.get("current_price")))
                entry.setdefault("change_rate", item.get("change_rate"))
                entry.setdefault("volume", item.get("volume"))
                if source_name not in entry["scanner_sources"]:
                    entry["scanner_sources"].append(source_name)

        for item in scored_candidates:
            symbol = str(item.get("symbol", "") or "").strip()
            if not symbol:
                continue
            sources = list(lookup.get(symbol, {}).get("scanner_sources") or [])
            for source in item.get("sources") or []:
                if source not in sources:
                    sources.append(source)
            lookup[symbol] = {
                "price": item.get("price"),
                "change_rate": item.get("change_rate"),
                "volume": item.get("volume"),
                "scanner_score": item.get("score"),
                "scanner_sources": sources,
                "scanner_reason_codes": item.get("reason_codes"),
                "news_negative_pressure": item.get("news_negative_pressure"),
            }
        return lookup

    def _build_realtime_monitor_candidates(
        self,
        selected: list[dict],
        scored_candidates: list[dict],
        *,
        volume_rank: list[dict] | None = None,
        surge_data: list[dict] | None = None,
        max_candidates: int = 30,
    ) -> list[dict]:
        """분석 대상은 유지하면서 실시간 감시 범위만 넓히기 위한 후보 목록."""
        candidates: list[dict] = []
        seen: set[str] = set()

        def add(item: dict, source: str) -> None:
            symbol = str(item.get("symbol", item.get("code", "")) or "").strip()
            if not symbol or symbol in seen or len(candidates) >= max_candidates:
                return
            seen.add(symbol)
            candidate = dict(item)
            candidate["symbol"] = symbol
            candidate.setdefault("market", "KRX")
            candidate.setdefault("name", item.get("name", symbol))
            candidate.setdefault("price", item.get("price", item.get("current_price")))
            candidate.setdefault("change_rate", item.get("change_rate"))
            candidate.setdefault("volume", item.get("volume"))
            candidate.setdefault("scanner_monitor_source", source)
            candidates.append(candidate)

        for item in selected:
            add(item, "selected")
        for item in scored_candidates:
            add(item, "scored_candidates")
        for item in (volume_rank or [])[:15]:
            add(item, "volume_rank")
        for item in (surge_data or [])[:15]:
            add(item, "surge_data")

        return candidates

    async def scan(
        self,
        cycle_id: str | None = None,
        dynamic_limits: dict | None = None,
        *,
        horizon: str | None = None,
    ) -> dict:
        """시장 스캔 + 종목 선별 통합 실행"""
        scan_horizon = normalize_scan_horizon(horizon)
        scan_profile = horizon_scan_profile(scan_horizon)
        logger.debug("시장 스캔 시작 ({})", scan_profile.label)
        timer = activity_logger.timer()

        await activity_logger.log(
            ActivityType.SCAN, ActivityPhase.START,
            f"\U0001f4e1 {scan_horizon} 시장 스캔 중... 거래량/등락 상위 종목 조회",
            cycle_id=cycle_id,
        )

        # 1. 데이터 수집 병렬화 (시장 랭킹 3건 + DB 1건 + 계좌 2건)
        (
            balance,
            holdings,
            volume_rank,
            surge_data,
            drop_data,
            performance_summary,
        ) = await asyncio.gather(
            self._broker_adapter.get_balance(),
            self._broker_adapter.get_holdings(),
            self._get_volume_rank(),
            self._get_fluctuation_rank("top"),
            self._get_fluctuation_rank("bottom"),
            self._get_performance_summary(),
        )
        available_cash = balance.cash
        total_asset = balance.total_asset or available_cash
        max_pos_pct = 0.2
        if dynamic_limits:
            max_pos_pct = dynamic_limits.get("max_position_pct", 20.0) / 100
        max_per_stock = available_cash * max_pos_pct
        cooldown_symbols = await self._get_recent_candidate_cooldown_symbols()

        # 현금 비율 매우 낮으면 보유종목 매도 검토 힌트
        rotation_hint = ""
        if total_asset > 0 and available_cash < total_asset * 0.1 and len(holdings) > 0:
            rotation_hint = "⚠️ 현금 비율 매우 낮음 — 보유종목 중 정체/부진 종목 매도 검토 필요"

        data_elapsed = activity_logger.elapsed_ms(timer)
        logger.debug("MCP 데이터 수집 완료: {}ms", data_elapsed)
        scanner_policy = await self._build_scanner_policy(scan_horizon)
        max_candidates = scan_profile.max_candidates

        scored_candidates = candidate_scoring_service.score_candidates(
            volume_rank=volume_rank,
            surge_data=surge_data,
            drop_data=drop_data,
            holdings=holdings,
            available_cash=available_cash,
            max_candidates=max_candidates,
            cooldown_symbols=cooldown_symbols,
            risk_appetite=getattr(settings, "RISK_APPETITE", "MODERATE"),
            aggressive_min_change_pct=getattr(settings, "SCANNER_AGGRESSIVE_MIN_CHANGE_PCT", 3.0),
            aggressive_max_change_pct=getattr(settings, "SCANNER_AGGRESSIVE_MAX_CHANGE_PCT", 18.0),
            aggressive_min_score=getattr(settings, "SCANNER_AGGRESSIVE_MIN_SCORE", 45.0),
            preferred_change_min_pct=scanner_policy.get("preferred_change_min_pct"),
            preferred_change_max_pct=scanner_policy.get("preferred_change_max_pct"),
            horizon=scan_horizon,
        )
        news_pressure_by_symbol = await self._get_candidate_news_pressures(
            scored_candidates,
            horizon=scan_horizon,
        )
        if news_pressure_by_symbol:
            scored_candidates = candidate_scoring_service.score_candidates(
                volume_rank=volume_rank,
                surge_data=surge_data,
                drop_data=drop_data,
                holdings=holdings,
                available_cash=available_cash,
                max_candidates=max_candidates,
                cooldown_symbols=cooldown_symbols,
                news_pressure_by_symbol=news_pressure_by_symbol,
                risk_appetite=getattr(settings, "RISK_APPETITE", "MODERATE"),
                aggressive_min_change_pct=getattr(settings, "SCANNER_AGGRESSIVE_MIN_CHANGE_PCT", 3.0),
                aggressive_max_change_pct=getattr(settings, "SCANNER_AGGRESSIVE_MAX_CHANGE_PCT", 18.0),
                aggressive_min_score=getattr(settings, "SCANNER_AGGRESSIVE_MIN_SCORE", 45.0),
                preferred_change_min_pct=scanner_policy.get("preferred_change_min_pct"),
                preferred_change_max_pct=scanner_policy.get("preferred_change_max_pct"),
                horizon=scan_horizon,
            )
        await self._record_scored_candidate_events(
            cycle_id=cycle_id,
            scored_candidates=scored_candidates,
            available_cash=available_cash,
            horizon=scan_horizon,
        )

        # 2. AI 시장 분석 + 종목 선별 (통합 1회 호출)
        from util.time_util import now_kst

        now = now_kst()
        cutoff_time = now.replace(
            hour=settings.BUY_CUTOFF_HOUR,
            minute=settings.BUY_CUTOFF_MINUTE,
            second=0, microsecond=0,
        )
        minutes_until_cutoff = max(0, int((cutoff_time - now).total_seconds() / 60))

        prompt = MARKET_SCAN_PROMPT.format(
            current_time=now.strftime("%H:%M"),
            minutes_until_cutoff=minutes_until_cutoff,
            total_asset=total_asset,
            available_cash=available_cash,
            max_per_stock=max_per_stock,
            rotation_hint=rotation_hint,
            volume_rank_data=self._format_data(volume_rank),
            surge_data=self._format_data(surge_data),
            drop_data=self._format_data(drop_data),
            holdings_data=self._format_holdings(holdings),
            holding_count=len(holdings),
            performance_summary=performance_summary,
            scanner_policy=self._format_scanner_policy(scanner_policy),
            scored_candidates=self._format_scored_candidates(scored_candidates),
            scan_horizon=scan_horizon,
            scan_horizon_label=scan_profile.label,
            horizon_focus=scan_profile.prompt_focus,
            max_selected=scan_profile.max_selected,
        )

        try:
            result_text, provider = await llm_factory.generate_tier1(
                prompt, system_prompt=MARKET_SCAN_SYSTEM
            )
            parsed = self._parse_json_response(result_text)
            selected = parsed.get("selected", [])
            elapsed = activity_logger.elapsed_ms(timer)

            # 가격 기반 사전 필터: 1주 매수 불가능한 종목 제거
            if available_cash > 0 and selected:
                price_lookup = self._build_price_lookup(volume_rank, surge_data, drop_data)
                before = len(selected)
                selected = [
                    s for s in selected
                    if str(s.get("direction") or "BUY").upper() != "BUY"
                    or price_lookup.get(s.get("symbol", ""), 0) <= 0
                    or price_lookup[s["symbol"]] <= available_cash
                ]
                if len(selected) < before:
                    logger.debug("현금 필터: {}건 → {}건 (가용 {:,.0f}원)", before, len(selected), available_cash)

            market_data_lookup = self._build_market_data_lookup(
                scored_candidates,
                volume_rank=volume_rank,
                surge_data=surge_data,
                drop_data=drop_data,
            )
            for item in selected:
                symbol = str(item.get("symbol", "") or "").strip()
                item.setdefault("target_horizon_hint", scan_horizon)
                item.setdefault("scan_horizon", scan_horizon)
                market_data = market_data_lookup.get(symbol)
                if not market_data:
                    continue
                for key, value in market_data.items():
                    item.setdefault(key, value)

            selected, policy_adjustments = self._apply_selection_policy(
                selected,
                scored_candidates,
                scanner_policy=scanner_policy,
            )
            selected, fallback_adjustments = self._fill_policy_candidates(
                selected,
                scored_candidates,
                scanner_policy=scanner_policy,
            )
            policy_adjustments.extend(fallback_adjustments)

            monitor_candidates = self._build_realtime_monitor_candidates(
                selected,
                scored_candidates,
                volume_rank=volume_rank,
                surge_data=surge_data,
                max_candidates=min(max(scan_profile.max_candidates, 30), 60),
            )

            logger.info(
                "시장 스캔+선별 완료 ({}): {}개 선정 (데이터 {}ms + AI {}ms)",
                provider, len(selected), data_elapsed, elapsed - data_elapsed,
            )

            # 활동 로그 요약
            selected_lines = []
            for s in selected[:8]:
                name = s.get("name", s.get("symbol", "?"))
                strategy = s.get("strategy_type", "")
                reason = s.get("reason", "")
                line = f"  {name} [{strategy}]"
                if reason:
                    line += f" — {reason}"
                selected_lines.append(line)

            summary_text = f"\U0001f4e1 시장 스캔 완료: {len(selected)}개 선정"
            if selected_lines:
                summary_text += "\n" + "\n".join(selected_lines)
            market_analysis = parsed.get("market_analysis", "")
            if market_analysis:
                summary_text += f"\n   시장: {market_analysis}"

            await activity_logger.log(
                ActivityType.SCAN, ActivityPhase.COMPLETE,
                summary_text,
                cycle_id=cycle_id,
                detail={
                    "selected_count": len(selected),
                    "scan_horizon": scan_horizon,
                    "scan_horizon_label": scan_profile.label,
                    "selected": selected,
                    "monitor_candidates": monitor_candidates,
                    "scored_candidates": scored_candidates,
                    "cooldown_symbols": sorted(cooldown_symbols),
                    "news_pressure_by_symbol": news_pressure_by_symbol,
                    "scanner_policy": scanner_policy,
                    "selection_policy_adjustments": policy_adjustments,
                    "market_regime": parsed.get("market_regime", ""),
                    "market_analysis": market_analysis,
                    "available_cash": available_cash,
                },
                llm_provider=provider,
                llm_tier="TIER1",
                execution_time_ms=elapsed,
            )

            return {
                "selected": selected,
                "scan_horizon": scan_horizon,
                "scan_horizon_label": scan_profile.label,
                "monitor_candidates": monitor_candidates,
                "market_summary": parsed.get("market_analysis", ""),
                "market_regime": parsed.get("market_regime", ""),
                "market_analysis": parsed.get("market_analysis", ""),
                "leading_sectors": parsed.get("leading_sectors", []),
                "scored_candidates": scored_candidates,
                "scanner_policy": scanner_policy,
                "selection_policy_adjustments": policy_adjustments,
                "available_cash": available_cash,
                "max_per_stock": max_per_stock,
                "provider": provider,
            }
        except Exception as e:
            elapsed = activity_logger.elapsed_ms(timer)
            err_msg = str(e) or repr(e)
            logger.error("시장 스캔 AI 분석 실패 ({}): {}", type(e).__name__, err_msg)
            await activity_logger.log(
                ActivityType.SCAN, ActivityPhase.ERROR,
                f"\u274c 시장 스캔 실패: [{type(e).__name__}] {err_msg[:100]}",
                cycle_id=cycle_id,
                error_message=err_msg,
                execution_time_ms=elapsed,
            )
            return {"selected": [], "market_summary": "스캔 실패", "available_cash": available_cash}

    async def _build_scanner_policy(self, horizon: str | None = None) -> dict:
        """현재 손실 복구/호라이즌 운용 방향을 스캐너 후보 정책으로 변환한다."""
        scan_horizon = normalize_scan_horizon(horizon)
        scan_profile = horizon_scan_profile(scan_horizon)
        consecutive_losses = await self._get_consecutive_losses()
        max_losses = int(getattr(settings, "MAX_CONSECUTIVE_LOSSES", 0) or 0)
        recovery_mode = str(
            getattr(settings, "LOSS_STREAK_RECOVERY_MODE", "BLOCK_BUY") or "BLOCK_BUY"
        ).upper()
        probation_active = (
            recovery_mode == "PROBATION"
            and max_losses > 0
            and consecutive_losses >= max_losses
        )

        probation_min = self._to_float(getattr(settings, "LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT", 0.0))
        probation_max = self._to_float(getattr(settings, "LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT", 0.0))
        preferred_min = probation_min if probation_active and probation_min > 0 else None
        preferred_max = (
            probation_max
            if probation_active and probation_max > 0
            else scan_profile.preferred_change_max_pct
        )
        if not probation_active:
            preferred_min = scan_profile.preferred_change_min_pct

        return {
            "scan_horizon": scan_horizon,
            "scan_horizon_label": scan_profile.label,
            "horizon_focus": scan_profile.prompt_focus,
            "max_candidates": scan_profile.max_candidates,
            "max_selected": scan_profile.max_selected,
            "news_pressure_candidates": scan_profile.news_pressure_candidates,
            "news_lookback_hours": scan_profile.news_lookback_hours,
            "mid_long_bias": scan_horizon in {TradeHorizon.MID, TradeHorizon.LONG},
            "recovery_mode": recovery_mode,
            "probation_active": probation_active,
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": max_losses,
            "preferred_change_min_pct": preferred_min,
            "preferred_change_max_pct": preferred_max,
            "probation_min_change_pct": probation_min,
            "probation_max_change_pct": probation_max,
        }

    async def _get_consecutive_losses(self) -> int:
        try:
            async with AsyncSessionLocal() as session:
                tracker = PerformanceTracker(session)
                return await tracker.get_consecutive_losses()
        except Exception as exc:
            logger.debug("연속 손실 조회 실패: {}", str(exc))
            return 0

    def _apply_selection_policy(
        self,
        selected: list[dict],
        scored_candidates: list[dict],
        *,
        scanner_policy: dict,
    ) -> tuple[list[dict], list[dict]]:
        """LLM 선정 결과를 deterministic scanner policy에 맞춘다."""
        scored_by_symbol = {
            str(item.get("symbol") or "").strip(): item
            for item in scored_candidates
            if str(item.get("symbol") or "").strip()
        }
        preferred_min = scanner_policy.get("preferred_change_min_pct")
        preferred_max = scanner_policy.get("preferred_change_max_pct")
        probation_active = bool(scanner_policy.get("probation_active"))
        filtered: list[dict] = []
        adjustments: list[dict] = []
        seen: set[str] = set()

        for raw in selected:
            item = dict(raw)
            symbol = str(item.get("symbol") or "").strip()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            direction = str(item.get("direction") or "BUY").upper()
            item["direction"] = direction
            scored = scored_by_symbol.get(symbol) or {}

            if direction == "BUY" and scored:
                hinted_strategy = str(scored.get("strategy_type_hint") or "").strip()
                if hinted_strategy:
                    original_strategy = str(item.get("strategy_type") or "").strip()
                    if original_strategy != hinted_strategy:
                        item["strategy_type"] = hinted_strategy
                        item["strategy_alignment"] = "DETERMINISTIC_HINT"
                        adjustments.append(
                            {
                                "symbol": symbol,
                                "action": "strategy_aligned",
                                "from": original_strategy,
                                "to": hinted_strategy,
                            }
                        )
                item.setdefault("policy_buy_eligible", scored.get("policy_buy_eligible"))
                if scored.get("policy_buy_eligible") is False or scored.get("buyable") is False:
                    adjustments.append(
                        {
                            "symbol": symbol,
                            "action": "buy_filtered",
                            "reason": "SCANNER_POLICY_INELIGIBLE",
                            "reason_codes": scored.get("reason_codes", []),
                            "scanner_score": scored.get("score"),
                        }
                    )
                    continue

            if direction == "BUY" and probation_active:
                change_rate = self._candidate_change_rate(item, scored)
                if preferred_min is not None and change_rate < float(preferred_min):
                    adjustments.append(
                        {
                            "symbol": symbol,
                            "action": "buy_filtered",
                            "reason": "PROBATION_CHANGE_BELOW_MIN",
                            "change_rate": change_rate,
                            "min_change_pct": preferred_min,
                        }
                    )
                    continue
                if preferred_max is not None and change_rate > float(preferred_max):
                    adjustments.append(
                        {
                            "symbol": symbol,
                            "action": "buy_filtered",
                            "reason": "PROBATION_CHANGE_OVER_MAX",
                            "change_rate": change_rate,
                            "max_change_pct": preferred_max,
                        }
                    )
                    continue
                item["policy_buy_eligible"] = True

            filtered.append(item)

        return filtered, adjustments

    def _fill_policy_candidates(
        self,
        selected: list[dict],
        scored_candidates: list[dict],
        *,
        scanner_policy: dict,
    ) -> tuple[list[dict], list[dict]]:
        """PROBATION 중 LLM 선정이 모두 과열로 탈락하면 정책 적합 후보를 분석 대상으로 보강한다."""
        if not bool(scanner_policy.get("probation_active")):
            return selected, []

        selected_items = list(selected)
        selected_symbols = {
            str(item.get("symbol") or "").strip()
            for item in selected_items
            if str(item.get("symbol") or "").strip()
        }
        buy_count = sum(
            1
            for item in selected_items
            if str(item.get("direction") or "BUY").upper() == "BUY"
        )
        adjustments: list[dict] = []
        preferred_min = scanner_policy.get("preferred_change_min_pct")
        preferred_max = scanner_policy.get("preferred_change_max_pct")

        for scored in scored_candidates:
            if buy_count >= _POLICY_FALLBACK_BUY_TARGET:
                break
            symbol = str(scored.get("symbol") or "").strip()
            if not symbol or symbol in selected_symbols:
                continue
            if scored.get("hold_candidate") or not scored.get("buyable", True):
                continue
            if scored.get("policy_buy_eligible") is False:
                continue
            change_rate = self._candidate_change_rate(scored, scored)
            if preferred_min is not None and change_rate < float(preferred_min):
                continue
            if preferred_max is not None and change_rate > float(preferred_max):
                continue

            selected_symbols.add(symbol)
            buy_count += 1
            selected_items.append(
                {
                    "symbol": symbol,
                    "name": scored.get("name", symbol),
                    "strategy_type": scored.get("strategy_type_hint") or "STABLE_SHORT",
                    "reason": "정책 적합 deterministic 후보 보강",
                    "direction": "BUY",
                    "price": scored.get("price"),
                    "change_rate": scored.get("change_rate"),
                    "volume": scored.get("volume"),
                    "scanner_score": scored.get("score"),
                    "scanner_sources": scored.get("sources", []),
                    "scanner_reason_codes": scored.get("reason_codes", []),
                    "target_horizon_hint": scanner_policy.get("scan_horizon") or TradeHorizon.SHORT,
                    "scan_horizon": scanner_policy.get("scan_horizon") or TradeHorizon.SHORT,
                    "news_negative_pressure": scored.get("news_negative_pressure"),
                    "policy_buy_eligible": True,
                    "strategy_alignment": "DETERMINISTIC_FALLBACK",
                }
            )
            adjustments.append(
                {
                    "symbol": symbol,
                    "action": "buy_fallback_added",
                    "reason": "PROBATION_POLICY_ELIGIBLE",
                    "change_rate": change_rate,
                    "scanner_score": scored.get("score"),
                }
            )

        return selected_items, adjustments

    @staticmethod
    def _candidate_change_rate(item: dict, scored: dict | None = None) -> float:
        for source in (item, scored or {}):
            value = source.get("change_rate")
            try:
                return float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                continue
        return 0.0

    async def _get_performance_summary(self) -> str:
        """과거 매매 성과 요약 텍스트 생성"""
        try:
            async with AsyncSessionLocal() as session:
                tracker = PerformanceTracker(session)
                stats = await tracker.get_overall_stats()

            overall = stats.get("overall")
            if not overall or overall.total_trades == 0:
                return "매매 이력 없음"

            lines = [
                f"총 {overall.total_trades}거래, "
                f"승률 {overall.win_rate * 100:.1f}%, "
                f"총손익 {overall.total_pnl:+,.0f}원, "
                f"평균수익률 {overall.avg_return:+.2f}%"
            ]

            by_strategy = stats.get("by_strategy", {})
            for strategy_type, stat in by_strategy.items():
                lines.append(
                    f"  - {strategy_type}: {stat.total_trades}거래, "
                    f"승률 {stat.win_rate * 100:.1f}%, "
                    f"평균수익률 {stat.avg_return:+.2f}%"
                )

            return "\n".join(lines)
        except Exception as e:
            logger.warning("성과 요약 조회 실패: {}", str(e))
            return "매매 이력 없음"

    async def _get_recent_candidate_cooldown_symbols(self) -> set[str]:
        """최근 후보/분석 종목을 감점 대상으로 조회한다."""
        try:
            from util.time_util import now_kst

            start_at = now_kst() - timedelta(hours=6)
            stages = {
                "CANDIDATE_SCORING",
                "PRE_ANALYSIS_GATE",
                "DETERMINISTIC_FINAL_GATE",
                "TIER1_COST_GATE",
                "ORDER_GATE",
            }
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(DecisionEvent.symbol)
                    .where(and_(
                        DecisionEvent.created_at >= start_at,
                        DecisionEvent.decision_stage.in_(stages),
                    ))
                    .order_by(DecisionEvent.created_at.desc())
                    .limit(200)
                )
                return {
                    str(symbol).strip()
                    for symbol in result.scalars().all()
                    if str(symbol or "").strip()
                }
        except Exception as exc:
            logger.debug("최근 후보 cooldown 조회 실패: {}", str(exc))
            return set()

    async def _get_candidate_news_pressures(
        self,
        scored_candidates: list[dict],
        *,
        horizon: str | None = None,
    ) -> dict[str, float]:
        """후보 top-N에 대해서만 뉴스 부정 압력을 계산한다."""
        scan_horizon = normalize_scan_horizon(horizon)
        news_policy = news_horizon_policy(scan_horizon)
        if news_policy.pressure_candidates <= 0:
            return {}
        symbols = [
            str(item.get("symbol") or "").strip()
            for item in scored_candidates[:news_policy.pressure_candidates]
            if str(item.get("symbol") or "").strip()
        ]
        if not symbols:
            return {}

        pressures: dict[str, float] = {}
        try:
            async with AsyncSessionLocal() as session:
                for symbol in symbols:
                    result = await news_signal_service.evaluate_gate(
                        session,
                        symbol=symbol,
                        horizon=scan_horizon,
                    )
                    pressure = float(result.get("negative_pressure") or 0.0)
                    if pressure > 0:
                        pressures[symbol] = round(pressure, 4)
        except Exception as exc:
            logger.debug("후보 뉴스 압력 조회 실패: {}", str(exc))
            return {}
        return pressures

    async def _get_volume_rank(self) -> list[dict]:
        stocks = await self._broker_adapter.get_volume_rank()
        return self._filter_untradeable(stocks)

    async def _get_fluctuation_rank(self, sort: str) -> list[dict]:
        stocks = await self._broker_adapter.get_fluctuation_rank(sort=sort)
        return self._filter_untradeable(stocks)

    def _format_data(self, data: list[dict]) -> str:
        if not data:
            return "데이터 없음"
        lines = []
        for i, item in enumerate(data[:15], 1):
            symbol = item.get("symbol", item.get("code", ""))
            name = item.get("name", "")
            price = item.get("price", item.get("current_price", ""))
            change_rate = item.get("change_rate", "")
            volume = item.get("volume", "")
            lines.append(f"{i}. {name}({symbol}) {price}원 {change_rate}% 거래량:{volume}")
        return "\n".join(lines)

    def _format_holdings(self, holdings) -> str:
        if not holdings:
            return "보유 종목 없음"
        lines = []
        for h in holdings:
            lines.append(
                f"- {h.name}({h.symbol}) {h.quantity}주 "
                f"평균단가:{h.avg_buy_price:,.0f} 수익률:{h.pnl_rate:+.2f}%"
            )
        return "\n".join(lines)

    def _format_scanner_policy(self, policy: dict) -> str:
        scan_horizon = str(policy.get("scan_horizon") or "SHORT").upper()
        if scan_horizon == TradeHorizon.LONG:
            operating_direction = "운용 방향: 장기 후보는 급등 추격보다 구조적 추세, 장기 가격 위치, 뉴스/공시 논거를 우선"
        elif scan_horizon == TradeHorizon.MID:
            operating_direction = "운용 방향: 중기 후보는 눌림 후 회복, 거래량 지속, 며칠 이상 유지 가능한 뉴스/테마 논거를 우선"
        else:
            operating_direction = "운용 방향: 단기 후보는 장중 유동성, 거래량, 최근 뉴스 리스크, 명확한 손절/익절 계획을 우선"
        lines = [
            f"스캔 호라이즌: {scan_horizon} ({policy.get('scan_horizon_label', '')})",
            f"호라이즌 기준: {policy.get('horizon_focus', '')}",
            operating_direction,
            "전략 의미: STABLE_SHORT/AGGRESSIVE_SHORT는 legacy 실행·위험 프로파일이며 보유기간 자체가 아님",
            f"결정론 1차 후보 폭: 최대 {int(policy.get('max_candidates') or getattr(settings, 'SCANNER_MAX_CANDIDATES', 30) or 30)}개 점수화 후 LLM 선별",
            f"LLM 최종 선정 상한: 최대 {int(policy.get('max_selected') or 8)}개",
            f"뉴스 부정압력 검사: 상위 {int(policy.get('news_pressure_candidates') or 0)}개 / 최근 {int(policy.get('news_lookback_hours') or 0)}시간",
            f"선호 등락률 상한: +{float(policy.get('preferred_change_max_pct') or 0.0):.2f}%",
            "상품 정책: 인버스/레버리지/현금성/채권형 상품은 신규 BUY 제외, 방어형 ETF는 공격 성향에서 감점",
            "AGGRESSIVE_SHORT 사용: 상승 모멘텀+거래량 확인 후보 중 Deterministic strategy=AGGRESSIVE_SHORT인 경우만 허용",
        ]
        if policy.get("preferred_change_min_pct") is not None:
            lines.append(f"선호 등락률 하한: {float(policy.get('preferred_change_min_pct') or 0.0):+.2f}%")
        if bool(policy.get("probation_active")):
            min_change = policy.get("preferred_change_min_pct")
            max_change = policy.get("preferred_change_max_pct")
            lines.append(
                "현재 상태: 연속 손실 PROBATION 활성 "
                f"({policy.get('consecutive_losses')}회 >= {policy.get('max_consecutive_losses')}회)"
            )
            lines.append(
                f"BUY 후보 필수 조건: 전일대비 +{float(min_change or 0.0):.2f}%"
                f"~+{float(max_change or 0.0):.2f}% 범위만 선택"
            )
        else:
            lines.append(
                "현재 상태: PROBATION 비활성, 그래도 과열 급등 추격보다 중기·장기 후보 우선"
            )
        return "\n".join(f"- {line}" for line in lines)

    def _format_scored_candidates(self, candidates: list[dict]) -> str:
        if not candidates:
            return "후보 없음"
        lines = []
        for index, item in enumerate(candidates, 1):
            reasons = ", ".join(item.get("reasons", [])[:3])
            reason_codes = ",".join(item.get("reason_codes", [])[:5])
            lines.append(
                f"{index}. {item.get('name')}({item.get('symbol')}) "
                f"score={item.get('score')} price={item.get('price')} "
                f"chg={item.get('change_rate')}% buyable={item.get('buyable')} "
                f"policy_eligible={item.get('policy_buy_eligible')} "
                f"strategy={item.get('strategy_type_hint', '')} "
                f"sources={','.join(item.get('sources', []))} "
                f"codes={reason_codes} "
                f"reasons={reasons}"
            )
        return "\n".join(lines)

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0

    def _parse_json_response(self, text: str) -> dict:
        from core.json_utils import parse_llm_json
        return parse_llm_json(text)

    async def _record_scored_candidate_events(
        self,
        *,
        cycle_id: str | None,
        scored_candidates: list[dict],
        available_cash: float,
        horizon: str | None = None,
    ) -> None:
        """Deterministic scanner 후보군을 benchmark용 decision event로 남긴다."""
        for rank, item in enumerate(scored_candidates[:8], 1):
            try:
                buyable = bool(item.get("buyable", True))
                await decision_event_service.record_event(
                    cycle_id=cycle_id,
                    symbol=str(item.get("symbol") or ""),
                    stock_name=str(item.get("name") or item.get("symbol") or ""),
                    decision_stage="CANDIDATE_SCORING",
                    source="candidate_scoring",
                    scanner_score=item.get("score"),
                    risk_gate_result="PASS" if buyable else "NOT_BUYABLE",
                    final_action="CANDIDATE" if buyable else "SKIP",
                    reference_price=item.get("price"),
                    strategy_type=item.get("strategy_type_hint"),
                    provider="DETERMINISTIC",
                    model="candidate_scoring_v1",
                    reason=", ".join(str(reason) for reason in item.get("reasons", [])[:4]),
                    metadata={
                        "rank": rank,
                        "scan_horizon": normalize_scan_horizon(horizon),
                        "available_cash": available_cash,
                        "sources": item.get("sources", []),
                        "buyable": buyable,
                        "hold_candidate": bool(item.get("hold_candidate")),
                        "strategy_type_hint": item.get("strategy_type_hint"),
                        "reason_codes": item.get("reason_codes", []),
                        "news_negative_pressure": item.get("news_negative_pressure"),
                        "change_rate": item.get("change_rate"),
                        "volume": item.get("volume"),
                    },
                )
            except Exception as exc:
                logger.debug(
                    "candidate scoring decision event 기록 실패: {} {}",
                    item.get("symbol"),
                    str(exc),
                )


market_scanner = MarketScanner()
