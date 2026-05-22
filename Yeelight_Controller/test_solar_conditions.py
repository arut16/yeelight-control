from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from solar_conditions import get_sun_time, is_solar_condition_active, parse_solar_offset


TZ = ZoneInfo("Europe/Paris")
SUN_TIMES = {
    "sunrise": datetime(2026, 5, 16, 6, 5, tzinfo=TZ),
    "sunset": datetime(2026, 5, 16, 20, 52, tzinfo=TZ),
}


class SolarConditionTests(unittest.TestCase):
    def test_parse_offset(self):
        self.assertEqual(parse_solar_offset("sunset_offset_-60"), ("sunset", -60))

    def test_sunset_to_sunrise_offsets_are_two_event_windows_not_all_night(self):
        condition = {"start": "sunset_offset_-60", "end": "sunrise_offset_60"}
        self.assertFalse(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 0, 10, tzinfo=TZ)))
        self.assertTrue(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 5, 30, tzinfo=TZ)))
        self.assertTrue(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 21, 30, tzinfo=TZ)))
        self.assertFalse(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 22, 30, tzinfo=TZ)))

    def test_same_event_window_keeps_direct_interval_semantics(self):
        condition = {"start": "sunset_offset_-60", "end": "sunset_offset_60"}
        self.assertTrue(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 20, 0, tzinfo=TZ)))
        self.assertFalse(is_solar_condition_active(condition, SUN_TIMES, datetime(2026, 5, 16, 22, 0, tzinfo=TZ)))

    def test_get_sun_time_applies_offset(self):
        self.assertEqual(get_sun_time("sunrise_offset_60", SUN_TIMES), datetime(2026, 5, 16, 7, 5, tzinfo=TZ))


if __name__ == "__main__":
    unittest.main()
