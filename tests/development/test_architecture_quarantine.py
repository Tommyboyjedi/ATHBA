from pathlib import Path


MODERN_ROOTS = (Path("core/development"), Path("core/execution"))
MODERN_ENTRYPOINTS = (
    Path("scripts/run_pr17_independent_reservation_book.py"),
    Path("scripts/run_pr19_environment_proof.py"),
)
FORBIDDEN_IMPORT_MARKERS = (
    "from llm_service",
    "import llm_service",
    "from core.services.git_service",
    "from core.services.test_execution_service",
    "from core.agents.helpers.llm_exchange",
    "/tmp/athba_repos",
)


def python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def assert_modern_source_is_clean(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for marker in FORBIDDEN_IMPORT_MARKERS:
        assert marker not in source, f"{path} still depends on legacy marker {marker!r}"


def test_modern_development_and_execution_modules_do_not_import_legacy_control_plane():
    for root in MODERN_ROOTS:
        for path in python_files(root):
            assert_modern_source_is_clean(path)



def test_pr17_and_pr19_entrypoints_do_not_depend_on_legacy_local_stack():
    for path in MODERN_ENTRYPOINTS:
        assert_modern_source_is_clean(path)
