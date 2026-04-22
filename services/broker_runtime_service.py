"""브로커별 런타임 초기화/종료 조정"""
from loguru import logger

from core.config import settings
from trading.mcp_client import mcp_client


class BrokerRuntimeService:
    """앱 생명주기에서 브로커별 부가 런타임을 조정한다."""

    @property
    def broker_provider(self) -> str:
        return settings.BROKER_PROVIDER.upper()

    @property
    def mcp_required(self) -> bool:
        return self.broker_provider == "KIS"

    @property
    def mcp_connected(self) -> bool:
        return mcp_client.is_connected

    async def startup(self) -> None:
        """필요한 브로커 부가 런타임을 시작한다."""
        if not self.mcp_required:
            logger.debug("BROKER_PROVIDER={} → MCP 초기화 건너뜀", self.broker_provider)
            return

        try:
            await mcp_client.connect()
            tools = await mcp_client.list_tools()
            logger.info("MCP 도구 목록 ({}개): {}", len(tools), [t.get("name") for t in tools])
        except Exception as exc:
            logger.warning("MCP 서버 연결 실패 (나중에 재시도): {}", str(exc))

    async def shutdown(self) -> None:
        """브로커 런타임을 정리한다."""
        await mcp_client.disconnect()


broker_runtime_service = BrokerRuntimeService()
