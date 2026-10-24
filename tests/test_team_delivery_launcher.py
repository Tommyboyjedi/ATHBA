"""CLI opt-in routing only: controlled services, no backend/models/reservations."""
from dataclasses import dataclass
import json
from types import SimpleNamespace

import pytest

from core.delivery_management.domain import DeliveryPhase
from core.delivery_management.service import DispatchResult
from core.project_setup.fixture import fixture_specification
from core.project_setup.records import SetupStatus
from scripts import run_approved_project_campaign as launcher


@dataclass(frozen=True)
class ControlledBranch:
    id: str
    phase: DeliveryPhase = DeliveryPhase.COMPLETE


class ControlledDeliveries:
    def __init__(self):
        self.prepared = []
        self.dispatched = []

    async def prepare(self, request):
        self.prepared.append(request.behavior_id)
        return ControlledBranch(request.behavior_id)

    async def dispatch_ready(self, requests):
        self.dispatched.append(tuple(item.behavior_id for item in requests))
        return tuple(DispatchResult(item.behavior_id, ControlledBranch(item.behavior_id)) for item in requests)

    def inspect(self, project_id):
        return {"project_id": project_id, "main_unchanged": True}


@pytest.mark.asyncio
async def test_launcher_keeps_default_dry_run_and_explicit_live_uses_standard_concurrent_path(tmp_path, monkeypatch):
    identity = "507f1f77bcf86cd799439011"
    setup = SimpleNamespace(status=SetupStatus.READY, to_dict=lambda: {"status": "ready"})
    prepared = []
    async def prepare(handoff):
        prepared.append(handoff.decision.project_id)
        return setup
    deliveries = ControlledDeliveries()
    app = SimpleNamespace(records=SimpleNamespace(load=lambda project_id: setup),
                          setup=SimpleNamespace(prepare=prepare), deliveries=deliveries)
    async def backend(project_id):
        specification = {"version": 1, "content": fixture_specification(launcher.FIXTURE_DIRECTORY)}
        return object(), SimpleNamespace(id=project_id), specification
    monkeypatch.setattr(launcher, "_backend_lookup", backend)
    monkeypatch.setattr(launcher, "compose_project_setup", lambda request: app)
    def arguments(name, **flags):
        return launcher.CampaignArguments(identity, tmp_path / "state", tmp_path / name, **flags)
    assert await launcher.execute(arguments("dry")) == launcher.EXIT_READY
    assert not prepared and not deliveries.prepared and not deliveries.dispatched
    assert await launcher.execute(arguments("prepare", prepare=True)) == launcher.EXIT_READY
    assert prepared == [identity]
    assert deliveries.prepared == ["catalogue", "basket", "orders"]
    assert not deliveries.dispatched
    assert await launcher.execute(arguments("explicit", enable_live=True)) == launcher.EXIT_READY
    assert deliveries.dispatched == [("catalogue", "basket", "orders")]
    report = json.loads(next((tmp_path / "explicit").glob("campaign-*.json")).read_text())
    assert report["status"] == "branches_complete_not_integrated"
    assert report["application_main_integration_requested"] is False
    assert report["model_interactions"] is None
    assert report["bde_execution_attempted"] is True
