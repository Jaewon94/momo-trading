import asyncio

from core.config import Settings
from core.paths import DEFAULT_DATABASE_PATH, DEFAULT_DATABASE_URL, RUNTIME_DATA_DIR
from trading.kis_api import TOKEN_FILE
from trading.kiwoom_rest_client import KiwoomRESTClient


def test_settings_default_database_url_uses_runtime_data() -> None:
    settings = Settings(_env_file=None)

    assert settings.DATABASE_URL == DEFAULT_DATABASE_URL
    assert DEFAULT_DATABASE_PATH == RUNTIME_DATA_DIR / "app.db"


def test_broker_token_cache_defaults_use_runtime_data() -> None:
    client = KiwoomRESTClient()
    try:
        assert TOKEN_FILE == RUNTIME_DATA_DIR / "kis_token.json"
        assert client._token_cache_path == RUNTIME_DATA_DIR / "kiwoom_token.json"
    finally:
        asyncio.run(client.close())
