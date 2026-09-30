"""Shared entity helpers for TGE RDN."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, TGE_PAGE_URL


SERVICE_NAME = "TGE RDN Energy Prices"
SERVICE_MANUFACTURER = "@szczepuz999"
SERVICE_MODEL = "Total Energy Prices"


def get_service_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the shared Home Assistant service device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        entry_type=DeviceEntryType.SERVICE,
        name=SERVICE_NAME,
        manufacturer=SERVICE_MANUFACTURER,
        model=SERVICE_MODEL,
        configuration_url=TGE_PAGE_URL,
    )
