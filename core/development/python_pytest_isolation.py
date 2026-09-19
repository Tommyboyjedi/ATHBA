"""Scope pytest discovery to a target after importing the probe implementation."""
from __future__ import annotations

import os
from pathlib import Path
import sys

# These configure the hosting pytest process, not the target's declared config.
HOST_PYTEST_ENVIRONMENT = (
    "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "DJANGO_SETTINGS_MODULE", "DJANGO_CONFIGURATION",
)
PYTEST_CONFIG_NAMES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


class TargetPytestEnvironment:
    """Retain the runtime and target while removing harness discovery inputs."""

    def prepare(self, root: Path) -> None:
        harness = Path(__file__).resolve().parents[2]
        # Resolve the old empty sys.path entry before changing cwd.
        paths = [str(Path(entry).resolve()) for entry in sys.path if Path(entry).resolve() != harness]
        os.chdir(root)
        sys.path[:] = [str(root), *(entry for entry in paths if entry and Path(entry).resolve() != root)]
        bootstrap = os.environ.get("PYTHONPATH", "").split(os.pathsep)
        retained = [entry for entry in bootstrap if entry and Path(entry).resolve() != harness]
        if retained:
            os.environ["PYTHONPATH"] = os.pathsep.join(retained)
        else:
            os.environ.pop("PYTHONPATH", None)
        for name in HOST_PYTEST_ENVIRONMENT:
            os.environ.pop(name, None)
        # Already-imported probe collaborators remain referenced by the probe;
        # their package paths must not expose other harness application modules.
        for name in tuple(sys.modules):
            if name == "core" or name.startswith("core."):
                del sys.modules[name]

    def arguments(self, root: Path, node: str) -> list[str]:
        from _pytest.config.findpaths import load_config_dict_from_file

        target_file = (root / node.split("::", 1)[0]).resolve()
        if not target_file.is_relative_to(root):
            raise ValueError("pytest node must be inside the target project")
        config: Path | None = None
        fallback: Path | None = None
        directory = target_file.parent
        while directory.is_relative_to(root):
            for name in PYTEST_CONFIG_NAMES:
                candidate = directory / name
                if candidate.is_file():
                    if load_config_dict_from_file(candidate) is not None:
                        config = candidate
                        break
                    if fallback is None and name == "pyproject.toml":
                        fallback = candidate
            if config is not None or directory == root:
                break
            directory = directory.parent
        # An explicit empty config prevents pytest searching above the target.
        selected = str(config or fallback or os.devnull)
        options = load_config_dict_from_file(config) if config is not None else {}
        find_project = str((options or {}).get("django_find_project", "true")).lower()
        if find_project not in ("false", "0"):
            self._django_project_path(root, target_file)
        return ["-q", "-p", "no:cacheprovider", "-c", selected,
                f"--rootdir={root}", f"--confcutdir={root}",
                "-o", "django_find_project=false", node]

    @staticmethod
    def _django_project_path(root: Path, target_file: Path) -> None:
        # pytest-django's own scan ignores rootdir/confcutdir and ascends to '/'.
        # Supply its import-path convenience only for a manage.py inside target.
        for directory in (*target_file.parents, root):
            if directory.is_relative_to(root) and (directory / "manage.py").is_file():
                sys.path.insert(0, str(directory))
                break
