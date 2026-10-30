"""Per-plugin L5 must not pull sibling plugins' controls into the arm."""
from __future__ import annotations

from run_eval import _task_family_prefixes, load_tasks


def test_family_prefixes() -> None:
    assert _task_family_prefixes([{"id": "symnav-v2-001-x"}]) == {"symnav-v2"}
    assert _task_family_prefixes([{"id": "nav-001-x"}]) == {"nav"}


def test_symbol_navigator_v2_controls_are_scoped() -> None:
    tasks = load_tasks("navigation", 2, plugin="symbol-navigator")
    ids = {t["id"] for t in tasks}
    assert any(not t.get("control") and t["id"].startswith("symnav-v2-") for t in tasks)
    controls = [t for t in tasks if t.get("control")]
    assert controls
    assert all(t["id"].startswith("symnav-v2-") for t in controls)
    assert not any(i.startswith("depgraph-v2-ctl") for i in ids)
    assert not any(i.startswith("docscrap-v2-ctl") for i in ids)
