"""Test the binary sensor for dynamic tariff indicator."""
import sys
import os
import unittest
from unittest.mock import MagicMock

# Mock Home Assistant modules BEFORE importing from custom_components
mock_ha = MagicMock()
sys.modules["homeassistant"] = mock_ha
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()

# Define dummy base class for BinarySensorEntity
class MockBinarySensorEntity:
    pass

sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = MockBinarySensorEntity
sys.modules["homeassistant.helpers.device_registry"].DeviceInfo = dict
sys.modules["homeassistant.helpers.device_registry"].DeviceEntryType.SERVICE = "service"

# Add the custom_components to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from custom_components.tge_rdn.binary_sensor import TGEDynamicTariffBinarySensor, load_tariffs
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
                "name": "Ceny energii",
                "manufacturer": "Towarowa Giełda Energii",
                "model": "Całkowite ceny energii",
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


if __name__ == "__main__":
    unittest.main()
