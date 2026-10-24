"""Dependency order and overlapping delivery scopes are management concerns."""
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_approved_project_setup import approved, environment, reapprove


@pytest.mark.asyncio
async def test_dependency_dag_and_shared_scopes_do_not_impose_delivery_list_order(tmp_path):
    handoff = approved()
    catalogue, basket, orders = handoff.decision.behaviors
    shared = {"production_paths": ("shared.py",), "test_paths": ("tests/test_shared.py",)}
    catalogue = replace(catalogue, **shared)
    basket = replace(basket, **shared)
    orders = replace(orders, depends_on=(catalogue.id,), **shared)
    decision = replace(handoff.decision, behaviors=(orders, basket, catalogue))
    reordered = reapprove(handoff, decision)
    _, _, app = environment(tmp_path / "valid", reordered)
    result = await app.setup.prepare(reordered)
    root = Path(result.repository_root)
    assert (root / "shared.py").read_bytes() == b""
    assert not (root / "tests/test_shared.py").exists()
    assert result.behavior_ids == (orders.id, basket.id, catalogue.id)
    with pytest.raises(ValueError, match="acyclic"):
        replace(decision, behaviors=(orders, basket, replace(catalogue, depends_on=(orders.id,))))
    for dependencies in ((catalogue.id,), ("unknown-behavior",)):
        with pytest.raises(ValueError, match="known other"):
            replace(decision, behaviors=(orders, basket, replace(catalogue, depends_on=dependencies)))
    invalid = reapprove(handoff, replace(decision,
        behaviors=(replace(catalogue, production_paths=("tests/test_shared.py",)), basket, orders)))
    _, _, invalid_app = environment(tmp_path / "invalid", invalid)
    with pytest.raises(ValueError, match="overlap"):
        await invalid_app.setup.prepare(invalid)
