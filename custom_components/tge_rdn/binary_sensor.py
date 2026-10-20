"""TGE RDN binary sensor platform — dynamic tariff indicator."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .const import (
    DOMAIN,
    CONF_DEALER,
    CONF_DEALER_TARIFF,
    CONF_DISTRIBUTOR,
    CONF_DIST_TARIFF,
    SENSOR_IS_DYNAMIC,
    SENSOR_CHEAP_ELECTRICITY,
)
from .entity import get_service_device_info
from .holiday_provider import HolidayCalendarUnavailable, HolidayProvider
from .sensor import resolve_zone

_LOGGER = logging.getLogger(__name__)

ENTITY_NAME_PL = "Taryfa dynamiczna"
CHEAP_ELECTRICITY_NAME_PL = "Tani prąd"


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
        [
            TGEDynamicTariffBinarySensor(entry, tariffs_data),
            TGECheapElectricityBinarySensor(
                entry,
                tariffs_data,
                hass.data[DOMAIN][entry.entry_id]["holiday_provider"],
            ),
        ],
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


class TGECheapElectricityBinarySensor(BinarySensorEntity):
    """Indicate whether the active distribution zone is the low-price zone."""

    def __init__(
        self,
        entry: ConfigEntry,
        tariffs_data: dict,
        holiday_provider: HolidayProvider,
    ) -> None:
        """Initialize the cheap-electricity indicator."""
        self._entry = entry
        self._holiday_provider = holiday_provider
        self._zones = self._load_zones(tariffs_data)
        self._cheap_zones = {
            name for name, definition in self._zones.items() if definition.get("cheap", False)
        }
        self._is_dynamic_tariff = self._load_is_dynamic_tariff(tariffs_data)
        self._attr_has_entity_name = True
        self._attr_name = CHEAP_ELECTRICITY_NAME_PL
        self._attr_suggested_object_id = SENSOR_CHEAP_ELECTRICITY
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{SENSOR_CHEAP_ELECTRICITY}"
        self._attr_device_info = get_service_device_info(entry)
        self._attr_icon = "mdi:cash-clock"
        self._remove_time_listener = None

    def _load_zones(self, tariffs_data: dict) -> dict:
        """Return distribution zones for the configured tariff."""
        opts = self._entry.options
        distributor = opts.get(CONF_DISTRIBUTOR)
        tariff = opts.get(CONF_DIST_TARIFF)
        for item in tariffs_data.get("distributors", []):
            if item.get("name") != distributor:
                continue
            for item_tariff in item.get("tariffs", []):
                if item_tariff.get("name") == tariff:
                    return item_tariff.get("zones", {})
        return {}

    def _load_is_dynamic_tariff(self, tariffs_data: dict) -> bool:
        """Return whether the configured seller tariff uses market prices."""
        opts = self._entry.options
        dealer = opts.get(CONF_DEALER)
        tariff = opts.get(CONF_DEALER_TARIFF)
        for seller in tariffs_data.get("sellers", []):
            if seller.get("name") != dealer:
                continue
            for seller_tariff in seller.get("tariffs", []):
                if seller_tariff.get("name") == tariff:
                    return seller_tariff.get("is_dynamic", False)
        return False

    def _active_zone(self, when: datetime | None = None) -> Optional[str]:
        """Resolve the configured distribution zone for a local datetime."""
        if not self._zones:
            return None
        when = when or datetime.now().astimezone()
        try:
            is_holiday = self._holiday_provider.is_holiday(when.date())
        except HolidayCalendarUnavailable:
            return None
        zone, _rate = resolve_zone(self._zones, when, is_holiday)
        return zone

    @property
    def available(self) -> bool:
        """Return whether the tariff calendar needed for the decision is available."""
        return (
            not self._is_dynamic_tariff
            and bool(self._cheap_zones)
            and self._holiday_provider.is_calendar_available(
            datetime.now().astimezone().date()
            )
        )

    @property
    def is_on(self) -> bool:
        """Return True only for a zone marked as cheap in tariffs.json."""
        return self._active_zone() in self._cheap_zones

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Expose the active tariff zone used to make the decision."""
        opts = self._entry.options
        return {
            "distributor": opts.get(CONF_DISTRIBUTOR, ""),
            "distribution_tariff": opts.get(CONF_DIST_TARIFF, ""),
            "active_zone": self._active_zone(),
            "cheap_zones": sorted(self._cheap_zones),
            "dynamic_tariff": self._is_dynamic_tariff,
            "source": "tariffs.json",
        }

    async def async_added_to_hass(self) -> None:
        """Refresh the state exactly at each tariff-hour boundary."""
        await super().async_added_to_hass()
        self._remove_time_listener = async_track_time_change(
            self.hass, self._async_update_state, minute=0, second=0
        )

    async def async_will_remove_from_hass(self) -> None:
        """Remove the hourly state-update listener."""
        if self._remove_time_listener:
            self._remove_time_listener()
            self._remove_time_listener = None
        await super().async_will_remove_from_hass()

    async def _async_update_state(self, _now: datetime) -> None:
        """Publish the state at an hour boundary without fetching TGE prices."""
        self.async_write_ha_state()
