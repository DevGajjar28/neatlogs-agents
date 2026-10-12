from app.mail.classify import classify_deterministic


def test_meeting_confirmed_yes_that_works():
    label = classify_deterministic(body="yes that's works for me")
    assert label == "meeting_confirmed"


def test_parse_meeting_time_tuesday_13th():
    from app.calendar.events import parse_meeting_time_from_text
    from datetime import datetime, timezone

    now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    from app.calendar.events import resolve_slot_start

    dt = resolve_slot_start(None, "Tuesday 13th at 5:00pm", now=now)
    assert dt is not None
    assert dt.day == 13
    assert dt.hour == 17
