#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

.venv313/bin/python -m pytest tests/ -q \
  --cov=agent.trading_agent \
  --cov=scheduler.scheduler \
  --cov=agent.decision_maker \
  --cov=api.routes.admin \
  --cov-report=term-missing \
  --cov-fail-under=20
