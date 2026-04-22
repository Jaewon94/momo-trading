from tools.llm_cli_smoke import _classify_failure


def test_classify_failure_detects_login_issue() -> None:
    assert _classify_failure("Not logged in · Please run /login") == "로그인 필요"


def test_classify_failure_detects_network_issue() -> None:
    output = "failed to lookup address information: nodename nor servname provided, or not known"
    assert _classify_failure(output) == "네트워크/DNS 접근 불가"


def test_classify_failure_detects_permission_issue() -> None:
    assert _classify_failure("Operation not permitted") == "로컬 권한 또는 샌드박스 제약"
