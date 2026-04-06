# 2026-04-06 거래 기준선 리셋

## 왜 리셋이 필요한가
- 한 컴퓨터에서 관리하던 로컬 DB(`runtime/data/app.db`)가 다른 컴퓨터로 작업을 옮기는 과정에서 유실되거나 일부만 남은 것으로 보인다.
- 실계좌 보유/미체결은 브로커 응답에 남아 있지만, `trade_results` 기반 진입/청산 이력은 중간부터 끊겨 있다.
- 그 결과 `SELL` 체결은 일부 존재해도, 대응되는 `BUY` 진입 lot가 없어 실현손익/매도 횟수/성과 분석이 0 또는 왜곡된 값으로 보인다.

## 현재 어떤 값을 신뢰할지
- 현재 보유 종목/수량: 브로커 응답 기준
- 현재 미체결 주문: 브로커 응답 기준
- 현재 총자산/현금/주식평가: 브로커 응답 기준
  - 단, 키움 응답에서 `총자산 < 주식평가액`이 들어오면 애플리케이션에서 방어적으로 보정한다.
- 과거 실현손익/매도 완료 건수/성과 분석: 기존 로컬 DB는 완전한 진실 원본으로 보지 않는다.

## 2026-04-06 기준 복구 상태
- `049080`
  - 계좌 보유수량 기준으로 누락된 열린 `BUY` lot를 백필 완료
- `001250`
  - `PENDING_CONFIRM` 1건을 `CONFIRMED`로 복구
  - 이후 부족 수량을 계좌 평균단가 기준으로 백필 완료
- `093370`
  - `PENDING_CONFIRM` 주문이 실제 미체결로 남아 있어 자동 백필 보류
- `215790`
  - `PENDING_CONFIRM` 주문이 실제 미체결로 남아 있어 자동 백필 보류

## 지금부터의 운영 원칙
- 오늘 이후의 운영 기준선은 "현재 브로커 계좌 상태 + 복구된 열린 BUY lot"로 본다.
- 과거 손익을 무리하게 재구성하지 않는다.
- 향후 성과 지표는 이 기준선 이후 누적 데이터부터 신뢰한다.
- 이미 끝난 과거 매도 건은 옛 DB나 외부 거래내역이 없는 한 완전 복구 대상으로 보지 않는다.

## 운영 절차
1. 서버 재시작 후 `/api/v1/admin/account/balance`, `/api/v1/admin/account/holdings`를 다시 확인한다.
2. `PENDING_CONFIRM`가 남아 있으면 먼저 수동 복구를 돌린다.
   - `POST /api/v1/admin/trades/reconcile-pending`
3. 보유수량과 DB 열린 `BUY` lot가 다르면 보유 정합성 복구를 돌린다.
   - `POST /api/v1/admin/trades/reconcile-holdings`
   - 또는 시스템 설정 탭의 `DB 초기화` 버튼으로 운영 이력을 비운 뒤 기준선을 다시 만든다.
   - API: `POST /api/v1/admin/system/reset-operational-baseline`
4. 장중에는 미체결이 존재할 수 있으므로 `PENDING_CONFIRM` 종목은 즉시 백필하지 않는다.
5. 당일 장 종료 후 다시 한 번 `reconcile-pending -> reconcile-holdings` 순서로 점검한다.

## 남아 있는 한계
- 과거 `SELL` 체결 중 대응 `BUY` lot가 사라진 건은 실현손익이 자동 복구되지 않는다.
- 주간/월간 성과 분석은 기준선 리셋 이전 데이터가 섞여 있으면 왜곡될 수 있다.
- 성과/뉴스 화면에는 "기준선 리셋 이후 데이터" 배지를 추가했지만, 과거 리포트 아카이브는 여전히 과거 DB 상태 영향을 받을 수 있다.

## 권장 후속 작업
- [x] `runtime/data/app.db` 백업 루틴 정리
  - 시스템 설정 탭의 `DB 백업` 버튼 추가
  - API: `POST /api/v1/admin/system/backup-operational-db`
  - `DB 초기화` 실행 전 현재 DB 백업 파일을 자동 생성
- [ ] 다른 컴퓨터 이동 전/후 DB 백업 복원 절차 문서화
- [x] 종료 전 자동 백업 경로 추가
  - `bash start.sh stop --backup`
  - 또는 `MOMO_AUTO_BACKUP_ON_STOP=1 bash start.sh stop`
- [ ] 최소 일 1회 자동 백업 여부 검토
