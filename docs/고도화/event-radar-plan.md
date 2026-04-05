# Event Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 화면에 실시간 이벤트 레이더를 추가해 급등락/거래량/손절/익절 신호를 우선순위 있게 보여준다.

**Architecture:** `realtime.event_detector`가 최근 이벤트 메모리 스냅샷을 유지하고, 관리자 API가 이를 전용 응답으로 노출한다. 프런트는 새 상태 모듈로 이벤트를 점수/상태 중심 뷰모델로 변환한 뒤 메인 패널 상단의 레이더 UI와 종목 상세 모달의 최근 이벤트 스트립에 렌더링한다.

**Tech Stack:** FastAPI, in-memory event state, vanilla JS modules, Vitest, Pytest

---

### 파일 구조

**Create**
- `docs/고도화/event-radar-spec.md`
- `docs/고도화/event-radar-plan.md`
- `admin/static/js/event_radar_state.js`
- `tests/frontend/test_event_radar_state.test.js`
- `tests/api/test_admin_event_radar_routes.py`

**Modify**
- `realtime/event_detector.py`
- `api/routes/admin.py`
- `admin/static/index.html`
- `admin/static/js/app.js`

---

### Task 1: 이벤트 스냅샷 API TDD

**Files:**
- Modify: `realtime/event_detector.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_event_radar_routes.py`

- [ ] **Step 1: 실패 테스트 작성**

`GET /api/v1/admin/events/radar`가 요약과 이벤트 리스트를 반환하는 테스트를 작성한다.

- [ ] **Step 2: 테스트가 올바르게 실패하는지 확인**

Run: `pytest tests/api/test_admin_event_radar_routes.py -q`
Expected: route missing 또는 payload mismatch로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`event_detector`에 최근 이벤트 스냅샷 메모리와 `build_radar_snapshot()`를 추가하고, 관리자 API에 엔드포인트를 붙인다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/api/test_admin_event_radar_routes.py -q`
Expected: PASS

---

### Task 2: 이벤트 레이더 프런트 상태 TDD

**Files:**
- Create: `admin/static/js/event_radar_state.js`
- Test: `tests/frontend/test_event_radar_state.test.js`

- [ ] **Step 1: 실패 테스트 작성**

이벤트 레이더 뷰모델이 점수, 상태 라벨, 필터 카운트를 만드는 테스트를 작성한다.

- [ ] **Step 2: 테스트가 올바르게 실패하는지 확인**

Run: `npm run test:ui -- tests/frontend/test_event_radar_state.test.js`
Expected: module missing 또는 function missing으로 FAIL

- [ ] **Step 3: 최소 구현 작성**

이벤트 응답을 카드/필터/요약 바용 데이터로 바꾸는 함수들을 만든다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `npm run test:ui -- tests/frontend/test_event_radar_state.test.js`
Expected: PASS

---

### Task 3: 관리자 UI 렌더링

**Files:**
- Modify: `admin/static/index.html`
- Modify: `admin/static/js/app.js`
- Modify: `admin/static/js/event_radar_state.js`

- [ ] **Step 1: 레이아웃 삽입**

메인 패널 상단에 `Event Radar` 섹션과 필터 행, 리스트 컨테이너를 추가한다.

- [ ] **Step 2: 스타일 구현**

상태 배지, 점수 배지, 방향별 카드 톤, 쿨다운 표기를 추가한다.

- [ ] **Step 3: 데이터 로드 연결**

주기적 refresh와 SSE 활동 갱신 흐름에 맞춰 레이더 데이터도 다시 불러온다.

- [ ] **Step 4: 종목 상세 모달 연결**

종목 상세 모달 상단에 최근 이벤트 스트립을 연결한다.

---

### Task 4: 통합 검증

**Files:**
- Test: `tests/api/test_admin_event_radar_routes.py`
- Test: `tests/frontend/test_event_radar_state.test.js`
- Test: `tests/frontend/test_activity_state.test.js`
- Test: `tests/frontend/test_position_detail_state.test.js`

- [ ] **Step 1: API 테스트 실행**

Run: `pytest tests/api/test_admin_event_radar_routes.py -q`

- [ ] **Step 2: 프런트 테스트 실행**

Run: `npm run test:ui -- tests/frontend/test_event_radar_state.test.js tests/frontend/test_activity_state.test.js tests/frontend/test_position_detail_state.test.js`

- [ ] **Step 3: 수동 확인**

`/admin`에서 이벤트 레이더가 상단에 보이고, 필터가 동작하며, 종목 상세 모달에 최근 이벤트 스트립이 보이는지 확인한다.

- [ ] **Step 4: 커밋**

추천 메시지:

```bash
git add docs/고도화/event-radar-spec.md docs/고도화/event-radar-plan.md realtime/event_detector.py api/routes/admin.py admin/static/index.html admin/static/js/app.js admin/static/js/event_radar_state.js tests/api/test_admin_event_radar_routes.py tests/frontend/test_event_radar_state.test.js
git commit -m "이벤트 레이더와 운영 이벤트 가시성 추가"
```
