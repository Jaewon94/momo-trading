#!/usr/bin/env python3
"""Guard risky git commands and obvious secret leaks."""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_BRANCHES = {"main", "master", "dev", "develop"}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    "htmlcov",
}
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".toml", ".sh", ".js", ".ts", ".env.example"}
TEXT_NAMES = {"AGENTS.md", "README.md", ".env.example"}


@dataclass(frozen=True)
class GuardResult:
    status: str
    message: str
    exit_code: int


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b")),
    ("password_assignment", re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"]?([^'\"\s]{12,})")),
)


def branch_name(ref: str) -> str:
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    if ":" in ref:
        return branch_name(ref.rsplit(":", 1)[1])
    return ref


def is_protected_ref(ref: str) -> bool:
    return branch_name(ref) in PROTECTED_BRANCHES


def command_tokens(command: str) -> list[str]:
    return shlex.split(command)


def has_force_flag(tokens: list[str]) -> bool:
    return any(token in {"--force", "-f"} or token.startswith("--force-with-lease") for token in tokens)


def push_refs(tokens: list[str]) -> list[str]:
    refs: list[str] = []
    seen_remote = False
    for token in tokens[2:]:
        if token.startswith("-"):
            continue
        if not seen_remote:
            seen_remote = True
            continue
        refs.append(token)
    return refs


def check_command(command: str) -> GuardResult:
    try:
        tokens = command_tokens(command)
    except ValueError as exc:
        return GuardResult("blocked", f"command parse failed: {exc}", 2)

    if len(tokens) < 2 or tokens[0] != "git":
        return GuardResult("allowed", "not a guarded git command", 0)

    action = tokens[1]
    if action == "commit":
        return GuardResult("ask", "git commit requires explicit user confirmation", 1)
    if action != "push":
        return GuardResult("allowed", "git command is not guarded", 0)

    force = has_force_flag(tokens)
    protected = any(is_protected_ref(ref) for ref in push_refs(tokens))
    if force and protected:
        return GuardResult("blocked", "force push to protected branch is blocked", 2)
    if force:
        return GuardResult("ask", "force push requires explicit user confirmation", 1)
    return GuardResult("ask", "git push requires separate explicit user confirmation", 1)


def should_skip(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return any(part in SKIP_DIRS or part.startswith(".venv") for part in rel_parts)


def candidate_files(paths: list[Path], root: Path) -> list[Path]:
    candidates = paths or [path for path in root.rglob("*") if path.is_file()]
    output: list[Path] = []
    for path in candidates:
        path = path if path.is_absolute() else root / path
        if not path.exists() or not path.is_file() or should_skip(path, root):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            output.append(path)
    return output


def line_is_placeholder(line: str) -> bool:
    lowered = line.casefold()
    return any(marker in lowered for marker in ("placeholder", "example", "your_", "dummy", "redacted", "not-a-real"))


def scan_secrets(paths: list[Path], root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in candidate_files(paths, root):
        rel = path.relative_to(root)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append(f"{rel}: read failed: {exc}")
            continue
        for line_no, line in enumerate(lines, start=1):
            if line_is_placeholder(line):
                continue
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{rel}:{line_no}: possible {name}")
    return findings


def is_non_fast_forward(local_sha: str, remote_sha: str, root: Path = ROOT) -> bool:
    if set(remote_sha) == {"0"}:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode != 0


def check_pre_push(stdin: str, root: Path = ROOT) -> GuardResult:
    for raw_line in stdin.splitlines():
        parts = raw_line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if local_ref == "(delete)" or set(local_sha) == {"0"}:
            if is_protected_ref(remote_ref):
                return GuardResult("blocked", "deleting protected branch is blocked", 2)
            return GuardResult("ask", "branch deletion requires explicit user confirmation", 1)
        if is_protected_ref(remote_ref) and is_non_fast_forward(local_sha, remote_sha, root):
            return GuardResult("blocked", "non-fast-forward update to protected branch is blocked", 2)
    return GuardResult("allowed", "pre-push guard passed", 0)


def print_result(result: GuardResult) -> int:
    stream = sys.stderr if result.exit_code else sys.stdout
    print(f"{result.status}: {result.message}", file=stream)
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    check = subparsers.add_parser("check-command", help="Classify a command string")
    check.add_argument("--command", dest="command_text", required=True)

    scan = subparsers.add_parser("scan-secrets", help="Scan files for obvious secret patterns")
    scan.add_argument("paths", nargs="*", type=Path)

    subparsers.add_parser("pre-push", help="Read git pre-push stdin and enforce protected refs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.subcommand == "check-command":
        return print_result(check_command(args.command_text))
    if args.subcommand == "scan-secrets":
        findings = scan_secrets(args.paths, root=root)
        if findings:
            for finding in findings:
                print(finding, file=sys.stderr)
            return 2
        print("secret scan passed")
        return 0
    if args.subcommand == "pre-push":
        return print_result(check_pre_push(sys.stdin.read(), root=root))
    return 2


if __name__ == "__main__":
    sys.exit(main())
