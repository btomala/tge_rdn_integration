"""Tests for resolve_zone() and is_polish_holiday() functions."""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock

# Mock Home Assistant modules BEFORE importing from custom_components
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["voluptuous"] = MagicMock()

# Define dummy base classes
class MockSensorEntity: pass
class MockCoordinatorEntity:
    def __init__(self, coord):
        self.coordinator = coord

sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.helpers.device_registry"].DeviceInfo = dict
sys.modules["homeassistant.helpers.device_registry"].DeviceEntryType.SERVICE = "service"

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from custom_components.tge_rdn.sensor import resolve_zone, is_polish_holiday, _easter, load_tariffs


def dt(year, month, day, hour):
    """Shortcut for creating datetime."""
    return datetime(year, month, day, hour, 0, 0)


# --- Zone definitions loaded from tariffs.json for testing ---

def load_test_tariffs():
    """Load tariffs.json from the component directory."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "tge_rdn", "tariffs.json"
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_dist_zones(data, distributor_name, tariff_name):
    """Get zones dict for a distributor tariff."""
    for d in data.get("distributors", []):
        if d["name"] == distributor_name:
            for t in d.get("tariffs", []):
                if t["name"] == tariff_name:
                    return t["zones"]
    raise ValueError(f"Tariff {tariff_name} not found for {distributor_name}")


class TestPolishHolidays(unittest.TestCase):
    """Test is_polish_holiday() function."""

    def test_new_year(self):
        self.assertTrue(is_polish_holiday(date(2026, 1, 1)))

    def test_epiphany(self):
        self.assertTrue(is_polish_holiday(date(2026, 1, 6)))

    def test_labour_day(self):
        self.assertTrue(is_polish_holiday(date(2026, 5, 1)))

    def test_constitution_day(self):
        self.assertTrue(is_polish_holiday(date(2026, 5, 3)))

    def test_assumption(self):
        self.assertTrue(is_polish_holiday(date(2026, 8, 15)))

    def test_all_saints(self):
        self.assertTrue(is_polish_holiday(date(2026, 11, 1)))

    def test_independence_day(self):
        self.assertTrue(is_polish_holiday(date(2026, 11, 11)))

    def test_christmas_day(self):
        self.assertTrue(is_polish_holiday(date(2026, 12, 25)))

    def test_second_christmas(self):
        self.assertTrue(is_polish_holiday(date(2026, 12, 26)))

    def test_easter_2026(self):
        # Easter 2026 is April 5
        easter = _easter(2026)
        self.assertEqual(easter, date(2026, 4, 5))
        self.assertTrue(is_polish_holiday(date(2026, 4, 5)))   # Easter Sunday
        self.assertTrue(is_polish_holiday(date(2026, 4, 6)))   # Easter Monday

    def test_corpus_christi_2026(self):
        # Corpus Christi 2026 = Easter + 60 = June 4
        self.assertTrue(is_polish_holiday(date(2026, 6, 4)))

    def test_whit_sunday_2026(self):
        # Zielone Świątki = Easter + 49 = May 24
        self.assertTrue(is_polish_holiday(date(2026, 5, 24)))

    def test_normal_workday_not_holiday(self):
        self.assertFalse(is_polish_holiday(date(2026, 3, 10)))  # Tuesday

    def test_weekend_not_holiday(self):
        # Regular Saturday — not a public holiday
        self.assertFalse(is_polish_holiday(date(2026, 3, 7)))


class TestResolveZoneG11(unittest.TestCase):
    """Test G11 single-zone tariff — always returns the same zone."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "Tauron Dystrybucja", "G11")

    def test_workday_morning(self):
        zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, 8), False)
        self.assertEqual(zone, "all")
        self.assertEqual(rate, 289.92)

    def test_workday_night(self):
        zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, 23), False)
        self.assertEqual(zone, "all")
        self.assertEqual(rate, 289.92)

    def test_weekend(self):
        zone, rate = resolve_zone(self.zones, dt(2026, 1, 10, 14), False)  # Saturday
        self.assertEqual(zone, "all")

    def test_holiday(self):
        zone, rate = resolve_zone(self.zones, dt(2026, 12, 25, 12), True)
        self.assertEqual(zone, "all")


class TestResolveZoneG12Tauron(unittest.TestCase):
    """Test G12 dual-zone tariff for Tauron (no seasonal variation in midday)."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "Tauron Dystrybucja", "G12")

    def test_night_low_zone(self):
        """22:00-05:59 should be low."""
        for h in [22, 23, 0, 1, 2, 3, 4, 5]:
            zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "low", f"Hour {h} should be low")
            self.assertEqual(rate, 99.27)

    def test_midday_low_zone(self):
        """13:00-14:59 should be low every day."""
        for h in [13, 14]:
            zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, h), False)  # Monday
            self.assertEqual(zone, "low", f"Hour {h} should be low")

    def test_weekend_midday_low_zone_boundaries(self):
        """Weekend midday window should be low only from 13:00 to 14:59."""
        for day in [10, 11]:  # Saturday and Sunday
            expected_zones = {12: "high", 13: "low", 14: "low", 15: "high"}
            for hour, expected_zone in expected_zones.items():
                zone, _ = resolve_zone(self.zones, dt(2026, 1, day, hour), False)
                self.assertEqual(
                    zone,
                    expected_zone,
                    f"Day {day}, hour {hour} should be {expected_zone}",
                )

    def test_holiday_midday_low_zone(self):
        """The midday low window should also apply on public holidays."""
        for hour in [13, 14]:
            zone, rate = resolve_zone(self.zones, dt(2026, 12, 25, hour), True)
            self.assertEqual(zone, "low")
            self.assertEqual(rate, 99.27)

    def test_daytime_high_zone(self):
        """6:00-12:59 and 15:00-21:59 workday should be high."""
        for h in [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21]:
            zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "high", f"Hour {h} should be high")
            self.assertEqual(rate, 327.56)

    def test_boundary_hour_22(self):
        """Boundary: hour 22 = low."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 22), False)
        self.assertEqual(zone, "low")

    def test_boundary_hour_6(self):
        """Boundary: hour 6 = high."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 6), False)
        self.assertEqual(zone, "high")

    def test_boundary_hour_13(self):
        """Boundary: hour 13 = low (midday dip)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 13), False)
        self.assertEqual(zone, "low")

    def test_boundary_hour_15(self):
        """Boundary: hour 15 = high (midday dip ends)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 15), False)
        self.assertEqual(zone, "high")


class TestResolveZoneG12PGE(unittest.TestCase):
    """Test G12 for PGE Dystrybucja — has seasonal midday variation."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "PGE Dystrybucja", "G12")

    def test_winter_midday_low(self):
        """Winter (Jan): midday low at 13-14."""
        for h in [13, 14]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "low", f"Winter hour {h} should be low")

    def test_winter_midday_15_is_high(self):
        """Winter (Jan): hour 15 is NOT low."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 15), False)
        self.assertEqual(zone, "high")

    def test_summer_midday_low(self):
        """Summer (Jul): midday low at 15-16."""
        for h in [15, 16]:
            zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, h), False)  # Monday
            self.assertEqual(zone, "low", f"Summer hour {h} should be low")

    def test_summer_midday_13_is_high(self):
        """Summer (Jul): hour 13 is NOT low (unlike winter)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, 13), False)
        self.assertEqual(zone, "high")

    def test_weekend_midday_low_in_both_seasons(self):
        """Seasonal midday windows should also apply on weekends."""
        winter_zone, _ = resolve_zone(self.zones, dt(2026, 1, 10, 13), False)
        summer_zone, _ = resolve_zone(self.zones, dt(2026, 7, 4, 15), False)
        self.assertEqual(winter_zone, "low")
        self.assertEqual(summer_zone, "low")

    def test_holiday_midday_low_in_both_seasons(self):
        """Seasonal midday windows should also apply on public holidays."""
        winter_zone, _ = resolve_zone(self.zones, dt(2026, 12, 25, 13), True)
        summer_zone, _ = resolve_zone(self.zones, dt(2026, 5, 1, 15), True)
        self.assertEqual(winter_zone, "low")
        self.assertEqual(summer_zone, "low")

    def test_night_same_in_both_seasons(self):
        """Night hours are low regardless of season."""
        for h in [22, 23, 0, 1, 2, 3, 4, 5]:
            zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, h), False)
            self.assertEqual(zone, "low", f"Summer night hour {h} should be low")
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "low", f"Winter night hour {h} should be low")

    def test_season_boundary_april(self):
        """April 1 = start of summer."""
        zone, _ = resolve_zone(self.zones, dt(2026, 4, 1, 15), False)  # Wednesday
        self.assertEqual(zone, "low")  # Summer rule: 15-16 low

    def test_season_boundary_march(self):
        """March 31 = still winter."""
        zone, _ = resolve_zone(self.zones, dt(2026, 3, 31, 15), False)  # Tuesday
        self.assertEqual(zone, "high")  # Winter: 15 is high

    def test_season_boundary_october(self):
        """October 1 = start of winter."""
        zone, _ = resolve_zone(self.zones, dt(2026, 10, 1, 13), False)  # Thursday
        self.assertEqual(zone, "low")  # Winter rule: 13-14 low


class TestResolveZoneG12w(unittest.TestCase):
    """Test G12w weekend tariff for Tauron."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "Tauron Dystrybucja", "G12w")

    def test_saturday_all_low(self):
        """Saturday — every hour should be low."""
        for h in range(24):
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 10, h), False)  # Saturday
            self.assertEqual(zone, "low", f"Saturday hour {h} should be low")

    def test_sunday_all_low(self):
        """Sunday — every hour should be low."""
        for h in range(24):
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 11, h), False)  # Sunday
            self.assertEqual(zone, "low", f"Sunday hour {h} should be low")

    def test_holiday_all_low(self):
        """Polish holiday (Christmas) — every hour should be low."""
        for h in range(24):
            zone, _ = resolve_zone(self.zones, dt(2026, 12, 25, h), True)
            self.assertEqual(zone, "low", f"Holiday hour {h} should be low")

    def test_workday_daytime_high(self):
        """Workday 6:00-12:59 and 15:00-21:59 should be high."""
        for h in [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)  # Monday
            self.assertEqual(zone, "high", f"Workday hour {h} should be high")

    def test_workday_night_low(self):
        """Workday night hours should be low."""
        for h in [22, 23, 0, 1, 2, 3, 4, 5]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "low", f"Workday night hour {h} should be low")

    def test_workday_midday_low(self):
        """Workday 13:00-14:59 midday should be low."""
        for h in [13, 14]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "low", f"Workday hour {h} should be low")

    def test_holiday_on_weekday(self):
        """May 1 (Thursday) is a holiday — should be all low."""
        for h in [8, 12, 18]:
            zone, _ = resolve_zone(self.zones, dt(2026, 5, 1, h), True)
            self.assertEqual(zone, "low", f"Holiday workday hour {h} should be low")


class TestResolveZoneG13(unittest.TestCase):
    """Test G13 triple-zone tariff for Tauron."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "Tauron Dystrybucja", "G13")

    # --- Workday summer ---
    def test_summer_morning_mid_peak(self):
        """Summer workday 7-12 = mid_peak."""
        for h in [7, 8, 9, 10, 11, 12]:
            zone, rate = resolve_zone(self.zones, dt(2026, 6, 1, h), False)  # Monday
            self.assertEqual(zone, "mid_peak", f"Summer workday hour {h} should be mid_peak")
            self.assertEqual(rate, 263.82)

    def test_summer_afternoon_peak(self):
        """Summer workday 19-21 = peak."""
        for h in [19, 20, 21]:
            zone, rate = resolve_zone(self.zones, dt(2026, 7, 6, h), False)  # Monday
            self.assertEqual(zone, "peak", f"Summer workday hour {h} should be peak")
            self.assertEqual(rate, 433.33)

    def test_summer_off_peak(self):
        """Summer workday remaining hours = off_peak."""
        for h in [0, 1, 2, 3, 4, 5, 6, 13, 14, 15, 16, 17, 18, 22, 23]:
            zone, rate = resolve_zone(self.zones, dt(2026, 7, 6, h), False)
            self.assertEqual(zone, "off_peak", f"Summer workday hour {h} should be off_peak")
            self.assertEqual(rate, 82.70)

    # --- Workday winter ---
    def test_winter_morning_mid_peak(self):
        """Winter workday 7-12 = mid_peak."""
        for h in [7, 8, 9, 10, 11, 12]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)  # Monday
            self.assertEqual(zone, "mid_peak", f"Winter workday hour {h} should be mid_peak")

    def test_winter_afternoon_peak(self):
        """Winter workday 16-20 = peak."""
        for h in [16, 17, 18, 19, 20]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "peak", f"Winter workday hour {h} should be peak")

    def test_winter_off_peak(self):
        """Winter workday remaining hours = off_peak."""
        for h in [0, 1, 2, 3, 4, 5, 6, 13, 14, 15, 21, 22, 23]:
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "off_peak", f"Winter workday hour {h} should be off_peak")

    # --- Weekends and holidays ---
    def test_weekend_all_off_peak(self):
        """Weekend all hours = off_peak."""
        for h in range(24):
            zone, _ = resolve_zone(self.zones, dt(2026, 1, 10, h), False)  # Saturday
            self.assertEqual(zone, "off_peak", f"Weekend hour {h} should be off_peak")

    def test_holiday_all_off_peak(self):
        """Holiday all hours = off_peak."""
        for h in [8, 12, 17, 20]:
            zone, _ = resolve_zone(self.zones, dt(2026, 5, 1, h), True)
            self.assertEqual(zone, "off_peak", f"Holiday hour {h} should be off_peak")

    # --- Season boundaries ---
    def test_boundary_summer_peak_hour_19(self):
        """Summer: 19 is peak; winter: 19 is also peak."""
        zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, 19), False)
        self.assertEqual(zone, "peak")
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 19), False)
        self.assertEqual(zone, "peak")

    def test_boundary_summer_hour_16_off_peak(self):
        """Summer workday hour 16 = off_peak (peak starts at 19)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, 16), False)
        self.assertEqual(zone, "off_peak")

    def test_boundary_winter_hour_16_peak(self):
        """Winter workday hour 16 = peak (peak starts at 16)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 16), False)
        self.assertEqual(zone, "peak")

    def test_boundary_hour_7_always_mid_peak(self):
        """Hour 7 workday = mid_peak in both seasons."""
        zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, 7), False)
        self.assertEqual(zone, "mid_peak")
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 7), False)
        self.assertEqual(zone, "mid_peak")

    def test_boundary_hour_13_off_peak(self):
        """Hour 13 workday = off_peak (mid_peak ends at 12)."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 13), False)
        self.assertEqual(zone, "off_peak")


class TestResolveZoneG12wPGE(unittest.TestCase):
    """Test G12w for PGE Dystrybucja — has seasonal midday + weekend."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "PGE Dystrybucja", "G12w")

    def test_winter_workday_midday_low(self):
        """Winter workday 13-14 = low."""
        zone, _ = resolve_zone(self.zones, dt(2026, 1, 12, 13), False)
        self.assertEqual(zone, "low")

    def test_summer_workday_midday_low(self):
        """Summer workday 15-16 = low."""
        zone, _ = resolve_zone(self.zones, dt(2026, 7, 6, 15), False)
        self.assertEqual(zone, "low")

    def test_weekend_all_low(self):
        """Weekend all hours = low."""
        for h in range(24):
            zone, _ = resolve_zone(self.zones, dt(2026, 7, 4, h), False)  # Saturday
            self.assertEqual(zone, "low", f"Weekend hour {h} should be low")


class TestResolveZoneG12ePGE(unittest.TestCase):
    """Test PGE G12e monthly workday windows and all-day days off."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "PGE Dystrybucja", "G12e")

    def test_every_month_workday_schedule(self):
        """Each month uses its published daytime window plus 22:00-06:00."""
        workdays = {
            1: 12, 2: 2, 3: 2, 4: 1, 5: 4, 6: 1,
            7: 6, 8: 3, 9: 1, 10: 5, 11: 2, 12: 1,
        }
        daytime_windows = {
            1: range(13, 15), 2: range(13, 15),
            3: range(11, 15), 4: range(10, 17),
            5: range(9, 17), 6: range(9, 17),
            7: range(9, 17), 8: range(9, 17),
            9: range(10, 17), 10: range(11, 15),
            11: range(13, 15), 12: range(13, 15),
        }

        for month, day in workdays.items():
            low_hours = set(range(0, 6)) | set(daytime_windows[month]) | {22, 23}
            for hour in range(24):
                with self.subTest(month=month, hour=hour):
                    zone, rate = resolve_zone(self.zones, dt(2026, month, day, hour), False)
                    expected_zone = "low" if hour in low_hours else "high"
                    expected_rate = 76.42 if expected_zone == "low" else 426.02
                    self.assertEqual(zone, expected_zone)
                    self.assertEqual(rate, expected_rate)

    def test_weekend_and_holiday_all_low(self):
        """Weekends and public holidays use the low zone all day."""
        for when, is_holiday in [(dt(2026, 7, 4, 0), False), (dt(2026, 12, 25, 0), True)]:
            for hour in range(24):
                with self.subTest(when=when, hour=hour):
                    zone, rate = resolve_zone(self.zones, when.replace(hour=hour), is_holiday)
                    self.assertEqual(zone, "low")
                    self.assertEqual(rate, 76.42)


class TestResolveZoneCustom(unittest.TestCase):
    """Test Custom tariff — single zone with rate 0."""

    def setUp(self):
        data = load_test_tariffs()
        self.zones = get_dist_zones(data, "Custom", "Custom")

    def test_always_returns_all(self):
        for h in [0, 6, 12, 18, 23]:
            zone, rate = resolve_zone(self.zones, dt(2026, 1, 12, h), False)
            self.assertEqual(zone, "all")
            self.assertEqual(rate, 0.0)


class TestLoadTariffs(unittest.TestCase):
    """Test that tariffs.json loads correctly with new schema."""

    def setUp(self):
        self.data = load_test_tariffs()

    def test_has_sellers_key(self):
        self.assertIn("sellers", self.data)

    def test_has_distributors_key(self):
        self.assertIn("distributors", self.data)

    def test_sellers_have_names(self):
        for seller in self.data["sellers"]:
            self.assertIn("name", seller)
            self.assertIn("tariffs", seller)

    def test_seller_tariffs_have_required_fields(self):
        for seller in self.data["sellers"]:
            for t in seller["tariffs"]:
                self.assertIn("name", t)
                self.assertIn("is_dynamic", t)
                if t.get("is_dynamic"):
                    self.assertIn("exchange_fee", t)
                    self.assertIn("trade_fee", t)

    def test_all_g12_midday_windows_apply_every_day(self):
        """Every distributor G12 midday window applies on workdays, weekends, and holidays."""
        dates_by_season = {
            "winter": [
                (dt(2026, 1, 12, 0), False),
                (dt(2026, 1, 10, 0), False),
                (dt(2026, 12, 25, 0), True),
            ],
            "summer": [
                (dt(2026, 7, 6, 0), False),
                (dt(2026, 7, 4, 0), False),
                (dt(2026, 5, 1, 0), True),
            ],
            "all": [
                (dt(2026, 1, 12, 0), False),
                (dt(2026, 1, 10, 0), False),
                (dt(2026, 12, 25, 0), True),
            ],
        }

        for distributor in self.data["distributors"]:
            g12 = next((tariff for tariff in distributor["tariffs"] if tariff["name"] == "G12"), None)
            if g12 is None:
                continue
            midday_rules = g12["zones"]["low"]["schedule"][1:]
            self.assertTrue(midday_rules, f"{distributor['name']} G12 has no midday low window")
            for rule in midday_rules:
                self.assertEqual(rule.get("days"), "all", distributor["name"])
                for base_datetime, is_holiday in dates_by_season[rule.get("season", "all")]:
                    for hour in rule["hours"]:
                        when = base_datetime.replace(hour=hour)
                        zone, _ = resolve_zone(g12["zones"], when, is_holiday)
                        self.assertEqual(zone, "low", f"{distributor['name']} at {when}")

    def test_distributor_tariffs_have_zones(self):
        for dist in self.data["distributors"]:
            for t in dist["tariffs"]:
                self.assertIn("zones", t, f"Missing zones in {dist['name']} {t['name']}")
                self.assertIn("fixed_fees", t, f"Missing fixed_fees in {dist['name']} {t['name']}")

    def test_every_tariff_has_default_zone(self):
        """Every distributor tariff must have exactly one default rule."""
        for dist in self.data["distributors"]:
            for t in dist["tariffs"]:
                has_default = False
                for zone_name, zone_def in t["zones"].items():
                    for rule in zone_def.get("schedule", []):
                        if rule.get("default"):
                            has_default = True
                self.assertTrue(has_default, f"{dist['name']} {t['name']} has no default zone")

    def test_pge_has_dynamic_seller_tariff(self):
        for seller in self.data["sellers"]:
            if seller["name"] == "PGE Obrót":
                names = [t["name"] for t in seller["tariffs"]]
                self.assertIn("Dynamic", names)
                for t in seller["tariffs"]:
                    if t["name"] == "Dynamic":
                        self.assertTrue(t.get("is_dynamic", False))
                return
        self.fail("PGE Obrót not found")

    def test_custom_seller_exists(self):
        names = [s["name"] for s in self.data["sellers"]]
        self.assertIn("Custom", names)

    def test_custom_distributor_exists(self):
        names = [d["name"] for d in self.data["distributors"]]
        self.assertIn("Custom", names)


class TestResolveZoneEdgeCases(unittest.TestCase):
    """Test edge cases for resolve_zone()."""

    def test_empty_zones_returns_fallback(self):
        """Empty zones dict should return default fallback."""
        zone, rate = resolve_zone({}, dt(2026, 1, 12, 10), False)
        self.assertEqual(zone, "all")
        self.assertEqual(rate, 0.0)

    def test_only_default_zone(self):
        """Zones with only a default rule."""
        zones = {"single": {"rate": 100.0, "schedule": [{"default": True}]}}
        zone, rate = resolve_zone(zones, dt(2026, 1, 12, 10), False)
        self.assertEqual(zone, "single")
        self.assertEqual(rate, 100.0)

    def test_midnight_hour_0(self):
        """Hour 0 (midnight) should work with night rules."""
        data = load_test_tariffs()
        zones = get_dist_zones(data, "Tauron Dystrybucja", "G12")
        zone, _ = resolve_zone(zones, dt(2026, 1, 12, 0), False)
        self.assertEqual(zone, "low")

    def test_hour_23(self):
        """Hour 23 should match night rules."""
        data = load_test_tariffs()
        zones = get_dist_zones(data, "Tauron Dystrybucja", "G12")
        zone, _ = resolve_zone(zones, dt(2026, 1, 12, 23), False)
        self.assertEqual(zone, "low")

    def test_dst_transition_day(self):
        """Daylight saving transition day should still resolve zones correctly."""
        data = load_test_tariffs()
        zones = get_dist_zones(data, "Tauron Dystrybucja", "G12")
        # Last Sunday of March 2026 = March 29 (DST change)
        zone, _ = resolve_zone(zones, dt(2026, 3, 29, 2), False)
        self.assertEqual(zone, "low")  # Night rule


if __name__ == "__main__":
    unittest.main()
