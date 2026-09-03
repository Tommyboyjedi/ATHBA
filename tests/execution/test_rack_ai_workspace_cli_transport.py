from __future__ import annotations

import json
import subprocess

from core.execution.rack_ai_workspace_cli_transport import (
    RackAiWorkspaceCliConfig,
    RackAiWorkspaceCliTransport,
)


def payload():
    return {
        "work_unit": {
            "limits": {"timeout_seconds": 300},
            "routing": {"submission_id": "submission"},
        }
    }


def test_transport_loads_packet_after_v2_cli_json(monkeypatch, tmp_path):
    packet_path = tmp_path / "review-packet.json"
    packet_path.write_text(json.dumps({"status": "checks_passed"}), encoding="utf-8")

    def fake_run(*args, **kwargs):
        assert "work-unit" in args[0]
        assert "--emit-json" in args[0]
        assert kwargs["timeout"] == 330
        return subprocess.CompletedProcess(args[0], 0, json.dumps({"packet_path": str(packet_path)}), "")

    monkeypatch.setattr("core.execution.rack_ai_workspace_cli_transport.subprocess.run", fake_run)
    result = RackAiWorkspaceCliTransport(RackAiWorkspaceCliConfig(state_root=str(tmp_path))).submit(payload())
    assert result["submission_id"] == "submission"
    assert result["packet_path"] == str(packet_path)


def test_transport_translates_duplicate_cli_rejection(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "duplicate idempotent submission")

    monkeypatch.setattr("core.execution.rack_ai_workspace_cli_transport.subprocess.run", fake_run)
    result = RackAiWorkspaceCliTransport(RackAiWorkspaceCliConfig()).submit(payload())
    assert result == {"submission_id": "submission", "status": "duplicate_submission", "generic_failure": "duplicate idempotent submission"}
