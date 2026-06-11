# 2026-06-12 서버 다운타임 인시던트 기록

## 요약

- **영향**: 2026-06-10 저녁 ~ 2026-06-12 08:20 (약 1.5거래일) 트레이딩 서버 완전 정지.
  6/11 장 전체가 서버 없이 지나감 — 보유 포지션 손절/익절 가드, 스케줄러, 뉴스 폴링 전부 미작동.
- **원인**: 코드 결함·크래시·재부팅 아님. 6/10 horizon 검증 작업 중 반복 재시작(12:58/15:43/17:05)
  후 마지막 종료 상태에서 **재기동을 잊음**. 종료 로그가 없고(`start.sh stop`은 SIGTERM→KILL만 수행)
  외부 알림이 없어 이틀간 인지하지 못함.
- **복구**: 6/12 08:20 `bash start.sh -d` 재기동. health/시스템 상태/무결성 게이트
  (`check_runtime_integrity.py --days 7`) 전부 OK. 브로커-DB 대사 불일치 0건.

## 조사 근거

- 마지막 로그: `runtime/logs/momo-trading.log` 2026-06-10 17:05:45 (정상 기동 직후 침묵)
- 재부팅 없음: uptime 9일 (6/3 부팅)
- 크래시 리포트 없음: `~/Library/Logs/DiagnosticReports`에 python 항목 없음
- `.venv313` 정상 (루트의 깨진 `venv/`는 실행 경로와 무관 — start.sh는 `.venv313` 사용)
- 6/10 21:38 PID 파일 갱신 = `start.sh status`의 stale PID 복구 흔적 → 그 시점까진 가동 중

## 재발 방지 조치 (미적용 — 후속 태스크 대상)

[2026-06-11 개선 로드맵](2026-06-11-service-improvement-roadmap.md)의 해당 항목과 동일하며,
이 인시던트가 실증 사례다:

1. **O1 외부 알림**: 서버 다운/킬스위치/체결 실패를 Telegram·Slack 웹훅으로 통지.
   "이틀간 아무도 모름"을 구조적으로 차단하는 최우선 조치.
2. **O3 자동 재시작**: launchd KeepAlive 적용. 단, 수동 `start.sh stop`과 충돌하므로
   stop을 `launchctl bootout`과 통합하는 설계 필요 (즉흥 적용 금지).
3. **종료 로그**: `scripts/dev/start.sh`의 `stop_momo_processes`에 종료 시각/사유 로깅 추가.
   이번 조사에서 종료 시점을 특정하지 못한 직접 원인.
4. (보조) 장 시작 전 health 자가점검: pre-market 시간대에 서버 미기동이면 알림 — O1에 포함 가능.

## 운영 메모

- 재기동 시점 설정: `TRADING_ENABLED=true, AUTONOMOUS, FULL` — 재기동이 곧 실주문 재개임을 유의.
- 장기 다운 후 재기동 시에는 반드시 `check_runtime_integrity.py`로 브로커-DB 대사를 확인할 것
  (이번에는 불일치 0건이었음).
