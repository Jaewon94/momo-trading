from pathlib import Path

from strategy.policy.registry import POLICY_REGISTRY, registry_by_owner, render_policy_registry_markdown
from strategy.policy.settings_catalog import POLICY_SETTINGS_CATALOG


def test_policy_registry_priorities_are_unique_and_sorted() -> None:
    priorities = [entry.priority for entry in POLICY_REGISTRY]

    assert priorities == sorted(priorities)
    assert len(priorities) == len(set(priorities))


def test_policy_registry_covers_settings_catalog_owners() -> None:
    registry_owners = set(registry_by_owner())
    catalog_owners = {item.owner for item in POLICY_SETTINGS_CATALOG.values()}

    assert catalog_owners <= registry_owners


def test_policy_registry_required_tests_exist() -> None:
    root = Path(__file__).resolve().parents[3]

    for entry in POLICY_REGISTRY:
        assert entry.required_tests, entry.owner
        for test_path in entry.required_tests:
            assert (root / test_path).exists(), f"{entry.owner}: missing {test_path}"


def test_policy_registry_governance_docs_are_in_sync() -> None:
    root = Path(__file__).resolve().parents[3]
    doc = (root / "docs/architecture/trading-policy-governance.md").read_text(encoding="utf-8")
    start = "<!-- POLICY_REGISTRY_START -->"
    end = "<!-- POLICY_REGISTRY_END -->"

    assert start in doc
    assert end in doc
    section = doc.split(start, 1)[1].split(end, 1)[0].strip()

    assert section == render_policy_registry_markdown().strip()
