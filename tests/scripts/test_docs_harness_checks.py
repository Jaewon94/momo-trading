import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_CHECK = REPO_ROOT / "scripts" / "check_docs_consistency.py"
LINK_CHECK = REPO_ROOT / "scripts" / "check_markdown_links.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_docs_consistency_accepts_current_repo() -> None:
    module = _load_module("check_docs_consistency", DOCS_CHECK)

    findings = module.check_docs(REPO_ROOT)

    assert findings == []


def test_markdown_link_check_detects_missing_local_link(tmp_path: Path) -> None:
    module = _load_module("check_markdown_links", LINK_CHECK)
    doc = tmp_path / "README.md"
    doc.write_text("[missing](docs/missing.md)\n", encoding="utf-8")

    findings = module.check_links(tmp_path, [doc])

    assert findings == ["README.md: missing local link target: docs/missing.md"]


def test_markdown_link_check_ignores_external_links(tmp_path: Path) -> None:
    module = _load_module("check_markdown_links", LINK_CHECK)
    doc = tmp_path / "README.md"
    doc.write_text("[external](https://example.com)\n", encoding="utf-8")

    findings = module.check_links(tmp_path, [doc])

    assert findings == []
