"""LLM CLI 사용량/상태 집계 서비스."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from analysis.llm.claude_code_provider import ClaudeCodeProvider
from analysis.llm.codex_provider import CodexProvider


class LLMUsageService:
    """Claude Code / Codex 로컬 상태를 화면용으로 정리한다."""

    CLAUDE_STATUSLINE_DOC_URL = "https://code.claude.com/docs/en/statusline"
    CLAUDE_USAGE_LIMIT_DOC_URL = "https://support.anthropic.com/en/articles/8241175-how-do-i-increase-my-message-limit"
    CODEX_USAGE_DOC_URL = "https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan.pdf"
    CODEX_CLI_DOC_URL = "https://developers.openai.com/codex/cli/reference"

    async def get_snapshot(self) -> dict:
        claude_code, codex = await asyncio.gather(
            self._collect_claude_code_usage(),
            self._collect_codex_usage(),
        )
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "claude_code": claude_code,
            "codex": codex,
        }

    async def _collect_claude_code_usage(self) -> dict:
        binary_path = ClaudeCodeProvider()._find_claude()
        auth = await self._get_claude_auth_status(binary_path)
        historical_usage = self._read_claude_stats_cache()

        return {
            "provider": "CLAUDE_CODE",
            "available": bool(binary_path),
            "binary_path": binary_path,
            "auth": auth,
            "official": {
                "docs_url": self.CLAUDE_STATUSLINE_DOC_URL,
                "usage_limit_docs_url": self.CLAUDE_USAGE_LIMIT_DOC_URL,
                "live_rate_limits_supported": True,
                "live_context_supported": True,
                "live_metrics_available_in_current_app": False,
                "availability_reason": (
                    "Claude Code 공식 status line 데이터는 interactive Claude Code 세션에서만 "
                    "stdin JSON으로 제공됩니다. 현재 앱은 비대화형 `claude -p` 호출을 사용해 "
                    "실시간 잔여 quota를 직접 수집하지 않습니다."
                ),
            },
            "historical_usage": historical_usage,
            "app_usage": ClaudeCodeProvider.get_usage_snapshot(),
        }

    async def _collect_codex_usage(self) -> dict:
        binary_path = CodexProvider()._find_codex()
        auth = await self._get_codex_auth_status(binary_path)

        return {
            "provider": "CODEX",
            "available": bool(binary_path),
            "binary_path": binary_path,
            "auth": auth,
            "official": {
                "docs_url": self.CODEX_USAGE_DOC_URL,
                "cli_docs_url": self.CODEX_CLI_DOC_URL,
                "login_status_supported": True,
                "local_remaining_usage_supported": False,
                "availability_reason": (
                    "OpenAI 공식 문서상 플랜별 사용량 정책은 안내되지만, "
                    "local environment usage는 제공되지 않습니다."
                ),
            },
        }

    def _read_claude_stats_cache(self) -> dict | None:
        stats_path = Path.home() / ".claude" / "stats-cache.json"
        if not stats_path.exists():
            return None

        data = json.loads(stats_path.read_text())
        model_usage = data.get("modelUsage", {})
        top_models = [
            {
                "model": model,
                "input_tokens": usage.get("inputTokens", 0),
                "output_tokens": usage.get("outputTokens", 0),
                "cache_read_input_tokens": usage.get("cacheReadInputTokens", 0),
                "cache_creation_input_tokens": usage.get("cacheCreationInputTokens", 0),
                "cost_usd": usage.get("costUSD", 0),
            }
            for model, usage in model_usage.items()
        ]

        return {
            "available": True,
            "last_computed_date": data.get("lastComputedDate"),
            "first_session_date": data.get("firstSessionDate"),
            "total_sessions": data.get("totalSessions", 0),
            "total_messages": data.get("totalMessages", 0),
            "top_models": top_models,
            "recent_daily_activity": data.get("dailyActivity", [])[-7:],
        }

    async def _get_claude_auth_status(self, binary_path: str | None) -> dict:
        if not binary_path:
            return {
                "supported": True,
                "logged_in": False,
                "error": "claude CLI를 찾을 수 없습니다",
            }

        result = await self._run_command([binary_path, "auth", "status"])
        stdout = result["stdout"].strip()

        if stdout:
            try:
                payload = json.loads(stdout)
                return {
                    "supported": True,
                    "logged_in": bool(payload.get("loggedIn")),
                    "auth_method": payload.get("authMethod"),
                    "api_provider": payload.get("apiProvider"),
                    "raw": payload,
                }
            except json.JSONDecodeError:
                pass

        return {
            "supported": True,
            "logged_in": False,
            "error": result["stderr"].strip() or stdout or "인증 상태를 해석할 수 없습니다",
        }

    async def _get_codex_auth_status(self, binary_path: str | None) -> dict:
        if not binary_path:
            return {
                "supported": True,
                "logged_in": False,
                "error": "codex CLI를 찾을 수 없습니다",
            }

        result = await self._run_command([binary_path, "login", "status"])
        status_text = result["stdout"].strip() or result["stderr"].strip()
        lowered = status_text.lower()

        logged_in = result["returncode"] == 0 and "logged in" in lowered
        auth_mode = ""
        if "chatgpt" in lowered:
            auth_mode = "ChatGPT"
        elif "api key" in lowered:
            auth_mode = "API key"

        return {
            "supported": True,
            "logged_in": logged_in,
            "auth_mode": auth_mode or None,
            "raw_status": status_text,
        }

    async def _run_command(self, cmd: list[str], timeout_sec: float = 5.0) -> dict:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "returncode": 124,
                "stdout": "",
                "stderr": f"timeout after {timeout_sec:.0f}s",
            }

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


llm_usage_service = LLMUsageService()
