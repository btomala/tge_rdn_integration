"""Test the tariff logic in sensor.py."""
import sys
import os
import unittest
from datetime import datetime, date
from unittest.mock import MagicMock

# Mock Home Assistant modules BEFORE importing from custom_components
mock_ha = MagicMock()
sys.modules["homeassistant"] = mock_ha
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["voluptuous"] = MagicMock()

# Define dummy base classes for Sensor components
class MockSensorEntity: pass
class MockCoordinatorEntity:
    def __init__(self, coord):
        self.coordinator = coord

sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity

# Add the custom_components to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from custom_components.tge_rdn.sensor import TGEFixedFeeSensor, TGERDNSensor, load_tariffs
from custom_components.tge_rdn.const import *

class MockCoordinator:
    def __init__(self):
        self.data = {}

class MockEntry:
    def __init__(self, options):
        self.entry_id = "test_entry"
        self.options = options

class TestTariffLogic(unittest.TestCase):
    """Test the distribution logic for different tariffs via zone schedules."""

    def setUp(self):
        self.coord = MockCoordinator()

    def test_load_tariffs(self):
        """Test that tariffs.json loads correctly with new schema."""
        data = load_tariffs()
        self.assertIn("sellers", data)
        self.assertIn("distributors", data)
        self.assertTrue(len(data["sellers"]) > 0)
        self.assertTrue(len(data["distributors"]) > 0)

    def test_single_tariff_g11(self):
        """Test G11 — single zone, always same rate from JSON."""
        options = {
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G11",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        # PGE G11 "all" zone rate = 349.59 netto PLN/MWh
        dt = datetime(2025, 1, 1, 10, 0)  # Wednesday morning
        self.assertEqual(sensor._get_dist(dt), 349.59)

        dt = datetime(2025, 1, 1, 20, 0)  # Wednesday evening
        self.assertEqual(sensor._get_dist(dt), 349.59)

    def test_dual_standard_g12(self):
        """Test PGE G12 dual zones with full variable distribution rates."""
        options = {
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G12",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        # Low: 22-05 all days
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 1, 23, 0)), 117.07)
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 1, 3, 0)), 117.07)

        # Low: 13-14 workday winter
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 2, 14, 0)), 117.07)  # Thursday

        # High: otherwise
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 2, 10, 0)), 442.28)
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 2, 18, 0)), 442.28)

    def test_dual_weekend_g12w(self):
        """Test PGE G12w dual zones with full variable distribution rates."""
        options = {
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G12w",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        # Weekend (Saturday 2025-01-04) - Should be low
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 4, 12, 0)), 125.2)

        # Holiday (Jan 1st) - Should be low
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 1, 12, 0)), 125.2)

        # Weekday peak - high
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 2, 10, 0)), 474.8)  # Thursday 10am

        # Weekday off-peak winter 13-14 - low
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 2, 14, 0)), 125.2)  # Thursday 2pm

    def test_pge_static_seller_prices_are_loaded_as_netto(self):
        """Test that PGE fixed seller tariffs expose netto seller prices from tariffs.json."""
        options = {
            CONF_DEALER: "PGE Obrót",
            CONF_DEALER_TARIFF: "G12",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G12",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2025, 1, 2, 14, 0))
        self.assertEqual(zone_name, "low")
        self.assertEqual(dist_rate, 117.07)
        self.assertEqual(seller_price, 373.98)

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2025, 1, 2, 10, 0))
        self.assertEqual(zone_name, "high")
        self.assertEqual(dist_rate, 442.28)
        self.assertEqual(seller_price, 569.11)

    def test_pge_g12e_prices_are_loaded_as_netto(self):
        """Test G12e seller and distributor prices converted from gross to netto."""
        options = {
            CONF_DEALER: "PGE Obrót",
            CONF_DEALER_TARIFF: "G12e",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G12e",
            CONF_VAT_RATE: 0.23,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2026, 5, 4, 9, 0))
        self.assertEqual((zone_name, dist_rate, seller_price), ("low", 76.42, 406.50))

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2026, 5, 4, 17, 0))
        self.assertEqual((zone_name, dist_rate, seller_price), ("high", 426.02, 682.93))

        fixed_fee = TGEFixedFeeSensor(
            entry, "fixed_transmission_fee", "Fixed Transmission Fee",
            CONF_FIXED_TRANSMISSION_FEE, DEFAULT_FIXED_TRANSMISSION_FEE,
        )
        trade_fee = TGEFixedFeeSensor(
            entry, "trade_fee", "Trade Fee", CONF_TRADE_FEE, DEFAULT_TRADE_FEE,
        )
        self.assertAlmostEqual(fixed_fee.state, 36.90, places=2)
        self.assertAlmostEqual(trade_fee.state, 43.00, places=2)

    def test_tauron_g12_weekend_midday_uses_low_prices(self):
        """Test that Tauron G12 uses both low seller and distribution rates on weekends."""
        options = {
            CONF_DEALER: "Tauron Sprzedaż",
            CONF_DEALER_TARIFF: "G12",
            CONF_DISTRIBUTOR: "Tauron Dystrybucja",
            CONF_DIST_TARIFF: "G12",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2026, 1, 10, 13, 0))
        self.assertEqual(zone_name, "low")
        self.assertEqual(dist_rate, 99.27)
        self.assertEqual(seller_price, 417.97)

        zone_name, dist_rate, seller_price = sensor._resolve(datetime(2026, 1, 10, 15, 0))
        self.assertEqual(zone_name, "high")
        self.assertEqual(dist_rate, 327.56)
        self.assertEqual(seller_price, 547.97)

    def test_pge_g12_weekend_midday_uses_seasonal_low_prices(self):
        """Test that PGE G12 uses low seller and distribution rates on seasonal weekend windows."""
        options = {
            CONF_DEALER: "PGE Obrót",
            CONF_DEALER_TARIFF: "G12",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G12",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        for when in [datetime(2026, 1, 10, 13, 0), datetime(2026, 7, 4, 15, 0)]:
            zone_name, dist_rate, seller_price = sensor._resolve(when)
            self.assertEqual(zone_name, "low")
            self.assertEqual(dist_rate, 117.07)
            self.assertEqual(seller_price, 373.98)

    def test_triple_tauron_g13(self):
        """Test Tauron G13 — three zones from JSON (mid_peak=263.82, peak=433.33, off_peak=82.70)."""
        options = {
            CONF_DISTRIBUTOR: "Tauron Dystrybucja",
            CONF_DIST_TARIFF: "G13",
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        # Weekend - off_peak
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 4, 12, 0)), 82.70)

        # Summer (July) Weekday
        # 7-12: mid_peak, 19-21: peak, else off_peak
        dt_summer = datetime(2025, 7, 2, 10, 0)  # Wednesday 10am
        self.assertEqual(sensor._get_dist(dt_summer), 263.82)

        dt_summer_evening = datetime(2025, 7, 2, 20, 0)  # Wednesday 8pm
        self.assertEqual(sensor._get_dist(dt_summer_evening), 433.33)

        dt_summer_night = datetime(2025, 7, 2, 23, 0)  # Wednesday 11pm
        self.assertEqual(sensor._get_dist(dt_summer_night), 82.70)

        # Winter (January) Weekday
        # 7-12: mid_peak, 16-20: peak, else off_peak
        dt_winter = datetime(2025, 1, 2, 10, 0)  # Thursday 10am
        self.assertEqual(sensor._get_dist(dt_winter), 263.82)

        dt_winter_evening = datetime(2025, 1, 2, 17, 0)  # Thursday 5pm
        self.assertEqual(sensor._get_dist(dt_winter_evening), 433.33)

        dt_winter_late = datetime(2025, 1, 2, 22, 0)  # Thursday 10pm
        self.assertEqual(sensor._get_dist(dt_winter_late), 82.70)

    def test_is_holiday(self):
        """Test holiday detection."""
        options = {}
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        self.assertTrue(sensor._is_holiday(date(2025, 1, 1)))  # New Year
        self.assertTrue(sensor._is_holiday(date(2025, 5, 3)))  # Constitution Day
        self.assertTrue(sensor._is_holiday(date(2025, 11, 11)))  # Independence Day

        # Easter 2025: April 20th
        self.assertTrue(sensor._is_holiday(date(2025, 4, 20)))
        self.assertTrue(sensor._is_holiday(date(2025, 4, 21)))  # Easter Monday

        # Not a holiday
        self.assertFalse(sensor._is_holiday(date(2025, 1, 2)))

    def test_legacy_fallback_no_zones(self):
        """Test that legacy configs without distributor/tariff fall back to CONF_DIST_LOW."""
        options = {
            CONF_DIST_LOW: 100.0,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        # Should always return the fallback rate
        self.assertEqual(sensor._get_dist(datetime(2025, 1, 1, 10, 0)), 100.0)
        self.assertEqual(sensor._get_dist(datetime(2025, 7, 2, 20, 0)), 100.0)

    def test_pstryk_negative_prices_allowed(self):
        """Test that Pstryk seller allows negative TGE prices (no max(0) clamping)."""
        options = {
            CONF_DEALER: "Pstryk",
            CONF_DEALER_TARIFF: "Dynamic",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G11",
            CONF_VAT_RATE: 0.23,
            CONF_EXCHANGE_FEE: 80.0,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        self.assertTrue(sensor._is_dynamic)
        self.assertTrue(sensor._negative_prices_allowed)

        dt = datetime(2025, 6, 15, 14, 0)  # Sunday afternoon
        # Negative TGE price: -50 PLN/MWh
        # base = -50 (not clamped), dist = 349.59, exchange_fee = 80.0, vat = 0.23
        # total = (-50.0 + 80.0 + 349.59) * 1.23 = 379.59 * 1.23 = 466.8957
        result = sensor._compute_total(-50.0, dt)
        self.assertAlmostEqual(result, 466.8957, places=4)

    def test_tauron_negative_prices_clamped(self):
        """Test that Tauron Dynamic clamps negative TGE prices to 0."""
        options = {
            CONF_DEALER: "Tauron Sprzedaż",
            CONF_DEALER_TARIFF: "Dynamic",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G11",
            CONF_VAT_RATE: 0.23,
            CONF_EXCHANGE_FEE: 89.2,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        self.assertTrue(sensor._is_dynamic)
        self.assertFalse(sensor._negative_prices_allowed)

        dt = datetime(2025, 6, 15, 14, 0)
        # Negative TGE price: -50 PLN/MWh
        # base = max(0, -50) = 0, dist = 349.59, exchange_fee = 89.2, vat = 0.23
        # total = (0.0 + 89.2 + 349.59) * 1.23 = 539.7117
        result = sensor._compute_total(-50.0, dt)
        self.assertAlmostEqual(result, 539.7117, places=4)

    def test_pstryk_positive_prices(self):
        """Test that Pstryk works normally with positive TGE prices."""
        options = {
            CONF_DEALER: "Pstryk",
            CONF_DEALER_TARIFF: "Dynamic",
            CONF_DISTRIBUTOR: "PGE Dystrybucja",
            CONF_DIST_TARIFF: "G11",
            CONF_VAT_RATE: 0.23,
            CONF_EXCHANGE_FEE: 80.0,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        dt = datetime(2025, 6, 15, 14, 0)
        # Positive TGE price: 300 PLN/MWh
        # base = 300, dist = 349.59, exchange_fee = 80.0, vat = 0.23
        # total = (300.0 + 80.0 + 349.59) * 1.23 = 729.59 * 1.23 = 897.3957
        result = sensor._compute_total(300.0, dt)
        self.assertAlmostEqual(result, 897.3957, places=4)

    def test_non_dynamic_prices_apply_vat_to_distribution_too(self):
        """Test that fixed seller price and distribution rates are both treated as netto."""
        options = {
            CONF_DEALER: "Tauron Sprzedaż",
            CONF_DEALER_TARIFF: "G13",
            CONF_DISTRIBUTOR: "Tauron Dystrybucja",
            CONF_DIST_TARIFF: "G13",
            CONF_VAT_RATE: 0.23,
        }
        entry = MockEntry(options)
        sensor = TGERDNSensor(self.coord, entry, "current_price")

        dt = datetime(2025, 7, 2, 10, 0)  # Workday, summer, mid_peak
        # seller = 471.79, dist = 263.82, both netto
        # total = (471.79 + 263.82) * 1.23 = 904.8003
        result = sensor._compute_total(0.0, dt)
        self.assertAlmostEqual(result, 904.8003, places=4)

    def test_negative_prices_allowed_attribute_in_tariffs(self):
        """Test that negative_prices_allowed is present in tariffs.json for all sellers."""
        data = load_tariffs()
        for seller in data["sellers"]:
            self.assertIn(
                "negative_prices_allowed", seller,
                f"Seller '{seller['name']}' missing negative_prices_allowed"
            )
        # Specifically check Pstryk is True, others are False
        seller_map = {s["name"]: s["negative_prices_allowed"] for s in data["sellers"]}
        self.assertTrue(seller_map["Pstryk"])
        self.assertFalse(seller_map["Tauron Sprzedaż"])
        self.assertFalse(seller_map["PGE Obrót"])

    def test_fixed_distribution_fee_sensor_applies_vat(self):
        """Test that distributor monthly fixed fees are read as netto and exposed as gross."""
        options = {
            CONF_DISTRIBUTOR: "Tauron Dystrybucja",
            CONF_DIST_TARIFF: "G13",
            CONF_VAT_RATE: 0.23,
        }
        entry = MockEntry(options)
        sensor = TGEFixedFeeSensor(
            entry,
            "fixed_transmission_fee",
            "Fixed Transmission Fee",
            CONF_FIXED_TRANSMISSION_FEE,
            DEFAULT_FIXED_TRANSMISSION_FEE,
        )

        # tariffs.json: Tauron Dystrybucja G13 fixed_transmission_fee = 10.86 netto
        self.assertAlmostEqual(sensor.state, 13.3578, places=4)

    def test_trade_fee_sensor_applies_vat(self):
        """Test that seller monthly trade fee is read as netto and exposed as gross."""
        options = {
            CONF_DEALER: "PGE Obrót",
            CONF_DEALER_TARIFF: "Dynamic",
            CONF_VAT_RATE: 0.23,
        }
        entry = MockEntry(options)
        sensor = TGEFixedFeeSensor(
            entry,
            "trade_fee",
            "Trade Fee",
            CONF_TRADE_FEE,
            DEFAULT_TRADE_FEE,
        )

        # tariffs.json: PGE Dynamic trade_fee = 5.0 netto
        self.assertAlmostEqual(sensor.state, 6.15, places=2)

if __name__ == '__main__':
    unittest.main()
