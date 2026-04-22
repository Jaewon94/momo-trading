# 2026-04-06 운영 DB 백업 / 복원 런북

## 목적
- 다른 컴퓨터로 작업 환경을 옮길 때 `runtime/data/app.db` 유실이나 정합성 꼬임을 줄인다.
- 기준선 리셋이 필요한 경우에도 직전 운영 상태를 백업 파일로 남긴다.

## 기본 원칙
- 실계좌 보유/미체결/잔고는 브로커 응답이 진실 원본이다.
- `runtime/data/app.db`는 운영 이력, 리포트, 뉴스 적재, 거래 근거를 보존하는 로컬 상태 저장소다.
- 다른 컴퓨터에서 이어서 작업할 때는 먼저 DB 백업을 복원하고, 그다음 서버를 실행한다.
- 과거 이력이 필요 없으면 `DB 초기화`로 새 기준선을 만들 수 있지만, 그 전에 백업은 항상 남긴다.

## 백업 방법
### 관리자 UI
1. `/admin` 접속
2. `설정` → `시스템` 탭 이동
3. `운영 DB 백업` 카드의 `DB 백업` 버튼 클릭
4. 백업 파일 생성 위치 확인
   - 기본 위치: `runtime/backups/db`

### API
- `POST /api/v1/admin/system/backup-operational-db`

## 복원 방법
1. 서버를 중지한다.
2. 백업 파일을 새 컴퓨터의 프로젝트 아래로 복사한다.
3. 백업 파일을 `runtime/data/app.db`로 덮어쓴다.
4. 서버를 다시 시작한다.
5. 아래 API로 상태를 확인한다.
   - `/api/v1/admin/account/balance`
   - `/api/v1/admin/account/holdings`
   - `/api/v1/admin/news/overview`

## 새 기준선으로 다시 시작할 때
1. 먼저 `DB 백업` 버튼 또는 백업 API로 스냅샷을 남긴다.
2. `DB 초기화` 버튼을 실행한다.
   - API: `POST /api/v1/admin/system/reset-operational-baseline`
3. 초기화 API는 실행 직전 `before-reset` 백업을 자동 생성한다.
4. 초기화 후 현재 브로커 보유 기준으로 열린 `BUY` lot를 다시 구성한다.

## 이동 전 체크리스트
- `.env`가 현재 컴퓨터 기준으로 맞는지 확인
- `runtime/backups/db`에 최신 백업이 있는지 확인
- `PENDING_CONFIRM`가 많으면 이동 전에 한 번 정리
  - `POST /api/v1/admin/trades/reconcile-pending`
- 필요한 경우 보유 정합성도 한 번 정리
  - `POST /api/v1/admin/trades/reconcile-holdings`

## 이동 후 체크리스트
- 복원한 `app.db`가 최신 백업인지 확인
- `/api/v1/admin/account/holdings`와 관리자 화면 보유 종목이 일치하는지 확인
- 성과/뉴스 화면에 `기준선 리셋 이후 데이터` 배지가 필요 이상으로 보이지 않는지 확인
- 이력이 불완전하다고 판단되면 백업을 보관한 채 `DB 초기화`로 새 기준선을 시작
