"""Helpers for evaluating sunrise/sunset automation windows."""

from datetime import datetime, timedelta


SUPPORTED_SUN_EVENTS = {"sunrise", "sunset"}


def parse_solar_offset(offset_str):
    """Return (event_name, offset_minutes) from strings like sunset_offset_-60."""
    try:
        event_name, marker, offset_value = offset_str.rsplit("_", 2)
        if marker != "offset" or event_name not in SUPPORTED_SUN_EVENTS:
            raise ValueError
        return event_name, int(offset_value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid solar offset: {offset_str!r}") from exc


def _sun_time(offset_str, sun_times):
    event_name, offset_minutes = parse_solar_offset(offset_str)
    base_time = sun_times[event_name]
    if not isinstance(base_time, datetime):
        raise ValueError(f"Invalid sun time for {event_name!r}: {base_time!r}")
    return event_name, offset_minutes, base_time + timedelta(minutes=offset_minutes)


def get_sun_time(offset_str, sun_times):
    """Return the datetime represented by a solar offset string."""
    return _sun_time(offset_str, sun_times)[2]


def _is_between(now, start_dt, end_dt):
    if start_dt <= end_dt:
        return start_dt <= now <= end_dt
    return now >= start_dt or now <= end_dt


def _dual_event_windows(now, start_event, start_offset, end_event, end_offset, sun_times):
    """
    Evaluate paired sunrise/sunset windows.

    The editor stores only two bounds. For a rule configured as "1h before sunset"
    to "1h after sunrise", users expect two narrow windows around the two solar
    events, not one all-night interval. We therefore reuse the before/after
    offsets around each event: sunset-1h..sunset+1h and sunrise-1h..sunrise+1h.
    """
    before_offset = start_offset if start_offset <= 0 else -abs(start_offset)
    after_offset = end_offset if end_offset >= 0 else abs(end_offset)

    for event_name in (start_event, end_event):
        base_time = sun_times[event_name]
        window_start = base_time + timedelta(minutes=before_offset)
        window_end = base_time + timedelta(minutes=after_offset)
        if _is_between(now, window_start, window_end):
            return True
    return False


def is_solar_condition_active(condition_dict, sun_times, now=None):
    """Return True when the current time is inside an automation solar condition."""
    if now is None:
        sample_time = sun_times.get("sunrise") or sun_times.get("sunset")
        now = datetime.now(sample_time.tzinfo if isinstance(sample_time, datetime) else None)

    start_event, start_offset, start_dt = _sun_time(condition_dict["start"], sun_times)
    end_event, end_offset, end_dt = _sun_time(condition_dict["end"], sun_times)

    if start_event != end_event and start_offset <= 0 <= end_offset:
        return _dual_event_windows(now, start_event, start_offset, end_event, end_offset, sun_times)

    return _is_between(now, start_dt, end_dt)
