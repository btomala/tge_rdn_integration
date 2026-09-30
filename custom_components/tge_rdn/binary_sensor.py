"""TGE RDN binary sensor platform — dynamic tariff indicator."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DEALER,
    CONF_DEALER_TARIFF,
    SENSOR_IS_DYNAMIC,
)
from .entity import get_service_device_info

_LOGGER = logging.getLogger(__name__)

ENTITY_NAME_PL = "Taryfa dynamiczna"


def load_tariffs() -> dict:
    """Load tariffs from JSON file."""
    path = os.path.join(os.path.dirname(__file__), "tariffs.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sellers": [], "distributors": []}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from config entry."""
    tariffs_data = await hass.async_add_executor_job(load_tariffs)
    async_add_entities(
        [TGEDynamicTariffBinarySensor(entry, tariffs_data)],
        True,
    )


class TGEDynamicTariffBinarySensor(BinarySensorEntity):
    """Binary sensor indicating whether the configured seller tariff is dynamic."""

    def __init__(self, entry: ConfigEntry, tariffs_data: dict) -> None:
        """Initialize binary sensor."""
        self._entry = entry
        self._tariffs_data = tariffs_data
        self._attr_has_entity_name = True
        self._attr_name = ENTITY_NAME_PL
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{SENSOR_IS_DYNAMIC}"
        self._attr_device_info = get_service_device_info(entry)
        self._attr_icon = "mdi:lightning-bolt"

    def _resolve_is_dynamic(self) -> bool:
        """Look up is_dynamic flag from tariffs data for the selected seller tariff."""
        opts = self._entry.options
        dealer = opts.get(CONF_DEALER)
        dealer_tariff = opts.get(CONF_DEALER_TARIFF)
        if dealer and dealer_tariff:
            for seller in self._tariffs_data.get("sellers", []):
                if seller["name"] == dealer:
                    for tariff in seller.get("tariffs", []):
                        if tariff["name"] == dealer_tariff:
                            return tariff.get("is_dynamic", False)
                    break
        return False

    @property
    def is_on(self) -> bool:
        """Return True if the current seller tariff is dynamic."""
        return self._resolve_is_dynamic()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra attributes."""
        opts = self._entry.options
        return {
            "seller": opts.get(CONF_DEALER, ""),
            "seller_tariff": opts.get(CONF_DEALER_TARIFF, ""),
            "source": "tariffs.json",
        }
