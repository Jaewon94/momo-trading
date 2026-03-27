"""로컬 Claude/Codex CLI 상태 점검 도구.

예시:
    .venv313/bin/python -m tools.llm_cli_smoke
    .venv313/bin/python -m tools.llm_cli_smoke --provider codex --live
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass

from core.config import settings


SMOKE_PROMPT = "Reply with exactly OK and nothing else."


@dataclass
class SmokeResult:
    provider: str
    configured_path: str
    binary_found: bool
    command_ok: bool
    live_ok: bool
    model: str
    summary: str
    detail: str = ""


def _truncate(text: str, limit: int = 400) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _classify_failure(output: str) -> str:
    lowered = output.lower()
    if "not logged in" in lowered or "please run /login" in lowered:
        return "로그인 필요"
    if "failed to lookup address information" in lowered or "name or service not known" in lowered:
        return "네트워크/DNS 접근 불가"
    if "operation not permitted" in lowered:
        return "로컬 권한 또는 샌드박스 제약"
    if "timed out" in lowered:
        return "응답 시간 초과"
    return "CLI 호출 실패"


def _run_command(args: list[str], *, stdin_text: str | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        input=stdin_text,
        text=True,
        capture_output=True,
        timeout=60,
        env=os.environ.copy(),
    )
    output = (proc.stderr or "") + ("\n" if proc.stderr and proc.stdout else "") + (proc.stdout or "")
    return proc.returncode, _truncate(output)


def _claude_result(live: bool) -> SmokeResult:
    path = settings._find_claude_path() or ""
    model = settings.CLAUDE_CODE_MODEL_TIER1 or settings.CLAUDE_CODE_MODEL or "haiku"
    if not path:
        return SmokeResult("CLAUDE_CODE", "", False, False, False, model, "claude CLI 미발견")

    version_code, version_output = _run_command([path, "--help"])
    if version_code != 0:
        return SmokeResult("CLAUDE_CODE", path, True, False, False, model, "claude CLI 실행 실패", version_output)

    if not live:
        return SmokeResult("CLAUDE_CODE", path, True, True, False, model, "바이너리/도움말 확인 완료")

    command = [
        path,
        "-p",
        "--output-format",
        "text",
        "--model",
        model,
        "--dangerously-skip-permissions",
        SMOKE_PROMPT,
    ]
    code, output = _run_command(command)
    if code == 0 and output.strip() == "OK":
        return SmokeResult("CLAUDE_CODE", path, True, True, True, model, "live 응답 성공", output)
    return SmokeResult(
        "CLAUDE_CODE",
        path,
        True,
        True,
        False,
        model,
        _classify_failure(output),
        output,
    )


def _codex_result(live: bool) -> SmokeResult:
    path = settings._find_codex_path() or ""
    model = settings.CODEX_MODEL_TIER1 or settings.CODEX_MODEL or "gpt-5-codex"
    if not path:
        return SmokeResult("CODEX", "", False, False, False, model, "codex CLI 미발견")

    version_code, version_output = _run_command([path, "--version"])
    if version_code != 0:
        return SmokeResult("CODEX", path, True, False, False, model, "codex CLI 실행 실패", version_output)

    if not live:
        return SmokeResult("CODEX", path, True, True, False, model, "바이너리/버전 확인 완료", version_output)

    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        output_path = handle.name

    try:
        command = [
            path,
            "exec",
            "--ephemeral",
            "--model",
            model,
            "--sandbox",
            "read-only",
            "--output-last-message",
            output_path,
            "-",
        ]
        code, output = _run_command(command, stdin_text=SMOKE_PROMPT)
        if code == 0:
            with open(output_path, encoding="utf-8") as handle:
                response = handle.read().strip()
            if response == "OK":
                return SmokeResult("CODEX", path, True, True, True, model, "live 응답 성공", response)
            return SmokeResult("CODEX", path, True, True, False, model, "응답 형식 불일치", _truncate(response))

        return SmokeResult("CODEX", path, True, True, False, model, _classify_failure(output), output)
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude/Codex CLI 상태 점검")
    parser.add_argument(
        "--provider",
        choices=["all", "claude", "codex"],
        default="all",
        help="점검 대상 provider",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="실제 프롬프트를 보내는 live 점검까지 수행",
    )
    args = parser.parse_args()

    results: list[SmokeResult] = []
    if args.provider in ("all", "claude"):
        results.append(_claude_result(args.live))
    if args.provider in ("all", "codex"):
        results.append(_codex_result(args.live))

    print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
