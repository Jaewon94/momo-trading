from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.paths import DEFAULT_DATABASE_URL

DEFAULT_LLM_MODEL = "DEFAULT"


def normalize_llm_model_value(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text.upper() == DEFAULT_LLM_MODEL:
        return DEFAULT_LLM_MODEL
    return text


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    APP_NAME: str = "momo-trading"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "local"  # local | staging | production

    DATABASE_URL: str = DEFAULT_DATABASE_URL
    SQLITE_BUSY_TIMEOUT_MS: int = 5000
    SQLITE_WRITE_RETRY_COUNT: int = 3
    SQLITE_WRITE_RETRY_DELAY_MS: int = 150
    LOG_LEVEL: str = "DEBUG"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # === Broker Runtime ===
    # 기본값은 로컬 실사용 기준으로 Kiwoom을 우선한다.
    # 배포/테스트 환경에서는 .env 또는 runtime setting으로 override 가능하다.
    KIS_MCP_URL: str = "http://localhost:3100/sse"
    BROKER_PROVIDER: str = "KIWOOM"

    # === Kiwoom REST API ===
    KIWOOM_APP_KEY: str = ""
    KIWOOM_SECRET_KEY: str = ""
    KIWOOM_PAPER_APP_KEY: str = ""
    KIWOOM_PAPER_SECRET_KEY: str = ""
    KIWOOM_ACCOUNT_TYPE: str = "VIRTUAL"

    # KIS API 인증
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_PAPER_APP_KEY: str = ""
    KIS_PAPER_APP_SECRET: str = ""
    KIS_HTS_ID: str = ""
    KIS_ACCT_STOCK: str = ""
    KIS_PAPER_STOCK: str = ""
    KIS_PROD_TYPE: str = "01"
    KIS_ACCOUNT_TYPE: str = "VIRTUAL"

    # KIS WebSocket
    KIS_WS_URL_DOMESTIC: str = "ws://ops.koreainvestment.com:21000"
    KIS_WS_URL_OVERSEAS: str = "ws://ops.koreainvestment.com:31000"

    # === AI / LLM ===
    LLM_PROVIDER: str = "CLAUDE_CODE"  # 기본 provider (CLAUDE_CODE | CODEX)
    LLM_PROVIDER_TIER1: str = ""  # 비어있으면 LLM_PROVIDER 사용
    LLM_PROVIDER_TIER2: str = ""  # 비어있으면 LLM_PROVIDER 사용
    LLM_FALLBACK_PROVIDER_TIER1: str = ""  # CLAUDE_CODE | CODEX | 빈값
    LLM_FALLBACK_PROVIDER_TIER2: str = ""  # CLAUDE_CODE | CODEX | 빈값
    LLM_FALLBACK_MODEL_TIER1: str = DEFAULT_LLM_MODEL
    LLM_FALLBACK_MODEL_TIER2: str = DEFAULT_LLM_MODEL

    # Claude Code CLI
    CLAUDE_CODE_MODEL: str = DEFAULT_LLM_MODEL  # 기본값: CLI vendor default
    CLAUDE_CODE_MODEL_TIER1: str = DEFAULT_LLM_MODEL  # Tier1 override
    CLAUDE_CODE_MODEL_TIER2: str = DEFAULT_LLM_MODEL  # Tier2 override
    CLAUDE_CODE_PATH: str = ""  # 비어있으면 자동 탐색 (예: /opt/homebrew/bin/claude)

    # Codex CLI
    CODEX_MODEL: str = DEFAULT_LLM_MODEL  # 기본값: CLI vendor default
    CODEX_MODEL_TIER1: str = DEFAULT_LLM_MODEL  # Tier1 override
    CODEX_MODEL_TIER2: str = DEFAULT_LLM_MODEL  # Tier2 override
    CODEX_TIMEOUT_SEC_TIER1: int = 90
    CODEX_TIMEOUT_SEC_TIER2: int = 120
    CODEX_PATH: str = ""  # 비어있으면 자동 탐색 (예: /opt/homebrew/bin/codex)
    LLM_TIER1_CONCURRENCY: int = 2
    LLM_TIER2_CONCURRENCY: int = 1
    MANUAL_LLM_PROVIDER: str = "CLAUDE_CODE"  # CLAUDE_CODE | CODEX | OLLAMA
    MANUAL_LLM_MODEL: str = DEFAULT_LLM_MODEL
    MANUAL_LLM_FALLBACK_PROVIDER: str = ""
    MANUAL_LLM_FALLBACK_MODEL: str = DEFAULT_LLM_MODEL
    NEWS_LLM_ENABLED: bool = True
    NEWS_LLM_PROVIDER: str = "CLAUDE_CODE"  # CLAUDE_CODE | CODEX | OLLAMA
    NEWS_LLM_MODEL: str = DEFAULT_LLM_MODEL
    NEWS_LLM_FALLBACK_PROVIDER: str = ""
    NEWS_LLM_FALLBACK_MODEL: str = DEFAULT_LLM_MODEL
    NEWS_DOMESTIC_MEDIA_ENABLED: bool = False
    NEWS_INCLUDE_FOREIGN: bool = True
    NEWS_TRANSLATE_FOREIGN_ENABLED: bool = True
    NEWS_NASDAQ_ENABLED: bool = False
    NEWS_GATE_ENABLED: bool = True
    NEWS_LOOKBACK_HOURS: int = 24
    NEWS_MAX_ITEMS_PER_SYMBOL: int = 20
    NEWS_NEGATIVE_BLOCK_THRESHOLD: float = 0.75
    NEWS_FRESHNESS_HALFLIFE_HOURS: float = 8.0
    NEWS_POLL_ENABLED: bool = True
    NEWS_POLL_INTERVAL_MIN_TRADING: int = 5
    NEWS_POLL_INTERVAL_MIN_OFF_HOURS: int = 30
    NEWS_POLL_PAGE_COUNT: int = 25
    NEWS_FETCH_CONCURRENCY: int = 4
    NEWS_SOURCE_FAILURE_THRESHOLD: int = 3
    NEWS_SOURCE_FAILURE_COOLDOWN_MIN: int = 30
    NEWS_TRANSLATION_CONCURRENCY: int = 3
    NEWS_CLAUDE_SHARE_SESSION: bool = True
    NEWS_RECHECK_COOLDOWN_SEC: int = 300
    BROKER_BALANCE_RETRY_COUNT: int = 2
    BROKER_BALANCE_RETRY_DELAY_MS: int = 700
    NEWS_SHADOW_ENABLED: bool = True
    NEWS_ROLLOUT_MIN_SAMPLE_SIZE: int = 12
    NEWS_ROLLOUT_MIN_PROFIT_FACTOR: float = 1.1
    NEWS_ROLLOUT_MIN_EXPECTANCY: float = 0.0
    NEWS_ROLLOUT_MAX_DRAWDOWN_KRW: float = 500000.0
    METRICS_RESOURCE_SAMPLING_ENABLED: bool = True
    METRICS_RESOURCE_INTERVAL_MIN: int = 5
    METRICS_MAINTENANCE_ENABLED: bool = True
    METRICS_MAINTENANCE_INTERVAL_MIN: int = 60
    METRICS_ROLLUP_LOOKBACK_HOURS: int = 72
    METRICS_RAW_RETENTION_DAYS: int = 30
    METRICS_ROLLUP_RETENTION_DAYS: int = 365
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_MODEL_TIER1: str = DEFAULT_LLM_MODEL
    OLLAMA_MODEL_TIER2: str = DEFAULT_LLM_MODEL
    OLLAMA_GENERATE_TIMEOUT_SEC: int = 180
    OPEN_DART_API_KEY: str = ""

    # === AI Agent ===
    AUTONOMY_MODE: str = "AUTONOMOUS"  # AUTONOMOUS / SEMI_AUTO
    RECOMMENDATION_EXPIRE_MIN: int = 60
    MIN_BUY_QUANTITY: int = 1

    # === Trading Safety ===
    TRADING_ENABLED: bool = True
    ORDER_SUBMISSION_MODE: str = "FULL"  # FULL | SELL_ONLY | READ_ONLY
    DAY_TRADING_ONLY: bool = False  # True=당일 청산 필수, False=스윙 (유망 종목 오버나이트 보유)
    BUY_CUTOFF_HOUR: int = 14  # 신규 매수 마감 시각 (14시 이후 매수 차단)
    BUY_CUTOFF_MINUTE: int = 30
    FORCE_LIQUIDATION_HOUR: int = 15  # 강제 청산 시각 (종가경매 전)
    FORCE_LIQUIDATION_MINUTE: int = 10
    MAX_HOLD_DAYS_STABLE: int = 5  # STABLE_SHORT 최대 보유일
    MAX_HOLD_DAYS_AGGRESSIVE: int = 3  # AGGRESSIVE_SHORT 최대 보유일
    MAX_DAILY_TRADES: int = 0  # 0 = 무제한
    MAX_SINGLE_ORDER_KRW: int = 0  # 0 = AI 자율 결정 (시스템 하드 리밋 없음)
    MAX_SINGLE_ORDER_USD: int = 0  # 0 = AI 자율 결정
    ABS_MAX_DAILY_TRADES: int = 8  # AI/LLM 한도 제안에 항상 적용되는 절대 상한
    ABS_MAX_SINGLE_ORDER_KRW: int = 50_000_000  # 0이면 절대 주문금액 상한 비활성
    ABS_MAX_POSITION_PCT: float = 15.0  # 단일 포지션 비중 절대 상한(%)
    BUY_ORDER_EXECUTION_MODE: str = "LIMIT_GUARD"  # LIMIT_GUARD | MARKET
    BUY_SLIPPAGE_GUARD_BPS: int = 20  # LIMIT_GUARD 모드에서 허용 슬리피지 (bp)
    ORDER_RESERVATION_ENFORCEMENT: str = "SHADOW"  # SHADOW | ENFORCE
    AUTO_RISK_KILL_SWITCH_ENABLED: bool = True
    MAX_DAILY_DRAWDOWN_PCT: float = 2.5  # 일손실률 한도(%)
    MAX_CONSECUTIVE_LOSSES: int = 4
    MIN_STRATEGY_EXPECTANCY: float = 0.0
    EXPECTANCY_SAMPLE_SIZE: int = 12
    VOLATILITY_POSITION_SIZING_ENABLED: bool = True
    RISK_PER_TRADE_PCT: float = 0.5
    RISK_MULTIPLIER_SHORT: float = 0.7
    RISK_MULTIPLIER_MID: float = 1.0
    RISK_MULTIPLIER_LONG: float = 1.2
    COST_GATE_ENABLED: bool = True
    ESTIMATED_ENTRY_COST_BPS: int = 8
    ESTIMATED_EXIT_COST_BPS: int = 8
    ESTIMATED_SLIPPAGE_BPS_SHORT: int = 12
    ESTIMATED_SLIPPAGE_BPS_MID: int = 8
    ESTIMATED_SLIPPAGE_BPS_LONG: int = 6
    MIN_EDGE_TO_COST_RATIO_SHORT: float = 1.5
    MIN_EDGE_TO_COST_RATIO_MID: float = 1.3
    MIN_EDGE_TO_COST_RATIO_LONG: float = 1.1

    # === AI Risk Tuning ===
    AI_RISK_TUNING_ENABLED: bool = True
    RISK_APPETITE: str = "AGGRESSIVE"  # CONSERVATIVE / MODERATE / AGGRESSIVE
    MIN_CASH_RATIO: float = 0.0  # 최소 현금 비중 (0 = 제한 없음, 소액 계좌에서 매수 차단 방지)

    # === Scheduler ===
    SCHEDULER_ENABLED: bool = True

    @property
    def async_database_url(self) -> str:
        """Sync URL에서 async 드라이버 URL을 자동 생성"""
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+aiomysql://", 1)
        return url

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT == "local"

    @property
    def is_paper_trading(self) -> bool:
        return self.KIS_ACCOUNT_TYPE.upper() == "VIRTUAL"

    @property
    def normalized_broker_provider(self) -> str:
        return self.BROKER_PROVIDER.upper().strip()

    @property
    def uses_kis_broker(self) -> bool:
        return self.normalized_broker_provider == "KIS"

    @property
    def uses_kiwoom_broker(self) -> bool:
        return self.normalized_broker_provider == "KIWOOM"

    def validate_on_startup(self) -> None:
        """시작 시 필수 설정 검증 — 누락된 키에 대해 경고 로그"""
        llm_providers = {
            self.LLM_PROVIDER_TIER1 or self.LLM_PROVIDER or "CLAUDE_CODE",
            self.LLM_PROVIDER_TIER2 or self.LLM_PROVIDER or "CLAUDE_CODE",
            self.LLM_FALLBACK_PROVIDER_TIER1 or "",
            self.LLM_FALLBACK_PROVIDER_TIER2 or "",
        }

        claude_path = self._find_claude_path()
        if "CLAUDE_CODE" in llm_providers and claude_path:
            logger.debug("Claude Code CLI 감지: {}", claude_path)
        elif "CLAUDE_CODE" in llm_providers:
            logger.warning(
                "Claude Code CLI를 찾을 수 없음. "
                "CLAUDE_CODE_PATH를 설정하거나 claude CLI를 설치하세요."
            )

        codex_path = self._find_codex_path()
        if "CODEX" in llm_providers and codex_path:
            logger.debug("Codex CLI 감지: {}", codex_path)
        elif "CODEX" in llm_providers:
            logger.warning(
                "Codex CLI를 찾을 수 없음. "
                "CODEX_PATH를 설정하거나 codex CLI를 설치하세요."
            )

        broker_provider = self.normalized_broker_provider
        if broker_provider == "KIS":
            if not self.KIS_APP_KEY and not self.KIS_PAPER_APP_KEY:
                logger.warning(
                    "KIS API 키 미설정: KIS_APP_KEY, KIS_PAPER_APP_KEY 모두 비어있음. "
                    "실매매/모의투자 모두 불가합니다."
                )

        if broker_provider == "KIWOOM":
            if not self.KIWOOM_APP_KEY and not self.KIWOOM_PAPER_APP_KEY:
                logger.warning(
                    "Kiwoom API 키 미설정: KIWOOM_APP_KEY, KIWOOM_PAPER_APP_KEY 모두 비어있음. "
                    "실매매/모의투자 모두 불가합니다."
                )

        if not self.TRADING_ENABLED:
            logger.debug("TRADING_ENABLED=false: 매매 기능이 비활성화 상태입니다.")


    def _find_claude_path(self) -> str | None:
        """claude CLI 경로 탐색 (설정값 → PATH → 일반적 설치 경로)"""
        import os
        import shutil
        if self.CLAUDE_CODE_PATH:
            return self.CLAUDE_CODE_PATH
        path = shutil.which("claude")
        if path:
            return path
        for candidate in [
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            os.path.expanduser("~/.local/bin/claude"),
            os.path.expanduser("~/.npm-global/bin/claude"),
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _find_codex_path(self) -> str | None:
        """codex CLI 경로 탐색 (설정값 → PATH → 일반적 설치 경로)"""
        import os
        import shutil
        if self.CODEX_PATH:
            return self.CODEX_PATH
        path = shutil.which("codex")
        if path:
            return path
        for candidate in [
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None


settings = Settings()
