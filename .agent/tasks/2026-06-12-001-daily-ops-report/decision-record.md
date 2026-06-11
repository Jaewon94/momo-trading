# Decision Record

## Decision

1. 기존 집계 서비스(observability_reporting, news_reporting, TradeResultRepository, AgentActivityRepository)를 재사용해 데이터 수집은 결정론으로, 해설만 LLM(generate_manual)로 분리한다.
2. 섹션별 독립 수집(_collect_section try/except) — 한 섹션 실패가 리포트 전체를 막지 않고 error 필드 + alert 플래그로 표면화된다.
3. LLM 코멘터리는 4개 고정 소제목(운영 요약 / 병목·이상 / 개선 제안 / 적용 검토할 신기능)을 강제하고, 실패 시 None으로 리포트는 계속 생성된다.
4. 잡 시각은 평일 16:40 — post_market(15:40) → portfolio_sync(16:00) → calibration(금 16:10) → market_data(16:30) 이후 모든 하루치 데이터가 정리된 시점.
5. 산출물은 weekly_review와 동일하게 runtime/reports/에 daily_ops_<YYYYMMDD>.{json,md}로 보관. 전일 JSON을 읽어 delta를 계산한다.

## Rationale

- 운영자가 매일 읽는 문서이므로 사람용 Markdown(표/플래그/이모지)을 1급 산출물로 두고, JSON은 추이 분석/델타용 기계 포맷으로 분리.
- success_rate가 0~100 퍼센트, provider_breakdown/by_reason이 리스트라는 observability 실제 반환 형태를 확인 후 렌더링을 맞춤 (가정 코딩으로 인한 표시 버그 2건 사전 수정).
- errors.recent(24h)만 보면 미해결 인시던트를 놓침 — 실DB 검증에서 발견해 incident_count 플래그 추가.

## Deferred

- 외부 알림(텔레그램 등)으로 리포트 발송 — 로드맵 O1과 함께 진행.
- runtime_settings(MUTABLE_SETTINGS) 등록 — 현재는 .env/기본값으로 충분, admin UI 토글 필요 시 추가.
- 리포트 N일 보존 정책 — 파일이 누적되면 observability_maintenance에 정리 추가.

## Risks

- LLM 코멘터리 품질은 manual provider 체인에 의존 (검증 시 OLLAMA 폴백 사용됨). 부정확한 해설 가능성 있으므로 수치는 결정론 섹션이 기준.
- 잡 실패는 로그로만 남음 (스케줄러를 막지 않도록 광역 캐치) — 알림 채널 도입 전까지는 리포트 부재가 곧 신호.
