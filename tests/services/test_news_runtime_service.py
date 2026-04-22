from services.news_runtime_service import NewsRuntimeService


def test_news_runtime_service_tracks_source_result_and_overall_status():
    service = NewsRuntimeService()

    service.record_source_result(
        "DART",
        status="SUCCESS",
        mode="AUTO_OFF_HOURS",
        message="장외 폴링 정상",
        counts={"received": 3, "created": 2, "duplicates": 1, "skipped": 0},
    )

    snapshot = service.get_snapshot(include_foreign=True)

    assert snapshot["overall"]["last_status"] == "SUCCESS"
    assert snapshot["overall"]["last_mode"] == "AUTO_OFF_HOURS"
    assert snapshot["overall"]["last_message"] == "장외 폴링 정상"
    assert snapshot["overall"]["last_success_at"] is not None
    assert snapshot["sources"]["DART"]["status"] == "SUCCESS"
    assert snapshot["sources"]["DART"]["counts"]["created"] == 2
    assert snapshot["sources"]["KRX"]["status"] == "IDLE"


def test_news_runtime_service_marks_empty_results_without_treating_them_as_failure():
    service = NewsRuntimeService()

    service.record_source_result(
        "DART",
        status="EMPTY",
        mode="MANUAL",
        message="조회된 데이터 없음",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
    )

    snapshot = service.get_snapshot(include_foreign=False)

    assert snapshot["overall"]["last_status"] == "EMPTY"
    assert snapshot["overall"]["last_mode"] == "MANUAL"
    assert snapshot["overall"]["last_message"] == "조회된 데이터 없음"
    assert snapshot["overall"]["last_success_at"] is None
    assert set(snapshot["sources"].keys()) == {"DART", "KRX", "YONHAP"}
    assert snapshot["sources"]["DART"]["counts"]["received"] == 0


def test_news_runtime_service_includes_bloomberg_when_foreign_sources_enabled():
    service = NewsRuntimeService()

    snapshot = service.get_snapshot(include_foreign=True)

    assert "BLOOMBERG" in snapshot["sources"]
    assert snapshot["sources"]["BLOOMBERG"]["implemented"] is True


def test_news_runtime_service_tracks_source_success_and_failure_streaks():
    service = NewsRuntimeService()

    service.record_source_result(
        "DART",
        status="ERROR",
        mode="AUTO_TRADING",
        message="타임아웃",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
    )
    service.record_source_result(
        "DART",
        status="ERROR",
        mode="AUTO_TRADING",
        message="재시도 실패",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
    )
    service.record_source_result(
        "DART",
        status="SUCCESS",
        mode="AUTO_OFF_HOURS",
        message="신규 2건 적재",
        counts={"received": 3, "created": 2, "duplicates": 1, "skipped": 0},
    )

    snapshot = service.get_snapshot(include_foreign=False)
    source = snapshot["sources"]["DART"]

    assert source["last_success_at"] is not None
    assert source["last_error_at"] is not None
    assert source["consecutive_failures"] == 0
    assert source["counts"]["created"] == 2


def test_news_runtime_service_can_record_overall_result_without_source_override():
    service = NewsRuntimeService()

    service.record_source_result(
        "DART",
        status="ERROR",
        mode="AUTO_TRADING",
        message="타임아웃",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
        update_overall=False,
    )
    service.record_overall_result(
        status="PARTIAL_ERROR",
        mode="AUTO_TRADING",
        message="일부 소스 실패 · 신규 0건 · 중복 3건 · 스킵 0건 · 오류 1건",
    )

    snapshot = service.get_snapshot(include_foreign=False)

    assert snapshot["overall"]["last_status"] == "PARTIAL_ERROR"
    assert snapshot["overall"]["last_message"].startswith("일부 소스 실패")
    assert snapshot["sources"]["DART"]["status"] == "ERROR"


def test_news_runtime_service_marks_source_cooldown_when_failures_repeat(monkeypatch):
    service = NewsRuntimeService()
    monkeypatch.setattr("services.news_runtime_service.settings.NEWS_SOURCE_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr("services.news_runtime_service.settings.NEWS_SOURCE_FAILURE_COOLDOWN_MIN", 30)

    service.record_source_result(
        "INVESTING",
        status="ERROR",
        mode="AUTO_EVENT",
        message="dns fail",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
        update_overall=False,
    )
    service.record_source_result(
        "INVESTING",
        status="ERROR",
        mode="AUTO_EVENT",
        message="dns fail",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
        update_overall=False,
    )

    snapshot = service.get_snapshot(include_foreign=True)
    source = snapshot["sources"]["INVESTING"]

    assert source["cooldown_active"] is True
    assert int(source["cooldown_remaining_sec"]) > 0
    assert source["cooldown_until"] is not None
