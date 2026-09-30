"""TGE RDN sensor platform v2.1.6 - Web Table Parsing with Date Fix."""
import logging
import asyncio
import re
import json
import os
from datetime import datetime, timedelta, time, date
from typing import Dict, List, Optional, Any

try:
    import requests
    from bs4 import BeautifulSoup
    REQUIRED_LIBRARIES_AVAILABLE = True
except ImportError as err:
    REQUIRED_LIBRARIES_AVAILABLE = False
    IMPORT_ERROR = str(err)

import voluptuous as vol
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    TGE_PAGE_URL,
    UNIT_PLN_MWH,
    UNIT_PLN_KWH,
    UNIT_EUR_MWH,
    UNIT_EUR_KWH,
    CONF_UNIT,
    DEFAULT_UNIT,
    CONF_DEALER,
    CONF_DISTRIBUTOR,
    CONF_DEALER_TARIFF,
    CONF_DIST_TARIFF,
    CONF_EXCHANGE_FEE,
    DEFAULT_EXCHANGE_FEE,
    CONF_VAT_RATE,
    DEFAULT_VAT_RATE,
    CONF_DIST_LOW,
    DEFAULT_DIST_LOW,
    CONF_DIST_MED,
    DEFAULT_DIST_MED,
    CONF_DIST_HIGH,
    DEFAULT_DIST_HIGH,
    CONF_FIXED_TRANSMISSION_FEE,
    DEFAULT_FIXED_TRANSMISSION_FEE,
    CONF_TRANSITIONAL_FEE,
    DEFAULT_TRANSITIONAL_FEE,
    CONF_SUBSCRIPTION_FEE,
    DEFAULT_SUBSCRIPTION_FEE,
    CONF_CAPACITY_FEE,
    DEFAULT_CAPACITY_FEE,
    CONF_TRADE_FEE,
    DEFAULT_TRADE_FEE,
    UPDATE_INTERVAL_CURRENT,
    UPDATE_INTERVAL_NEXT_DAY,
    UPDATE_INTERVAL_FREQUENT,
)
from .entity import get_service_device_info

_LOGGER = logging.getLogger(__name__)

def load_tariffs():
    """Load tariffs from JSON file."""
    path = os.path.join(os.path.dirname(__file__), "tariffs.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sellers": [], "distributors": []}


def _easter(y: int):
    """Calculate Easter Sunday date for a given year."""
    a = y % 19
    b = y // 100
    c = y % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mon = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(y, mon, day)


def is_polish_holiday(d: date) -> bool:
    """Check if a date is a Polish public holiday."""
    fixed = [(1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 25), (12, 26)]
    if (d.month, d.day) in fixed:
        return True
    easter_date = _easter(d.year)
    moveable = [
        easter_date,
        easter_date + timedelta(days=1),
        easter_date + timedelta(days=49),
        easter_date + timedelta(days=60),
    ]
    return d in moveable


def _matches_season(rule_season: str, dt: datetime) -> bool:
    """Check if datetime falls within the rule's season."""
    if rule_season == "all":
        return True
    month = dt.month
    if rule_season == "summer":
        return 4 <= month <= 9
    if rule_season == "winter":
        return month <= 3 or month >= 10
    return True


def _matches_days(rule_days: str, dt: datetime, is_holiday: bool) -> bool:
    """Check if datetime matches the rule's day filter."""
    if rule_days == "all":
        return True
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    if rule_days == "holidays":
        return is_holiday
    if rule_days == "weekends":
        return weekday in (5, 6)
    if rule_days == "workdays":
        return weekday not in (5, 6) and not is_holiday
    return True


def resolve_zone(zones: dict, dt: datetime, is_holiday: bool) -> tuple:
    """Resolve the active zone name and rate for a given datetime.

    Args:
        zones: Zone map from tariffs.json (zone_name -> {rate, schedule}).
        dt: The datetime to evaluate.
        is_holiday: Whether the date is a Polish public holiday.

    Returns:
        Tuple of (zone_name: str, rate: float).
        Falls back to the default zone if no time-based rule matches.
    """
    default_zone = None
    default_rate = 0.0
    hour = dt.hour

    for zone_name, zone_def in zones.items():
        rate = zone_def.get("rate", 0.0)
        for rule in zone_def.get("schedule", []):
            if rule.get("default"):
                default_zone = zone_name
                default_rate = rate
                continue

            rule_hours = rule.get("hours", [])
            rule_days = rule.get("days", "all")
            rule_season = rule.get("season", "all")
            rule_months = rule.get("months")

            if hour not in rule_hours:
                continue
            if not _matches_days(rule_days, dt, is_holiday):
                continue
            if rule_months:
                if dt.month not in rule_months:
                    continue
            elif not _matches_season(rule_season, dt):
                continue

            return (zone_name, rate)

    return (default_zone or "all", default_rate)

class DataNotAvailableError(Exception):
    """Custom exception for missing data."""
    pass


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors from config entry."""

    if not REQUIRED_LIBRARIES_AVAILABLE:
        _LOGGER.error(f"Missing libraries: {IMPORT_ERROR}")
        raise Exception(f"Missing libraries: {IMPORT_ERROR}")

    _LOGGER.info("🚀 TGE RDN v2.1.6 - Starting integration...")
    _LOGGER.info("📄 Source: https://tge.pl/energia-elektryczna-rdn")
    _LOGGER.info("✅ Web Table Parsing + DST Support Enabled")
    _LOGGER.info("💰 Price Source: Fixing I (primary)")

    tariffs_data = await hass.async_add_executor_job(load_tariffs)

    coordinator = TGERDNDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entities = [
        TGERDNSensor(coordinator, entry, "current_price", tariffs_data),
        TGERDNSensor(coordinator, entry, "next_hour_price", tariffs_data),
        TGERDNSensor(coordinator, entry, "daily_average", tariffs_data),
    ]

    # Fixed monthly fees
    fees = [
        ("fixed_transmission_fee", "Fixed Transmission Fee", CONF_FIXED_TRANSMISSION_FEE, DEFAULT_FIXED_TRANSMISSION_FEE),
        ("transitional_fee", "Transitional Fee", CONF_TRANSITIONAL_FEE, DEFAULT_TRANSITIONAL_FEE),
        ("subscription_fee", "Subscription Fee", CONF_SUBSCRIPTION_FEE, DEFAULT_SUBSCRIPTION_FEE),
        ("capacity_fee", "Capacity Fee", CONF_CAPACITY_FEE, DEFAULT_CAPACITY_FEE),
        ("trade_fee", "Trade Fee", CONF_TRADE_FEE, DEFAULT_TRADE_FEE),
    ]

    for fee_id, fee_name, conf_key, def_val in fees:
        entities.append(TGEFixedFeeSensor(entry, fee_id, fee_name, conf_key, def_val, tariffs_data))

    async_add_entities(entities, True)
    async_track_time_interval(hass, coordinator.hourly_update_callback, timedelta(minutes=5))

    if coordinator.data:
        today_ok = coordinator.data.get("today") is not None
        tomorrow_ok = coordinator.data.get("tomorrow") is not None
        _LOGGER.info(f"✅ TGE RDN v2.1.6 ready! Today: {'✅' if today_ok else '❌'}, Tomorrow: {'✅' if tomorrow_ok else '❌'}")


class TGERDNDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for TGE RDN data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.entry = entry
        self.tomorrow_data_available = False
        self.last_tomorrow_check = None
        self.last_hour_updated = datetime.now().hour

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._get_update_interval()),
        )

    @callback
    async def hourly_update_callback(self, now: datetime) -> None:
        """Check for hour changes."""
        current_hour = now.hour
        if self.last_hour_updated != current_hour:
            _LOGGER.info(f"⏰ Hour boundary: {self.last_hour_updated}:XX → {current_hour}:XX")
            self.last_hour_updated = current_hour
            await self.async_request_refresh()

    def _get_update_interval(self) -> int:
        """Get update interval based on time."""
        now = datetime.now()
        current_time = now.time()

        if time(0, 5) <= current_time <= time(1, 0):
            return UPDATE_INTERVAL_CURRENT
        elif time(11, 0) <= current_time <= time(12, 0):
            return UPDATE_INTERVAL_FREQUENT
        elif time(12, 0) <= current_time <= time(16, 0):
            return UPDATE_INTERVAL_NEXT_DAY
        else:
            return 1800

    def _parse_html_table_for_date(self, target_date: datetime) -> Optional[Dict[str, Any]]:
        """Parse TGE HTML table to extract price data for specific date."""
        try:
            date_str = target_date.strftime("%Y-%m-%d")
            # IMPORTANT: The TGE website shows prices for the NEXT day after dateShow parameter
            # To get prices for date X, we need to request dateShow=X-1 (previous day)
            previous_day = target_date - timedelta(days=1)
            date_param = previous_day.strftime("%d-%m-%Y")
            url_with_date = f"{TGE_PAGE_URL}?dateShow={date_param}"
            _LOGGER.debug(f"🔍 Fetching table data for: {date_str} from {url_with_date}")

            response = requests.get(url_with_date, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if response.status_code != 200:
                _LOGGER.warning(f"Failed to access TGE page: HTTP {response.status_code}")
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the main table
            table = soup.find('table', {'id': 'rdn'})
            if not table:
                table = soup.find('table', class_='table-rdb')
            
            if not table:
                _LOGGER.warning("Could not find price table")
                return None
            
            # Parse rows
            rows = table.find_all('tr')
            hourly_data = []
            negative_hours = 0
            
            for row in rows[2:]:  # Skip header rows
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                # First cell contains date and hour: "2025-11-22_H01"
                date_hour_text = cells[0].get_text(strip=True)
                
                # Skip quarter-hour entries
                if '_Q' in date_hour_text:
                    continue
                
                # Parse date and hour: format 2025-11-22_H01 or 2025-11-22_H02a
                match = re.match(r'(\d{4}-\d{2}-\d{2})_H(\d{2})([a-z]?)', date_hour_text)
                if not match:
                    continue
                
                row_date_str = match.group(1)
                hour_num = int(match.group(2))
                dst_marker = match.group(3)
                
                # Only process rows for target date
                if row_date_str != date_str:
                    continue
                
                # Parse price - try multiple columns
                price = None
                
                # Try Fixing I price (column 2) - PRIMARY SOURCE
                if len(cells) > 2:
                    price_text = cells[2].get_text(strip=True)
                    if price_text and price_text != '-':
                        price_text = price_text.replace(',', '.').replace(' ', '')
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass
                
                # If no Fixing I, try Fixing II price (column 7)
                if price is None and len(cells) > 7:
                    price_text = cells[7].get_text(strip=True)
                    if price_text and price_text != '-':
                        price_text = price_text.replace(',', '.').replace(' ', '')
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass
                
                # If still no price, try weighted average from all trading (column 13)
                if price is None and len(cells) > 13:
                    price_text = cells[13].get_text(strip=True)
                    if price_text and price_text != '-':
                        price_text = price_text.replace(',', '.').replace(' ', '')
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass
                
                if price is None:
                    continue
                
                if price < 0:
                    negative_hours += 1
                
                hour_datetime = target_date.replace(
                    hour=hour_num - 1,  # H01 = 00:00-01:00
                    minute=0,
                    second=0,
                    microsecond=0
                )
                
                hourly_data.append({
                    'time': hour_datetime.isoformat(),
                    'hour': hour_num,
                    'price': price,
                    'is_negative': price < 0,
                    'dst_marker': dst_marker
                })
            
            if not hourly_data:
                _LOGGER.debug(f"No data for {date_str}")
                return None
            
            # Sort by hour
            hourly_data.sort(key=lambda x: x['hour'])
            
            # Calculate statistics
            prices = [item['price'] for item in hourly_data]
            
            result = {
                "date": target_date.date().isoformat(),
                "hourly_data": hourly_data,
                "average_price": sum(prices) / len(prices) if prices else 0,
                "min_price": min(prices) if prices else 0,
                "max_price": max(prices) if prices else 0,
                "total_hours": len(hourly_data),
                "negative_hours": negative_hours,
            }
            
            _LOGGER.debug(f"✅ Found {len(hourly_data)} hours for {date_str}")
            return result
            
        except Exception as e:
            _LOGGER.error(f"Error parsing table for {target_date.date()}: {e}")
            return None

    async def async_config_entry_first_refresh(self) -> None:
        """First refresh with immediate fetch."""
        try:
            now = datetime.now()
            _LOGGER.info(f"📡 Initial fetch for {now.date()}")

            today_data = await self._fetch_day_data(now, "today")
            tomorrow = now + timedelta(days=1)
            tomorrow_data = await self._fetch_day_data(tomorrow, "tomorrow")

            if tomorrow_data:
                self.tomorrow_data_available = True
                self.last_tomorrow_check = now

            self.data = {
                "today": today_data,
                "tomorrow": tomorrow_data,
                "last_update": now,
            }
        except Exception as err:
            _LOGGER.error(f"Error during initial fetch: {err}")

        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from TGE."""
        if not REQUIRED_LIBRARIES_AVAILABLE:
            raise UpdateFailed(f"Libraries not available: {IMPORT_ERROR}")

        try:
            now = datetime.now()
            today_data = await self._fetch_day_data(now, "today")
            tomorrow_data = await self._handle_tomorrow_data(now)

            return {
                "today": today_data,
                "tomorrow": tomorrow_data,
                "last_update": now,
            }
        except Exception as err:
            _LOGGER.error(f"Update error: {err}")
            raise UpdateFailed(str(err))

    async def _handle_tomorrow_data(self, now: datetime) -> Optional[Dict[str, Any]]:
        """Handle tomorrow data with preservation."""
        current_time = now.time()

        should_fetch = (
            time(12, 0) <= current_time <= time(16, 0) or
            (time(16, 0) < current_time < time(22, 0) and not self.tomorrow_data_available)
        )

        if should_fetch:
            tomorrow = now + timedelta(days=1)
            new_data = await self._fetch_day_data(tomorrow, "tomorrow")

            if new_data:
                if not self.tomorrow_data_available:
                    _LOGGER.info(f"🎉 Tomorrow data available!")
                self.tomorrow_data_available = True
                self.last_tomorrow_check = now
                return new_data
            elif self.data and self.data.get("tomorrow"):
                return self.data.get("tomorrow")
            else:
                if current_time.hour >= 12:
                    _LOGGER.info(f"Tomorrow data not yet available")
                return None
        elif self.data and self.data.get("tomorrow"):
            return self.data.get("tomorrow")

        return None

    async def _fetch_day_data(
        self, date: datetime, day_type: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch data for specific date from HTML table."""
        try:
            _LOGGER.debug(f"📥 Fetching {day_type} from HTML table...")
            
            result = await self.hass.async_add_executor_job(
                self._parse_html_table_for_date, date
            )

            if not result:
                _LOGGER.debug(f"No data for {day_type} ({date.date()})")
                return None

            hours = len(result.get('hourly_data', []))
            avg = result.get('average_price', 0)
            _LOGGER.info(f"✅ {day_type.title()} ({date.date()}): {hours}h, avg {avg:.2f}")

            return result
        except DataNotAvailableError:
            return None
        except Exception as err:
            _LOGGER.error(f"Error fetching {day_type}: {err}")
            return None




# Polish entity names (fixed, not translated)
ENTITY_NAMES_PL = {
    "current_price": "Aktualna cena",
    "next_hour_price": "Cena w następnej godzinie",
    "daily_average": "Średnia dzienna",
    "fixed_transmission_fee": "Stała opłata przesyłowa",
    "transitional_fee": "Opłata przejściowa",
    "subscription_fee": "Opłata abonamentowa",
    "capacity_fee": "Opłata mocowa",
    "trade_fee": "Opłata handlowa",
}


class TGEFixedFeeSensor(SensorEntity):
    """Sensor for fixed monthly fees."""

    def __init__(self, entry: ConfigEntry, fee_id: str, fee_name: str, config_key: str, default_val: float, tariffs_data: dict = None) -> None:
        """Initialize fee sensor."""
        self._entry = entry
        self._fee_id = fee_id
        self._config_key = config_key
        self._default_val = default_val
        self._attr_has_entity_name = True
        self._attr_name = ENTITY_NAMES_PL.get(fee_id, fee_name)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{fee_id}"
        self._attr_device_info = get_service_device_info(entry)
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_icon = "mdi:cash"
        self._tariffs_data = tariffs_data if tariffs_data is not None else load_tariffs()

    def _load_fee(self) -> float:
        """Load fee value from tariffs data based on selected distributor/seller."""
        opts = self._entry.options

        # trade_fee comes from seller tariff
        if self._fee_id == "trade_fee":
            dealer = opts.get(CONF_DEALER)
            dealer_tariff = opts.get(CONF_DEALER_TARIFF)
            if dealer and dealer_tariff:
                for s in self._tariffs_data.get("sellers", []):
                    if s["name"] == dealer:
                        for t in s.get("tariffs", []):
                            if t["name"] == dealer_tariff:
                                return t.get("trade_fee", self._default_val)
            return self._default_val

        # Other fixed fees come from distributor tariff
        dist = opts.get(CONF_DISTRIBUTOR)
        dist_tariff = opts.get(CONF_DIST_TARIFF)
        if dist and dist_tariff:
            for d in self._tariffs_data.get("distributors", []):
                if d["name"] == dist:
                    for t in d.get("tariffs", []):
                        if t["name"] == dist_tariff:
                            return t.get("fixed_fees", {}).get(self._fee_id, self._default_val)
        return self._default_val

    @property
    def native_value(self) -> float:
        """Return fee value gross (VAT applied to netto tariffs data)."""
        vat = self._entry.options.get(CONF_VAT_RATE, DEFAULT_VAT_RATE)
        return self._load_fee() * (1 + vat)

    @property
    def state(self) -> float:
        """Return fee value for test environments that inspect state directly."""
        return self.native_value


class TGERDNSensor(CoordinatorEntity, SensorEntity):
    """TGE RDN sensor."""

    def __init__(self, coord, entry: ConfigEntry, sensor_type: str, tariffs_data: dict = None) -> None:
        """Initialize sensor."""
        super().__init__(coord)
        self._coord = coord
        self._entry = entry
        self._sensor_type = sensor_type
        self._attr_has_entity_name = True
        self._attr_name = ENTITY_NAMES_PL.get(sensor_type, sensor_type)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sensor_type}"
        self._attr_device_info = get_service_device_info(entry)
        self._last_hour = None

        opts = entry.options
        self._unit = opts.get(CONF_UNIT, DEFAULT_UNIT)
        self._vat = opts.get(CONF_VAT_RATE, DEFAULT_VAT_RATE)

        if tariffs_data is None:
            tariffs_data = load_tariffs()

        # Load seller tariff info
        self._is_dynamic = False
        self._seller_prices: Dict[str, float] = {}
        self._negative_prices_allowed = False
        dealer_name = opts.get(CONF_DEALER)
        dealer_tariff_name = opts.get(CONF_DEALER_TARIFF)
        if dealer_name and dealer_tariff_name:
            for s in tariffs_data.get("sellers", []):
                if s["name"] == dealer_name:
                    self._negative_prices_allowed = s.get("negative_prices_allowed", False)
                    for t in s.get("tariffs", []):
                        if t["name"] == dealer_tariff_name:
                            self._is_dynamic = t.get("is_dynamic", False)
                            self._seller_prices = t.get("energy_prices_netto_mwh", {})
                            break
                    break

        # Exchange fee only applies for dynamic tariffs
        self._fee = opts.get(CONF_EXCHANGE_FEE, DEFAULT_EXCHANGE_FEE) if self._is_dynamic else 0.0

        # Load distribution zone schedule from tariffs.json
        self._zones = None
        dist_name = opts.get(CONF_DISTRIBUTOR)
        dist_tariff_name = opts.get(CONF_DIST_TARIFF)
        if dist_name and dist_tariff_name:
            for d in tariffs_data.get("distributors", []):
                if d["name"] == dist_name:
                    for t in d.get("tariffs", []):
                        if t["name"] == dist_tariff_name:
                            self._zones = t.get("zones")
                            break
                    break

        # Fallback for legacy configs without zones in JSON
        if not self._zones:
            dl = opts.get(CONF_DIST_LOW, DEFAULT_DIST_LOW)
            self._zones = {"all": {"rate": dl, "schedule": [{"default": True}]}}

    @property
    def available(self) -> bool:
        """Return if available."""
        return REQUIRED_LIBRARIES_AVAILABLE and super().available

    @property
    def native_unit_of_measurement(self) -> str:
        """Return unit."""
        return self._unit

    @property
    def state(self) -> Optional[float]:
        """Return state."""
        if not REQUIRED_LIBRARIES_AVAILABLE or not self.coordinator.data:
            return None
        try:
            h = datetime.now().hour
            if self._sensor_type == "current_price" and self._last_hour and self._last_hour != h:
                _LOGGER.info(f"⏰ Current price: {self._last_hour}:XX → {h}:XX")
            self._last_hour = h
            return self._calc()
        except Exception as err:
            _LOGGER.error(f"Error: {err}")
            return None

    def _resolve(self, when) -> tuple:
        """Resolve (zone_name, dist_rate, energy_price_netto) for given time."""
        try:
            local = when.astimezone() if hasattr(when, 'astimezone') else when
        except Exception:
            local = when
        holiday = is_polish_holiday(local.date())
        zone_name, dist_rate = resolve_zone(self._zones, local, holiday)
        if self._is_dynamic or not self._seller_prices:
            energy_price = None  # caller must use TGE price
        else:
            energy_price = self._seller_prices.get(zone_name)
            if energy_price is None:
                energy_price = self._seller_prices.get("all")
        return zone_name, dist_rate, energy_price

    def _compute_total(self, tge_price: float, when) -> float:
        """Compute total price in PLN/MWh netto+VAT for given TGE price and time."""
        zone_name, dist_rate, seller_price = self._resolve(when)
        if seller_price is not None:
            base = seller_price
        else:
            base = tge_price if self._negative_prices_allowed else max(0, tge_price)
        subtotal_netto = base + self._fee + dist_rate
        return subtotal_netto * (1 + self._vat)

    def _apply_unit(self, mwh: float) -> float:
        if self._unit == UNIT_PLN_KWH: return mwh / 1000
        elif self._unit == UNIT_EUR_MWH: return mwh / 4.3
        elif self._unit == UNIT_EUR_KWH: return mwh / 4300
        return mwh

    def _get_dist(self, when) -> float:
        """Distribution rate logic — delegates to resolve_zone()."""
        _zone_name, rate, _ep = self._resolve(when)
        return rate

    def _is_holiday(self, d: date) -> bool:
        """Check if Polish holiday."""
        return is_polish_holiday(d)

    def _is_working_day(self) -> bool:
        """Check if today is a normal working day (not weekend or holiday)."""
        today = datetime.now().date()
        if today.weekday() in (5, 6):
            return False
        return not is_polish_holiday(today)

    def _calc(self) -> Optional[float]:
        """Calculate value."""
        d = self.coordinator.data
        n = datetime.now()

        if self._sensor_type == "current_price":
            td = d.get("today")
            if not td or not td.get("hourly_data"):
                return None
            h = n.hour + 1
            for x in td["hourly_data"]:
                if x["hour"] == h:
                    total = self._compute_total(x["price"], n)
                    return self._apply_unit(total)
            return None

        elif self._sensor_type == "next_hour_price":
            nh = n.hour + 2
            next_time = n + timedelta(hours=1)
            if nh > 24:
                tm = d.get("tomorrow")
                if not tm: return None
                for x in tm.get("hourly_data", []):
                    if x["hour"] == nh - 24:
                        total = self._compute_total(x["price"], next_time)
                        return self._apply_unit(total)
            else:
                td = d.get("today")
                if not td: return None
                for x in td.get("hourly_data", []):
                    if x["hour"] == nh:
                        total = self._compute_total(x["price"], next_time)
                        return self._apply_unit(total)
            return None

        elif self._sensor_type == "daily_average":
            td = d.get("today")
            if not td: return None
            tots = []
            for x in td.get("hourly_data", []):
                hdt = n.replace(hour=(x["hour"]-1)%24, minute=0, second=0, microsecond=0)
                tots.append(self._compute_total(x["price"], hdt))
            if not tots: return None
            return self._apply_unit(sum(tots) / len(tots))

        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return attributes."""
        if not REQUIRED_LIBRARIES_AVAILABLE or not self.coordinator.data:
            return {}
        data = self.coordinator.data

        attrs = {
            "version": "2.1.6",
            "source": TGE_PAGE_URL,
            "dst_support": True,
            "price_source": "Fixing I",
            "last_update": data.get("last_update"),
            "unit": self._unit,
            "is_working_day": self._is_working_day(),
        }

        if data.get("today"):
            today = data["today"]
            n = datetime.now()
            attrs["today"] = {
                "date": today.get("date"),
                "hours": today.get("total_hours"),
                "average": today.get("average_price"),
            }
            attrs["prices_today_gross"] = []
            for h in today.get("hourly_data", []):
                when = n.replace(hour=(h["hour"]-1)%24, minute=0, second=0, microsecond=0)
                total = self._compute_total(h["price"], when)
                attrs["prices_today_gross"].append({
                    "hour": h["hour"],
                    "time": h["time"],
                    "price_tge": h["price"],
                    "price_gross_pln_mwh": round(total, 2),
                    "price_gross": round(self._apply_unit(total), 6),
                })

        if data.get("tomorrow"):
            tomorrow = data["tomorrow"]
            n = datetime.now()
            attrs["tomorrow"] = {
                "date": tomorrow.get("date"),
                "hours": tomorrow.get("total_hours"),
                "average": tomorrow.get("average_price"),
            }
            attrs["prices_tomorrow_gross"] = []
            for h in tomorrow.get("hourly_data", []):
                when = (n + timedelta(days=1)).replace(hour=(h["hour"]-1)%24, minute=0, second=0, microsecond=0)
                total = self._compute_total(h["price"], when)
                attrs["prices_tomorrow_gross"].append({
                    "hour": h["hour"],
                    "time": h["time"],
                    "price_tge": h["price"],
                    "price_gross_pln_mwh": round(total, 2),
                    "price_gross": round(self._apply_unit(total), 6),
                })

        return attrs
