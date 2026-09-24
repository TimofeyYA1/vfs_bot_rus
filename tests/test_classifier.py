from datetime import date

from vfs_bot.classifier import classify_page, extract_dates
from vfs_bot.models import CheckState


def test_closed_phrase_wins() -> None:
    assert (
        classify_page("We are sorry, but no appointment slots are currently available")
        == CheckState.CLOSED
    )


def test_open_from_slot_controls() -> None:
    assert classify_page("Appointment details", has_slot_controls=True) == CheckState.OPEN


def test_blocked_wins_over_unknown() -> None:
    assert classify_page("Access denied. Too many requests.") == CheckState.BLOCKED


def test_extract_dates_multiple_formats() -> None:
    assert extract_dates("25.09.2026 and 2026-10-03") == (
        date(2026, 9, 25),
        date(2026, 10, 3),
    )
