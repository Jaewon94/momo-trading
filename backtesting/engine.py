"""과거 데이터 전략 시뮬레이션 엔진"""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from loguru import logger

from analysis.technical.indicators import TechnicalIndicators
from analysis.technical.patterns import ChartPatterns
from backtesting.fee_models import KoreaStockFeeModel
from backtesting.fill_models import LimitGuardFillModel, NextBarOHLCFillModel
from backtesting.metrics import BacktestMetrics, TradeRecord, calculate_metrics
from strategy.stable_short import StableShortStrategy
from strategy.aggressive_short import AggressiveShortStrategy
from trading.enums import SignalAction


@dataclass
class BacktestConfig:
    """백테스팅 설정"""
    strategy_type: str = "STABLE_SHORT"   # STABLE_SHORT / AGGRESSIVE_SHORT
    initial_capital: float = 10_000_000   # 초기 자본 (원)
    max_position_pct: float = 20.0        # 종목당 최대 비중 (%)
    commission_rate: float = 0.015        # 수수료율 (%)
    slippage_rate: float = 0.05           # 슬리피지 (%)
    sell_tax_rate: float = 0.0            # 매도 거래세율 (%)
    stop_loss_pct: float = -3.0           # 손절 (%)
    take_profit_pct: float = 5.0          # 익절 (%)
    max_hold_days: int = 5                # 최대 보유 일수
    execution_timing: str = "NEXT_OPEN"   # NEXT_OPEN / NEXT_CLOSE / LEGACY_SAME_CLOSE


@dataclass
class Position:
    """보유 포지션"""
    symbol: str
    entry_date: str
    entry_price: float
    quantity: int
    strategy: str
    entry_fee: float = 0.0
    hold_days: int = 0
    stop_loss: float = 0.0
    take_profit: float = 0.0


class BacktestEngine:
    """
    과거 데이터 전략 시뮬레이션 엔진
    - 일봉 데이터를 순차적으로 처리
    - 전략 시그널에 따라 가상 매매
    - 수수료/슬리피지/손절/익절 반영
    """

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.cash = self.config.initial_capital
        self.positions: list[Position] = []
        self.trades: list[TradeRecord] = []
        self.equity_curve: list[float] = []
        self.fee_model = KoreaStockFeeModel(
            commission_rate_pct=self.config.commission_rate,
            sell_tax_rate_pct=self.config.sell_tax_rate,
        )
        self.fill_model = LimitGuardFillModel(
            NextBarOHLCFillModel(slippage_rate_pct=self.config.slippage_rate),
        )

        # 전략 초기화
        if self.config.strategy_type == "STABLE_SHORT":
            self.strategy = StableShortStrategy(
                stop_loss_pct=self.config.stop_loss_pct,
                take_profit_pct=self.config.take_profit_pct,
                min_confidence=0.5,  # 백테스트는 기술지표 기반이므로 낮춤
            )
        else:
            self.strategy = AggressiveShortStrategy(
                stop_loss_pct=self.config.stop_loss_pct,
                take_profit_pct=self.config.take_profit_pct,
                min_confidence=0.5,
            )

    async def run(self, symbol: str, df: pd.DataFrame) -> dict:
        """
        백테스팅 실행

        Args:
            symbol: 종목 심볼
            df: OHLCV DataFrame (date, open, high, low, close, volume)

        Returns:
            dict: {"metrics": BacktestMetrics, "trades": list[TradeRecord], "equity_curve": list}
        """
        if df.empty or len(df) < 30:
            return {"error": "데이터가 부족합니다 (최소 30봉 필요)"}

        self.cash = self.config.initial_capital
        self.positions = []
        self.trades = []
        self.equity_curve = [self.config.initial_capital]

        logger.info("백테스팅 시작: {} ({} → {}, {}봉)", symbol,
                     df.iloc[0].get("date", ""), df.iloc[-1].get("date", ""), len(df))

        # 지표 계산을 위해 최소 lookback 필요 (30봉부터 시작)
        pending_signal: tuple[SignalAction, str] | None = None
        for i in range(30, len(df)):
            current_bar = df.iloc[i]
            lookback_df = df.iloc[:i + 1].copy()

            current_date = str(current_bar.get("date", i))
            open_price = float(current_bar["open"])
            current_price = float(current_bar["close"])
            high = float(current_bar["high"])
            low = float(current_bar["low"])

            # 1. 이전 봉 시그널을 현재 봉 시가에 체결한다.
            if pending_signal and self.config.execution_timing == "NEXT_OPEN":
                self._execute_signal(symbol, pending_signal[0], current_date, open_price, pending_signal[1], current_bar)
                pending_signal = None

            # 2. 기존 포지션 체크 (손절/익절/최대 보유일)
            self._check_positions(current_date, current_price, high, low)

            # 3. 이전 봉 시그널을 현재 봉 종가에 체결한다.
            if pending_signal and self.config.execution_timing == "NEXT_CLOSE":
                self._execute_signal(symbol, pending_signal[0], current_date, current_price, pending_signal[1], current_bar)
                pending_signal = None

            # 4. 기술 지표 계산
            indicators = TechnicalIndicators.calculate_all(lookback_df)

            # 5. 간이 분석 결과 생성 (AI 대신 기술지표 기반 규칙)
            analysis = self._build_rule_based_analysis(indicators, current_price)

            # 6. 전략 평가
            analysis["symbol"] = symbol
            analysis["stock_id"] = ""
            analysis["current_price"] = current_price

            signal = await self.strategy.evaluate(analysis)

            # 7. 시그널에 따라 매매. 기본 정책은 다음 봉 체결이며, legacy만 같은 봉 종가 체결을 허용한다.
            if signal and signal.action in {SignalAction.BUY, SignalAction.SELL}:
                if self.config.execution_timing == "LEGACY_SAME_CLOSE":
                    self._execute_signal(symbol, signal.action, current_date, current_price, "SIGNAL", current_bar)
                else:
                    pending_signal = (signal.action, "SIGNAL")

            # 8. 자산 곡선 기록
            total_equity = self._calculate_equity(current_price)
            self.equity_curve.append(total_equity)

            # 보유 기간 카운트
            for pos in self.positions:
                pos.hold_days += 1

        # 잔여 포지션 청산
        if self.positions:
            final_price = float(df.iloc[-1]["close"])
            final_date = str(df.iloc[-1].get("date", ""))
            for pos in list(self.positions):
                self._close_position(pos, final_date, final_price, "END_OF_DATA")

        metrics = calculate_metrics(self.trades, self.equity_curve, self.config.initial_capital)

        logger.info("백테스팅 완료: {}거래, 승률 {:.1f}%, 총수익 {:.2f}%, MDD {:.2f}%",
                     metrics.total_trades, metrics.win_rate * 100,
                     metrics.total_return, metrics.max_drawdown)

        return {
            "metrics": metrics,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "metadata": self.metadata(),
        }

    def _build_rule_based_analysis(self, indicators: dict, current_price: float) -> dict:
        """기술지표 기반 규칙 분석 (AI 대체)"""
        rsi = indicators.get("rsi_14")
        macd_hist = indicators.get("macd_histogram")
        cross = indicators.get("cross_signal")

        recommendation = "HOLD"
        confidence = 0.5

        # 매수 조건
        buy_score = 0
        if rsi is not None and rsi < 30:
            buy_score += 2
        elif rsi is not None and rsi < 40:
            buy_score += 1
        if macd_hist is not None and macd_hist > 0:
            buy_score += 1
        if cross == "GOLDEN_CROSS":
            buy_score += 2

        # 매도 조건
        sell_score = 0
        if rsi is not None and rsi > 70:
            sell_score += 2
        elif rsi is not None and rsi > 60:
            sell_score += 1
        if macd_hist is not None and macd_hist < 0:
            sell_score += 1
        if cross == "DEAD_CROSS":
            sell_score += 2

        if buy_score >= 3:
            recommendation = "BUY"
            confidence = min(0.5 + buy_score * 0.1, 0.9)
        elif sell_score >= 3:
            recommendation = "SELL"
            confidence = min(0.5 + sell_score * 0.1, 0.9)

        return {
            "recommendation": recommendation,
            "confidence": confidence,
            "indicators": indicators,
        }

    def _check_positions(self, current_date: str, close: float, high: float, low: float) -> None:
        """기존 포지션 손절/익절/최대보유일 체크"""
        for pos in list(self.positions):
            # 손절 체크 (장중 저가 기준)
            if low <= pos.stop_loss:
                self._close_position(pos, current_date, pos.stop_loss, "STOP_LOSS")
                continue

            # 익절 체크 (장중 고가 기준)
            if high >= pos.take_profit:
                self._close_position(pos, current_date, pos.take_profit, "TAKE_PROFIT")
                continue

            # 최대 보유 기간 초과
            if pos.hold_days >= self.config.max_hold_days:
                self._close_position(pos, current_date, close, "MAX_HOLD_DAYS")

    def _buy(self, symbol: str, date: str, price: float, bar=None) -> None:
        """매수 실행"""
        max_amount = self.cash * (self.config.max_position_pct / 100)
        max_amount = min(max_amount, self.cash * 0.9)  # 현금 10% 유지

        fill_probe = self.fill_model.fill_market_order(
            side="BUY",
            requested_quantity=1,
            reference_price=price,
            bar=bar,
        )
        if not fill_probe.filled:
            return

        actual_price = fill_probe.price
        quantity = int(max_amount / actual_price)

        if quantity <= 0:
            return

        fee = self.fee_model.calculate(side="BUY", price=actual_price, quantity=quantity)
        total_cost = abs(fee.cash_delta)

        if total_cost > self.cash:
            quantity = int(self.cash / (actual_price * (1 + self.config.commission_rate / 100)))
            if quantity <= 0:
                return
            fee = self.fee_model.calculate(side="BUY", price=actual_price, quantity=quantity)
            total_cost = abs(fee.cash_delta)

        self.cash -= total_cost

        stop_loss = actual_price * (1 + self.config.stop_loss_pct / 100)
        take_profit = actual_price * (1 + self.config.take_profit_pct / 100)

        self.positions.append(Position(
            symbol=symbol,
            entry_date=date,
            entry_price=actual_price,
            quantity=quantity,
            strategy=self.config.strategy_type,
            entry_fee=fee.commission + fee.tax,
            stop_loss=stop_loss,
            take_profit=take_profit,
        ))

    def _sell(self, symbol: str, date: str, price: float, reason: str, bar=None) -> None:
        """매도 실행"""
        for pos in list(self.positions):
            if pos.symbol == symbol:
                self._close_position(pos, date, price, reason, bar=bar)
                break

    def _execute_signal(
        self,
        symbol: str,
        action: SignalAction,
        date: str,
        price: float,
        reason: str,
        bar=None,
    ) -> None:
        if action == SignalAction.BUY and not self._has_position(symbol):
            self._buy(symbol, date, price, bar=bar)
        elif action == SignalAction.SELL and self._has_position(symbol):
            self._sell(symbol, date, price, reason, bar=bar)

    def _close_position(self, pos: Position, date: str, price: float, reason: str, bar=None) -> None:
        """포지션 청산"""
        fill = self.fill_model.fill_market_order(
            side="SELL",
            requested_quantity=pos.quantity,
            reference_price=price,
            bar=bar,
        )
        if not fill.filled:
            return

        actual_price = fill.price
        fee = self.fee_model.calculate(side="SELL", price=actual_price, quantity=pos.quantity)
        net = fee.cash_delta

        self.cash += net

        pnl = net - (pos.entry_price * pos.quantity) - pos.entry_fee
        return_pct = ((actual_price - pos.entry_price) / pos.entry_price) * 100

        self.trades.append(TradeRecord(
            symbol=pos.symbol,
            side="SELL",
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date,
            exit_price=actual_price,
            quantity=pos.quantity,
            pnl=round(pnl, 2),
            return_pct=round(return_pct, 2),
            hold_days=pos.hold_days,
            strategy=pos.strategy,
            reason=reason,
        ))

        self.positions.remove(pos)

    def _has_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol for p in self.positions)

    def _calculate_equity(self, current_price: float) -> float:
        stock_value = sum(p.quantity * current_price for p in self.positions)
        return self.cash + stock_value

    def metadata(self) -> dict:
        return {
            "model_family": "RULE_BASED_TECHNICAL_PROXY",
            "execution_policy": self.config.execution_timing,
            "fee_model": self.fee_model.metadata(),
            "fill_model": self.fill_model.metadata(),
        }
