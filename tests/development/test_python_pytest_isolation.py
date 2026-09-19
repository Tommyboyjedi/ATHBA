"""Real subprocess coverage for the harness/target pytest boundary."""
import json
from pathlib import Path

import pytest

from core.development.microcycle_domain import (
    FragmentationRequest, FrontierExecutionRequest, FrontierMaterialisationRequest,
    ScenarioFrontier, ScenarioParseRequest, TestScenarioDraft,
)
from core.development.python_pytest_adapter import PythonPytestAdapter


def execute_target(root, body="assert True"):
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("isolated", "readiness", "python", "def test_target():\n    " + body + "\n",
                              "tests/test_target.py::test_target", "tests/test_target.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    frontier = ScenarioFrontier(model.scenario_id, len(fragments) - 1, fragments[-1].fragment_id,
                                tuple(item.fragment_id for item in fragments))
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, "base"))
    return adapter.execute_frontier(FrontierExecutionRequest(artifact, str(root), draft.test_path))


def clear_harness_environment(monkeypatch):
    for name in ("DJANGO_SECRET_KEY", "DJANGO_SETTINGS_MODULE", "DJANGO_CONFIGURATION", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        monkeypatch.delenv(name, raising=False)


def test_non_django_target_ignores_ancestor_harness_configuration(tmp_path, monkeypatch):
    clear_harness_environment(monkeypatch)
    harness = tmp_path / "harness"
    target = harness / "state" / "target"
    target.mkdir(parents=True)
    (harness / "manage.py").write_text("# unrelated Django harness\n")
    (harness / "pytest.ini").write_text("[pytest]\nDJANGO_SETTINGS_MODULE = harness_settings\n")
    (harness / "harness_settings.py").write_text("raise RuntimeError('HARNESS_SETTINGS_LEAKED')\n")
    (harness / "conftest.py").write_text("raise RuntimeError('HARNESS_CONFTEST_LEAKED')\n")
    result = execute_target(target)
    assert result.kind == "green", result.to_dict()


@pytest.mark.parametrize("config_name,config_text", [
    ("pytest.ini", "[pytest]\naddopts = --strict-markers\nmarkers = target_marker: target only\n"),
    ("pyproject.toml", '[tool.pytest.ini_options]\naddopts = "--strict-markers"\nmarkers = ["target_marker: target only"]\n'),
])
def test_target_configuration_conftest_and_plugins_survive(tmp_path, monkeypatch, config_name, config_text):
    clear_harness_environment(monkeypatch)
    monkeypatch.setenv("PYTEST_ADDOPTS", "--host-option-that-must-not-leak")
    monkeypatch.setenv("PYTEST_PLUGINS", "host_plugin_that_must_not_load")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "athba.settings")
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "conftest.py").write_text("raise RuntimeError('OUTSIDE_CONFTEST')\n")
    (tmp_path / "manage.py").write_text("# ancestor Django project\n")
    (target / config_name).write_text(config_text)
    (target / "core").mkdir()
    (target / "core" / "__init__.py").write_text("value = 'target-package'\n")
    (target / "target_plugin.py").write_text('''import builtins
import pytest
@pytest.fixture(autouse=True)
def target_plugin_fixture():
    builtins.target_plugin_loaded = True
''')
    (target / "conftest.py").write_text('''import json, os, sys
from pathlib import Path
import pytest
pytest_plugins = ['target_plugin']
@pytest.fixture(autouse=True)
def target_fixture(pytestconfig):
    root = Path(__file__).parent
    assert pytestconfig.rootpath == root
    assert pytestconfig.inipath.parent == root
    assert pytestconfig.option.strict_markers
    assert pytestconfig.pluginmanager.hasplugin('django')
    assert 'DJANGO_SECRET_KEY' not in os.environ
    assert 'DJANGO_SETTINGS_MODULE' not in os.environ
    assert 'athba.settings' not in sys.modules
    Path('observed.json').write_text(json.dumps(dict(cwd=os.getcwd(), sys_path=sys.path,
        rootdir=str(pytestconfig.rootpath), config=str(pytestconfig.inipath),
        pythonpath=os.environ.get('PYTHONPATH'), django_plugin=True)))
''')
    result = execute_target(target, "assert __import__('builtins').target_plugin_loaded and __import__('core').value == 'target-package'")
    assert result.kind == "green", result.to_dict()
    observed = json.loads((target / "observed.json").read_text())
    harness = Path(__file__).resolve().parents[2]
    assert str(harness) not in observed["sys_path"]
    assert observed["pythonpath"] is None
    assert observed["cwd"] == str(target)


def test_target_declared_django_settings_are_preserved(tmp_path, monkeypatch):
    clear_harness_environment(monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    (target / "pytest.ini").write_text("[pytest]\nDJANGO_SETTINGS_MODULE = target_settings\n")
    (target / "manage.py").write_text("# legitimate target Django entry point\n")
    (target / "target_settings.py").write_text("INSTALLED_APPS = []\nDATABASES = {}\nTARGET_SETTING = 'target-only'\n")
    result = execute_target(target, "assert __import__('django.conf', fromlist=['settings']).settings.TARGET_SETTING == 'target-only'")
    assert result.kind == "green", result.to_dict()


def test_target_below_real_harness_without_config_or_django_secret(monkeypatch):
    from tempfile import TemporaryDirectory
    clear_harness_environment(monkeypatch)
    harness = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix="isolation-test-", dir=harness) as directory:
        target = Path(directory)
        (target / "conftest.py").write_text('''import os, sys
from pathlib import Path
import pytest
@pytest.fixture(autouse=True)
def check_boundary(pytestconfig):
    assert pytestconfig.rootpath == Path(__file__).parent
    assert pytestconfig.inipath == Path(os.devnull)
    assert pytestconfig.pluginmanager.hasplugin('django')
    assert 'DJANGO_SECRET_KEY' not in os.environ
    assert 'DJANGO_SETTINGS_MODULE' not in os.environ
    assert 'athba.settings' not in sys.modules
''')
        result = execute_target(target)
        assert result.kind == "green", result.to_dict()
