"""Holiday calendar provider for TGE RDN."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import requests

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

try:
    from homeassistant.helpers.storage import Store
except ImportError:  # pragma: no cover - only for lightweight unit tests without HA installed
    Store = None

from .const import DOMAIN, HOLIDAY_CACHE_TTL_DAYS, HOLIDAY_COUNTRY_CODE, HOLIDAY_API_URLS

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_holiday_cache"


class HolidayCalendarUnavailable(Exception):
    """Raised when holiday data is unavailable for a requested date."""


class HolidayProvider:
    """Fetch and cache public holidays for tariff zone resolution."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the provider."""
        self._hass = hass
        self._store = Store(hass, STORE_VERSION, STORE_KEY) if Store else None
        self._cache: dict[str, Any] = {HOLIDAY_COUNTRY_CODE: {}}
        self._holidays_by_year: dict[int, set[str]] = {}
        self._last_error: str | None = None

    async def async_setup(self, dates: Iterable[date]) -> None:
        """Load cached holidays and refresh missing/stale years."""
        if self._store:
            stored = await self._store.async_load()
            if isinstance(stored, dict):
                self._cache = stored
                self._load_memory_cache()

        await self.async_ensure_years({d.year for d in dates})

    async def async_ensure_years(self, years: Iterable[int]) -> None:
        """Ensure holiday data is available or attempted for the given years."""
        changed = False
        for year in sorted(set(years)):
            if self._is_year_fresh(year):
                continue

            try:
                holidays = await self._hass.async_add_executor_job(self._fetch_year, year)
            except Exception as err:  # noqa: BLE001 - surface API/cache diagnostics, keep HA running
                self._last_error = f"{type(err).__name__}: {err}"
                _LOGGER.warning("Could not refresh holiday calendar for %s: %s", year, err)
                continue

            self._set_year(year, holidays)
            changed = True

        if changed and self._store:
            await self._store.async_save(self._cache)

    def is_holiday(self, day: date) -> bool:
        """Return whether the date is a public holiday."""
        holidays = self._holidays_by_year.get(day.year)
        if holidays is None:
            raise HolidayCalendarUnavailable(f"No cached holidays for {day.year}")
        return day.isoformat() in holidays

    def is_calendar_available(self, day: date) -> bool:
        """Return whether the requested year is loaded."""
        return day.year in self._holidays_by_year

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Return diagnostics for sensor attributes."""
        country_cache = self._cache.get(HOLIDAY_COUNTRY_CODE, {})
        years = sorted(self._holidays_by_year)
        last_updates = {
            year: country_cache.get(str(year), {}).get("fetched_at")
            for year in years
        }
        return {
            "holiday_source": "nager_cache",
            "holiday_calendar_available": bool(years),
            "holiday_cache_years": years,
            "holiday_cache_last_update": last_updates,
            "holiday_error": self._last_error,
        }

    def _load_memory_cache(self) -> None:
        """Populate fast lookup sets from persisted cache."""
        self._holidays_by_year = {}
        for year, payload in self._cache.get(HOLIDAY_COUNTRY_CODE, {}).items():
            holidays = payload.get("holidays") if isinstance(payload, dict) else None
            if isinstance(holidays, list):
                self._holidays_by_year[int(year)] = set(holidays)

    def _is_year_fresh(self, year: int) -> bool:
        """Return whether cache for a year exists and is within TTL."""
        if year not in self._holidays_by_year:
            return False

        payload = self._cache.get(HOLIDAY_COUNTRY_CODE, {}).get(str(year), {})
        fetched_at = payload.get("fetched_at")
        if not fetched_at:
            return False

        try:
            fetched = datetime.fromisoformat(fetched_at)
        except ValueError:
            return False

        if fetched.tzinfo is None:
            fetched = dt_util.as_local(fetched)

        return dt_util.now() - fetched < timedelta(days=HOLIDAY_CACHE_TTL_DAYS)

    def _set_year(self, year: int, holidays: list[str]) -> None:
        """Persist and index holidays for a year."""
        self._cache.setdefault(HOLIDAY_COUNTRY_CODE, {})[str(year)] = {
            "fetched_at": dt_util.now().isoformat(),
            "source": "nager",
            "holidays": sorted(set(holidays)),
        }
        self._holidays_by_year[year] = set(holidays)
        self._last_error = None

    def _fetch_year(self, year: int) -> list[str]:
        """Fetch holidays for a year from Nager Holidays."""
        errors = []
        for url_template in HOLIDAY_API_URLS:
            url = url_template.format(year=year, country=HOLIDAY_COUNTRY_CODE)
            try:
                response = requests.get(url, timeout=20, headers={"User-Agent": "TGE RDN Home Assistant Integration"})
                response.raise_for_status()
                return self._parse_holidays(response.json())
            except Exception as err:  # noqa: BLE001 - try all configured endpoints
                errors.append(f"{url}: {err}")

        raise HolidayCalendarUnavailable("; ".join(errors))

    @staticmethod
    def _parse_holidays(payload: Any) -> list[str]:
        """Parse public holiday dates from Nager response."""
        if not isinstance(payload, list):
            raise ValueError("Holiday API response is not a list")

        holidays: list[str] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("date"):
                continue

            types = item.get("holidayTypes") or item.get("types") or ["Public"]
            if "Public" in types:
                holidays.append(item["date"])

        if not holidays:
            raise ValueError("Holiday API response did not contain public holidays")
        return holidays
