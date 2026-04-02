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
    LOG_LEVEL: str = "DEBUG"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # === KIS MCP 서버 ===
    KIS_MCP_URL: str = "http://localhost:3100/sse"
    BROKER_PROVIDER: str = "KIS"

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
    CODEX_PATH: str = ""  # 비어있으면 자동 탐색 (예: /opt/homebrew/bin/codex)
    MANUAL_LLM_PROVIDER: str = "AUTOMATIC"  # AUTOMATIC | CLAUDE_CODE | CODEX

    # === AI Agent ===
    AUTONOMY_MODE: str = "AUTONOMOUS"  # AUTONOMOUS / SEMI_AUTO
    RECOMMENDATION_EXPIRE_MIN: int = 60
    MIN_BUY_QUANTITY: int = 1

    # === Trading Safety ===
    TRADING_ENABLED: bool = True
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

        broker_provider = self.BROKER_PROVIDER.upper()
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
