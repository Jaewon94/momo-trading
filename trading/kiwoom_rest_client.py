"""Kiwoom REST API 저수준 클라이언트"""
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from core.config import settings
from core.paths import RUNTIME_DATA_DIR


@dataclass
class KiwoomAPIResponse:
    """Kiwoom HTTP 응답"""
    body: dict[str, Any]
    headers: dict[str, str]
    status_code: int


@dataclass
class KiwoomToken:
    """Kiwoom access token"""
    access_token: str
    expires_at: datetime


class KiwoomRESTClient:
    """OAuth 토큰 발급과 REST 요청을 담당한다."""

    REAL_BASE_URL = "https://api.kiwoom.com"
    MOCK_BASE_URL = "https://mockapi.kiwoom.com"

    def __init__(
        self,
        *,
        app_key: str | None = None,
        secret_key: str | None = None,
        paper_app_key: str | None = None,
        paper_secret_key: str | None = None,
        account_type: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        token_cache_path: str | Path | None = RUNTIME_DATA_DIR / "kiwoom_token.json",
    ) -> None:
        self._app_key = app_key if app_key is not None else settings.KIWOOM_APP_KEY
        self._secret_key = secret_key if secret_key is not None else settings.KIWOOM_SECRET_KEY
        self._paper_app_key = (
            paper_app_key if paper_app_key is not None else settings.KIWOOM_PAPER_APP_KEY
        )
        self._paper_secret_key = (
            paper_secret_key
            if paper_secret_key is not None
            else settings.KIWOOM_PAPER_SECRET_KEY
        )
        self._account_type = (account_type or settings.KIWOOM_ACCOUNT_TYPE).upper()
        self._token_cache_path = Path(token_cache_path) if token_cache_path else None
        self._token: KiwoomToken | None = None
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=True,
        )

    @property
    def base_url(self) -> str:
        return self.MOCK_BASE_URL if self.is_paper_trading else self.REAL_BASE_URL

    @property
    def is_paper_trading(self) -> bool:
        return self._account_type == "VIRTUAL"

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        *,
        api_id: str,
        endpoint: str,
        body: dict[str, Any],
        cont_yn: str = "N",
        next_key: str = "",
    ) -> KiwoomAPIResponse:
        retried_with_new_token = False
        rate_limit_retries = 0

        while True:
            token = await self.get_access_token()
            try:
                response = await self._client.post(
                    f"{self.base_url}{endpoint}",
                    headers={
                        "Content-Type": "application/json;charset=UTF-8",
                        "authorization": f"Bearer {token}",
                        "cont-yn": cont_yn,
                        "next-key": next_key,
                        "api-id": api_id,
                    },
                    json=body,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and rate_limit_retries < 2:
                    rate_limit_retries += 1
                    await asyncio.sleep(0.35 * rate_limit_retries)
                    continue
                raise
            payload = response.json()

            if (
                not retried_with_new_token
                and isinstance(payload, dict)
                and self._is_invalid_token_response(payload)
            ):
                self._invalidate_cached_token()
                retried_with_new_token = True
                continue

            return KiwoomAPIResponse(
                body=payload if isinstance(payload, dict) else {"data": payload},
                headers={
                    "cont-yn": response.headers.get("cont-yn", ""),
                    "next-key": response.headers.get("next-key", ""),
                    "api-id": response.headers.get("api-id", api_id),
                },
                status_code=response.status_code,
            )

    async def get_access_token(self) -> str:
        if self._token and self._token.expires_at > datetime.now() + timedelta(minutes=1):
            return self._token.access_token

        cached = self._load_cached_token()
        if cached:
            self._token = cached
            return cached.access_token

        issued = await self._issue_token()
        self._token = issued
        self._save_cached_token(issued)
        return issued.access_token

    async def _issue_token(self) -> KiwoomToken:
        app_key, secret_key = self._get_credentials()
        if not app_key or not secret_key:
            raise RuntimeError("Kiwoom API 키가 설정되지 않았습니다")

        response = await self._client.post(
            f"{self.base_url}/oauth2/token",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "secretkey": secret_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("token", "")
        expires_dt = payload.get("expires_dt", "")
        if not token or not expires_dt:
            raise RuntimeError("Kiwoom access token 응답이 올바르지 않습니다")

        return KiwoomToken(
            access_token=token,
            expires_at=datetime.strptime(expires_dt, "%Y%m%d%H%M%S"),
        )

    def _get_credentials(self) -> tuple[str, str]:
        if self.is_paper_trading:
            return self._paper_app_key, self._paper_secret_key
        return self._app_key, self._secret_key

    def _load_cached_token(self) -> KiwoomToken | None:
        if self._token_cache_path is None or not self._token_cache_path.exists():
            return None

        try:
            data = json.loads(self._token_cache_path.read_text())
            if data.get("account_type") != self._account_type:
                return None
            expires_at = datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
            if expires_at <= datetime.now() + timedelta(minutes=1):
                return None
            return KiwoomToken(
                access_token=data["token"],
                expires_at=expires_at,
            )
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            return None

    def _save_cached_token(self, token: KiwoomToken) -> None:
        if self._token_cache_path is None:
            return
        try:
            self._token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_cache_path.write_text(json.dumps({
                "account_type": self._account_type,
                "token": token.access_token,
                "expires_dt": token.expires_at.strftime("%Y%m%d%H%M%S"),
            }))
        except OSError:
            return

    @staticmethod
    def _is_invalid_token_response(payload: dict[str, Any]) -> bool:
        return payload.get("return_code") == 3 and "Token이 유효하지 않습니다" in str(
            payload.get("return_msg", "")
        )

    def _invalidate_cached_token(self) -> None:
        self._token = None
        if self._token_cache_path is None:
            return
        try:
            self._token_cache_path.unlink(missing_ok=True)
        except OSError:
            return
