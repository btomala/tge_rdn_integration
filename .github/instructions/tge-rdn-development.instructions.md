---
description: "Use when writing or modifying Python code for the TGE RDN Home Assistant integration: sensors, scraping, parsing, config flow, tariffs, tests, translations."
applyTo: "custom_components/tge_rdn/**"
---

# TGE RDN Integration — Development Guidelines

## Project Structure

- `sensor.py` — Price sensors (coordinator-based) and fixed fee sensors (standalone)
- `config_flow.py` — Multi-step wizard: Seller → Seller Tariff → Distributor → Distributor Tariff
- `const.py` — All constants grouped by category
- `tariffs.json` — Seller and distributor data with tariffs, fees, and zone schedules
- `strings.json` + `translations/` — Localization (EN + PL)

## Polish Energy Market Domain Model

The integration models the Polish electricity market where a consumer's bill has two independent parts:

1. **Sprzedawca (Seller/Retailer)** — the company selling energy (can be changed by the user)
   - Major sellers: PGE Obrót, Tauron Sprzedaż, Enea, Energa Obrót, E.ON Polska
   - Each seller offers tariff plans; some offer dynamic tariffs (price from TGE RDN stock + operation fee)
   - Seller tariff determines: energy price (PLN/kWh), exchange fee, VAT, trade fee
2. **Dystrybutor (Distributor/DSO)** — the grid operator delivering energy (cannot be changed)
   - Major DSOs: PGE Dystrybucja, Tauron Dystrybucja, Enea Operator, Energa Operator, Stoen Operator
   - Distributor tariff determines: distribution rates per zone, and fixed monthly fees

### Bill Components

**Variable fees (per kWh):**
- Energia czynna (active energy) — seller price, varies by tariff zone
- Opłata sieciowa zmienna (variable network fee) — distribution rate per zone
- Opłata jakościowa (quality fee)
- Opłata kogeneracyjna (cogeneration fee)
- Opłata OZE (renewable energy fee)

**Fixed monthly fees (PLN/month):**
- Opłata sieciowa stała (fixed network fee)
- Opłata abonamentowa (subscription fee)
- Opłata mocowa (capacity fee) — depends on annual consumption tier
- Opłata przejściowa (transitional fee)

### Tariff Types and Zone Logic

Tariffs define time-of-use zones. Zone schedules may differ between sellers and distributors, and some vary by season (summer Apr–Sep vs winter Oct–Mar):

- **G11** (single zone): flat rate 24/7 — always `dist_low`
- **G12** (dual standard): low rate at night 22–06 + midday 13–15; high rate otherwise. Some sellers (PGE) shift midday low to 15–17 in summer
- **G12w** (dual weekend): same as G12 + weekends and public holidays all low
- **G12n** (dual night/PGE-specific): low only 01–05 and Sundays/holidays; high otherwise
- **G13** (triple/Tauron): 3 zones — morning peak (7–13), afternoon peak (seasonal: 19–22 summer, 16–21 winter), off-peak (remaining hours + weekends)
- **G13s** (triple seasonal/Tauron): 3 zones with different rates for workdays vs holidays AND summer vs winter periods
- **G14** (dynamic distribution/Tauron): 4 distribution zones published day-ahead via Kompas Energetyczny (zalecane użytkowanie, normalne, zalecane oszczędzanie, wymagane ograniczenie)
- **Dynamic seller tariff**: energy price = TGE RDN hourly price + seller's operation fee + VAT

### Adding New Sellers, Distributors, or Tariffs

When extending the data model:
1. Add entry in `tariffs.json` under the appropriate seller/distributor with full zone schedule
2. No Python changes needed — the generic zone resolver reads schedules from JSON
3. Update `config_flow.py` only if the wizard UI needs new fields (typically not needed)
4. Update both `translations/en.json` and `translations/pl.json`
5. Write tests covering: zone assignment at boundary hours, seasonal transitions, weekday/weekend/holiday behavior

## Config Flow — Data-Driven Wizard

The config flow is a multi-step wizard driven entirely by `tariffs.json`:
- **Step 1**: Select Seller (Sprzedawca) from JSON list
- **Step 2**: Select Seller Tariff — filtered to tariffs available for chosen seller. Pre-populate default fee values (exchange_fee, vat_rate, trade_fee) from JSON; user may override
- **Step 3**: Select Distributor (Dystrybutor) from JSON list
- **Step 4**: Select Distributor Tariff — filtered to tariffs available for chosen distributor. Pre-populate distribution rates and fixed fees from JSON; user may override

All fee values come pre-filled from `tariffs.json` so users don't need to look them up. A "Custom" option is available for both seller and distributor for users with non-standard contracts.

`OptionsFlow` mirrors all steps for runtime reconfiguration.

All config is stored in `entry.options`, not `entry.data`.

## JSON Data Files — Fully Data-Driven Zone Schedules

`tariffs.json` is the **single source of truth** for all sellers, distributors, and their zone schedules. No per-tariff logic in Python.

### Schema Design Principles

- Every tariff declares its zones as named entries (e.g., `"low"`, `"high"`, `"peak"`, `"off_peak"`) with rates
- Each zone has a `schedule` array of time rules evaluated top-to-bottom (first match wins)
- A time rule specifies: `hours` (range or list), `days` (workdays/weekends/holidays/all), `season` (summer/winter/all), and optionally `months`
- A catch-all rule (`"default": true`) must be the last entry — it's the fallback zone

### Example Zone Schedule Structure

```json
{
  "name": "G12",
  "zones": {
    "low": {
      "rate": 80.0,
      "schedule": [
        { "hours": [22,23,0,1,2,3,4,5], "days": "all", "season": "all" },
        { "hours": [13,14], "days": "all", "season": "winter" },
        { "hours": [15,16], "days": "all", "season": "summer" }
      ]
    },
    "high": {
      "rate": 160.0,
      "schedule": [
        { "default": true }
      ]
    }
  }
}
```

The `hours` field uses 0–23 integers (hour H means the period H:00–H:59). Seasons are defined as `"summer"` (Apr 1 – Sep 30) and `"winter"` (Oct 1 – Mar 31). Days can be `"workdays"`, `"weekends"`, `"holidays"` (Polish public holidays), or `"all"`.

### Generic Zone Resolver (Python)

One function in `sensor.py` resolves the active zone:
```
def resolve_zone(tariff_zones: dict, dt: datetime, is_holiday: bool) -> str
```
It iterates the schedule rules for each zone, checks the current hour/day/season against the rule, and returns the matching zone name. No `if tariff == "G12"` branching — the JSON structure is the logic.

### Data Conventions

- Seller entries contain: name, list of tariffs (each with exchange_fee, vat_rate, trade_fee, `is_dynamic` flag, and optionally energy prices per zone)
- Distributor entries contain: name, list of tariffs (each with zone definitions including schedule + rate, and fixed monthly fees)
- Use placeholder values (0.0) for fields that will be user-provided when the user selects "Custom"
- When a seller offers a dynamic tariff (`"is_dynamic": true`), the energy price comes from TGE RDN hourly data, not from JSON

## Python Conventions

- Use `from __future__ import annotations` in every module
- Type-hint all function signatures: `Optional[Dict[str, Any]]`, `async def`, etc.
- Import order: future → stdlib → third-party (`requests`, `bs4`, `voluptuous`) → HA SDK → local (`.const`)
- Module-level logger: `_LOGGER = logging.getLogger(__name__)`
- Emoji-prefixed log messages (mandatory): 🚀 startup, ✅ success, ❌ error, 📡 fetch, ⏰ timing
- Constants use prefixed names: `CONF_*` (config keys), `DEFAULT_*` (defaults), `UNIT_*` (units)

## Sensor Development

- Price sensors extend `CoordinatorEntity` + `SensorEntity`; fixed-fee sensors extend `SensorEntity` only
- Three price sensor types: `current_price`, `next_hour_price`, `daily_average`
- Five fixed-fee sensors: `fixed_transmission_fee`, `transitional_fee`, `subscription_fee`, `capacity_fee`, `trade_fee`
- Unique ID format: `{DOMAIN}_{entry.entry_id}_{sensor_id}`
- Entity names use Polish as primary language from `ENTITY_NAMES_PL` dict
- `extra_state_attributes` must include `version`, `source`, `price_source`, `last_update`
- Unit conversion: PLN/MWh (default) → PLN/kWh (/1000) → EUR/MWh (/4.3) → EUR/kWh (/4300)

## Coordinator & Update Intervals

- `TGERDNDataUpdateCoordinator` uses adaptive polling intervals:
  - 5 min (00:05–01:00), 10 min (midday), 15 min (afternoon), 30 min (default)
- Preserve `tomorrow_data` if a fetch fails — never discard cached data on error

## Scraping & Parsing Rules

- Source: `https://tge.pl/energia-elektryczna-rdn` with `dateShow` parameter (target_date minus 1 day)
- Use `requests` with `timeout=30` and a User-Agent header
- Parse with `BeautifulSoup`; find table by ID `rdn` or class `table-rdb`
- Skip header rows (`[2:]`) and quarter-hour entries (`_Q00:15`, etc.)
- Hour/date regex: `r'(\d{4}-\d{2}-\d{2})_H(\d{2})([a-z]?)'` — handle DST markers `H02a`/`H02b`
- Price column priority: Fixing I (col 2) → Fixing II (col 7) → weighted average (col 13)
- Normalize prices: comma → dot, strip spaces, preserve negative values
- On HTTP error or parse failure: log with `_LOGGER.warning`/`_LOGGER.error`, return `None` — never raise

## Testing

- **Every code change must include tests** — no PR without corresponding test coverage
- Use `unittest.TestCase` — no pytest
- Mock HA modules with `MagicMock` + `sys.modules` patching
- Use `MockHass` and `MockEntry` helper classes for coordinator tests
- Test method naming: `test_<feature_under_test>` (e.g., `test_single_tariff_g11`)
- Required test cases for every feature:
  - Normal case (happy path)
  - Edge case (DST transitions, midnight boundary, missing data, seasonal switchover)
  - Error case (network failure, malformed HTML, missing JSON keys)
- For tariff logic: test zone assignment at every boundary hour, both workdays and weekends/holidays, both seasons

## HACS Compatibility

- Minimum HA version: `2023.1.0` — do not use APIs introduced after this version without checking
- Keep `manifest.json` and `hacs.json` version fields in sync
- Runtime dependencies: only `requests>=2.28.0` and `beautifulsoup4>=4.11.0`
- `integration_type: "service"`, `iot_class: "cloud_polling"`, `config_flow: true`
- Do not add dependencies on other HA integrations
