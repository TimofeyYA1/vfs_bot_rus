from pathlib import Path

from vfs_bot.models import CheckState, SlotObservation
from vfs_bot.storage import StateStore


def test_store_detects_transition(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    first = SlotObservation(target_id="moscow", state=CheckState.CLOSED)
    second = SlotObservation(target_id="moscow", state=CheckState.OPEN)

    initial = store.update(first)
    changed = store.update(second)

    assert initial.previous_state is None
    assert initial.state_changed is True
    assert changed.previous_state == CheckState.CLOSED
    assert changed.state_changed is True
