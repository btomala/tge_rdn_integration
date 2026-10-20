"""Test the binary sensor for dynamic tariff indicator."""
import sys
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock

# Mock Home Assistant modules BEFORE importing from custom_components
mock_ha = MagicMock()
sys.modules["homeassistant"] = mock_ha
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["voluptuous"] = MagicMock()

# Define dummy base class for BinarySensorEntity
class MockBinarySensorEntity:
    pass

class MockSensorEntity:
    pass

class MockCoordinatorEntity:
    def __init__(self, coord):
        self.coordinator = coord

sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = MockBinarySensorEntity
sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.helpers.device_registry"].DeviceInfo = dict
sys.modules["homeassistant.helpers.device_registry"].DeviceEntryType.SERVICE = "service"

# Add the custom_components to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from custom_components.tge_rdn.binary_sensor import (
    TGECheapElectricityBinarySensor,
    TGEDynamicTariffBinarySensor,
    load_tariffs,
)
from custom_components.tge_rdn.const import DOMAIN, SENSOR_IS_DYNAMIC, TGE_PAGE_URL


class MockEntry:
    def __init__(self, options):
        self.entry_id = "test_entry"
        self.options = options


class TestDynamicTariffBinarySensor(unittest.TestCase):
    """Test the TGEDynamicTariffBinarySensor."""

    def setUp(self):
        self.tariffs_data = load_tariffs()

    def test_dynamic_tariff_is_on(self):
        """Dynamic seller tariff should return is_on=True."""
        entry = MockEntry({"dealer": "PGE Obrót", "dealer_tariff": "Dynamic"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertTrue(sensor.is_on)

    def test_static_tariff_g11_is_off(self):
        """Static G11 tariff should return is_on=False."""
        entry = MockEntry({"dealer": "PGE Obrót", "dealer_tariff": "G11"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertFalse(sensor.is_on)

    def test_static_tariff_g12_is_off(self):
        """Static G12 tariff should return is_on=False."""
        entry = MockEntry({"dealer": "Tauron Sprzedaż", "dealer_tariff": "G12"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertFalse(sensor.is_on)

    def test_tauron_dynamic_is_on(self):
        """Tauron dynamic tariff should return is_on=True."""
        entry = MockEntry({"dealer": "Tauron Sprzedaż", "dealer_tariff": "Dynamic"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertTrue(sensor.is_on)

    def test_unknown_dealer_is_off(self):
        """Unknown dealer should default to is_on=False."""
        entry = MockEntry({"dealer": "NonExistent", "dealer_tariff": "G11"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertFalse(sensor.is_on)

    def test_missing_options_is_off(self):
        """Missing dealer/tariff options should default to is_on=False."""
        entry = MockEntry({})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertFalse(sensor.is_on)

    def test_unique_id_format(self):
        """Unique ID should follow the standard format."""
        entry = MockEntry({"dealer": "PGE Obrót", "dealer_tariff": "Dynamic"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertEqual(sensor._attr_unique_id, f"{DOMAIN}_test_entry_{SENSOR_IS_DYNAMIC}")

    def test_service_device_info(self):
        """Binary sensor should be assigned to the service device."""
        entry = MockEntry({"dealer": "PGE Obrót", "dealer_tariff": "Dynamic"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertEqual(
            sensor._attr_device_info,
            {
                "identifiers": {(DOMAIN, "test_entry")},
                "entry_type": "service",
                "name": "TGE RDN Energy Prices",
                "manufacturer": "@szczepuz999",
                "model": "Total Energy Prices",
                "configuration_url": TGE_PAGE_URL,
            },
        )

    def test_extra_state_attributes(self):
        """Extra attributes should include seller and tariff info."""
        entry = MockEntry({"dealer": "PGE Obrót", "dealer_tariff": "Dynamic"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["seller"], "PGE Obrót")
        self.assertEqual(attrs["seller_tariff"], "Dynamic")
        self.assertEqual(attrs["source"], "tariffs.json")

    def test_custom_tariff_is_dynamic(self):
        """Custom tariff is marked as dynamic in tariffs.json."""
        entry = MockEntry({"dealer": "Custom", "dealer_tariff": "Custom"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertTrue(sensor.is_on)

    def test_static_only_seller_is_off(self):
        """Seller with only static tariffs should return is_on=False."""
        entry = MockEntry({"dealer": "Enea", "dealer_tariff": "G11"})
        sensor = TGEDynamicTariffBinarySensor(entry, self.tariffs_data)
        self.assertFalse(sensor.is_on)


class TestCheapElectricityBinarySensor(unittest.TestCase):
    """Test the low-zone tariff indicator."""

    def setUp(self):
        self.tariffs_data = load_tariffs()
        self.holiday_provider = MagicMock()
        self.holiday_provider.is_holiday.return_value = False
        self.holiday_provider.is_calendar_available.return_value = True
        self.entry = MockEntry({
            "distributor": "PGE Dystrybucja",
            "dist_tariff": "G12",
        })
        self.sensor = TGECheapElectricityBinarySensor(
            self.entry, self.tariffs_data, self.holiday_provider
        )

    def test_low_zone_is_cheap(self):
        """G12's night zone is reported as cheap."""
        self.assertEqual(self.sensor._active_zone(datetime(2026, 1, 5, 22)), "low")

    def test_high_zone_is_not_cheap(self):
        """G12's daytime zone is not reported as cheap."""
        self.assertEqual(self.sensor._active_zone(datetime(2026, 1, 5, 12)), "high")

    def test_suggested_entity_id_is_cheap_electricity(self):
        """The entity gets a stable, automation-friendly object ID."""
        self.assertEqual(self.sensor._attr_suggested_object_id, "cheap_electricity")

    def test_g13_off_peak_zone_is_cheap(self):
        """G13's explicitly marked off-peak zone is reported as cheap."""
        entry = MockEntry({
            "dealer": "Tauron Sprzedaż",
            "dealer_tariff": "G13",
            "distributor": "Tauron Dystrybucja",
            "dist_tariff": "G13",
        })
        sensor = TGECheapElectricityBinarySensor(
            entry, self.tariffs_data, self.holiday_provider
        )
        self.assertEqual(sensor._active_zone(datetime(2026, 1, 5, 13)), "off_peak")
        self.assertIn("off_peak", sensor._cheap_zones)

    def test_dynamic_tariff_is_unavailable(self):
        """Dynamic tariffs require a separate price-policy decision."""
        entry = MockEntry({
            "dealer": "PGE Obrót",
            "dealer_tariff": "Dynamic",
            "distributor": "PGE Dystrybucja",
            "dist_tariff": "G12",
        })
        sensor = TGECheapElectricityBinarySensor(
            entry, self.tariffs_data, self.holiday_provider
        )
        self.assertFalse(sensor.available)


if __name__ == "__main__":
    unittest.main()
