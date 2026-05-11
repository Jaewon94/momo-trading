"""Codex CLI Provider — 로컬 Codex CLI로 LLM 호출"""
import asyncio
import os
import shutil
import tempfile
import time

from loguru import logger

from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import LLMProvider, LLMTier


class CodexProvider:
    """Codex CLI를 subprocess로 호출하는 LLM Provider.

    현재는 비대화형 `codex exec` 기반 일회성 호출을 사용한다.
    Claude Code처럼 세션을 이어붙이진 않으며, 세션 관련 메서드는 no-op로 둔다.
    """

    _FAILURE_COOLDOWN_SEC = 300

    def __init__(self, tier: LLMTier = LLMTier.TIER1, model_override: str | None = None):
        self._tier = tier
        self._codex_path: str | None = None
        self._disabled_until = 0.0
        self._last_failure_reason = ""
        self._last_failure_kind = ""
        if model_override is not None:
            configured_model = model_override
        elif tier == LLMTier.TIER1:
            configured_model = settings.CODEX_MODEL_TIER1 or settings.CODEX_MODEL
        else:
            configured_model = settings.CODEX_MODEL_TIER2 or settings.CODEX_MODEL
        normalized_model = normalize_llm_model_value(configured_model)
        self._configured_model = normalized_model
        self._model = None if normalized_model == DEFAULT_LLM_MODEL else normalized_model

    @classmethod
    def start_session(cls) -> None:
        return None

    @classmethod
    def pause_session(cls) -> None:
        return None

    @classmethod
    def resume_session(cls, session_id: str | None) -> None:
        return None

    @classmethod
    def end_session(cls) -> None:
        return None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.CODEX

    @property
    def tier(self) -> LLMTier:
        return self._tier

    @property
    def model_id(self) -> str:
        return f"codex:{self._model or DEFAULT_LLM_MODEL}"

    def _find_codex(self) -> str | None:
        if self._codex_path:
            return self._codex_path

        configured = getattr(settings, "CODEX_PATH", "")
        if configured:
            self._codex_path = configured
            return configured

        path = shutil.which("codex")
        if path:
            self._codex_path = path
            return path

        for candidate in [
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                self._codex_path = candidate
                return candidate
        return None

    def _build_command(self, output_path: str) -> list[str]:
        codex = self._find_codex()
        if not codex:
            raise RuntimeError("codex CLI를 찾을 수 없습니다 (PATH 확인)")
        effort = self._reasoning_effort()

        config_overrides = [
            f'model_reasoning_effort="{effort}"',
            "mcp_servers={}",
            "features.multi_agent=false",
        ]

        return [
            codex,
            "exec",
            *[item for override in config_overrides for item in ("-c", override)],
            "--ephemeral",
            *([] if not self._model else ["--model", self._model]),
            "--sandbox",
            "read-only",
            "--output-last-message",
            output_path,
            "-",
        ]

    def _reasoning_effort(self) -> str:
        configured = (
            settings.CODEX_REASONING_EFFORT_TIER1
            if self._tier == LLMTier.TIER1
            else settings.CODEX_REASONING_EFFORT_TIER2
        )
        effort = str(configured or "").lower().strip()
        return effort if effort in {"low", "medium", "high", "xhigh"} else "medium"

    def _timeout_sec(self) -> float:
        if self._tier == LLMTier.TIER1:
            return float(settings.CODEX_TIMEOUT_SEC_TIER1)
        return float(settings.CODEX_TIMEOUT_SEC_TIER2)

    def status_snapshot(self) -> dict:
        path = self._find_codex()
        disabled_for_sec = max(0, int(self._disabled_until - time.monotonic())) if self._disabled_until else 0
        cooldown_active = disabled_for_sec > 0
        available = bool(path) and not cooldown_active
        return {
            "available": available,
            "cli_path": path or "",
            "cooldown_active": cooldown_active,
            "disabled_for_sec": disabled_for_sec,
            "last_failure_reason": self._last_failure_reason,
            "last_failure_kind": self._last_failure_kind,
        }

    async def _terminate_process(self, proc) -> None:
        if proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    @staticmethod
    def _clean_env() -> dict[str, str]:
        """subprocess용 환경변수 정리.

        부모 세션/샌드박스 전용 환경변수가 하위 Codex 실행에 섞이지 않게 한다.
        """
        env = os.environ.copy()
        for key in [
            "CLAUDECODE",
            "CLAUDE_CODE_ENTRYPOINT",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
            "CODEX_THREAD_ID",
            "CODEX_SANDBOX",
            "CODEX_SANDBOX_NETWORK_DISABLED",
        ]:
            env.pop(key, None)
        env.setdefault("OTEL_SDK_DISABLED", "true")
        if settings.OPENAI_API_KEY:
            env["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
        return env

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{prompt}"

        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tmp:
            output_path = tmp.name

        cmd = self._build_command(output_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._clean_env(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=full_prompt.encode("utf-8")),
                    timeout=self._timeout_sec(),
                )
            except asyncio.TimeoutError as exc:
                self._disabled_until = time.monotonic() + self._FAILURE_COOLDOWN_SEC
                self._last_failure_kind = "timeout"
                self._last_failure_reason = f"Codex CLI timeout ({self._timeout_sec():.0f}s)"
                await self._terminate_process(proc)
                logger.error("Codex CLI timeout ({}s)", self._timeout_sec())
                raise RuntimeError(f"Codex CLI timeout ({self._timeout_sec():.0f}s)") from exc

            if proc.returncode != 0:
                self._disabled_until = time.monotonic() + self._FAILURE_COOLDOWN_SEC
                err = stderr.decode("utf-8", errors="replace")[:500]
                if not err.strip():
                    err = stdout.decode("utf-8", errors="replace")[:500]
                self._last_failure_kind = "exit_nonzero"
                self._last_failure_reason = f"Codex CLI 실패 (exit {proc.returncode}): {err}"
                logger.error("Codex CLI 호출 실패 (exit {}): {}", proc.returncode, err)
                raise RuntimeError(f"Codex CLI 실패 (exit {proc.returncode}): {err}")

            with open(output_path, encoding="utf-8") as handle:
                result = handle.read().strip()

            if not result:
                self._last_failure_kind = "empty_response"
                self._last_failure_reason = "Codex CLI 빈 응답"
                raise RuntimeError("Codex CLI 빈 응답")

            self._disabled_until = 0.0
            self._last_failure_kind = ""
            self._last_failure_reason = ""
            return result
        finally:
            try:
                os.remove(output_path)
            except OSError:
                pass

    async def is_available(self) -> bool:
        status = self.status_snapshot()
        path = status["cli_path"]
        if not path:
            logger.debug("Codex CLI를 찾을 수 없음 (PATH, /opt/homebrew/bin 등 확인)")
            return False
        if status["cooldown_active"]:
            logger.debug(
                "Codex CLI 일시 비활성화 상태 (최근 호출 실패: {} / 남은 {}s)",
                status["last_failure_reason"] or "unknown",
                status["disabled_for_sec"],
            )
            return False
        return True
