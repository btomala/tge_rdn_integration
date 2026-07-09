# TGE RDN Integration for Home Assistant

This project is a custom component for Home Assistant that integrates with the Polish energy exchange (TGE RDN) to provide real-time electricity prices. It scrapes the TGE website to fetch the data, calculates prices based on your dealer and distributor tariff, and exposes them as sensors in Home Assistant.

**Version:** 2.1.5

## Features

*   **Real-time Prices:** Fetches hourly electricity prices from [TGE.pl](https://tge.pl/energia-elektryczna-rdn).
*   **Tariff-based Calculations:** Automatically calculates the final cost based on your actual dealer and distributor tariffs (G11, G12, G12w, G13, Dynamic), including VAT, exchange fees, and time-zone-based distribution rates.
*   **Dynamic & Static Tariffs:** Supports both dynamic (TGE spot-price-based) and fixed-price tariffs. For fixed tariffs the seller's contracted energy price is used instead of the TGE price.
*   **Zone-based Distribution Rates:** Automatically resolves the active distribution zone (peak / off-peak / etc.) based on the hour, day type (workday / weekend / holiday), and season (summer / winter).
*   **Negative Price Handling:** Configurable per seller — some sellers (e.g. Pstryk) pass through negative prices; others clamp them to zero.
*   **Pre-populated Fees:** Fixed monthly fees (transmission, transitional, subscription, capacity) are loaded automatically from the selected distributor tariff.
*   **Localization:** Entity names in Polish; configuration dialogs in English and Polish.
*   **Reliable Data:** Uses "Fixing I" prices as the primary source, with automatic fallback to "Fixing II" and the weighted average.
*   **Smart Features:**
    *   **Tomorrow's Prices:** Available from ~12:30 PM.
    *   **Holiday Support:** Automatic detection of Polish national holidays for correct tariff zone resolution.
    *   **DST Support:** Correctly handles 23 h and 25 h days during clock changes.
    *   **Working Day Detection:** Exposes an `is_working_day` attribute for automation logic.

## Installation

The recommended installation method is via [HACS](https://hacs.xyz/).

1.  Open HACS in your Home Assistant instance.
2.  Go to "Integrations" and click "Explore & Download Repositories".
3.  Search for "TGE RDN" and install it.
4.  Restart Home Assistant.

## Configuration

After installation, configure the integration via the UI:

1.  Go to **Settings** → **Devices & Services**.
2.  Click **Add Integration** and search for **TGE RDN**.
3.  **Step 1 — Dealer & Distributor:**
    *   **Dealer (Seller):** Your energy supplier (see supported sellers below).
    *   **Distributor:** Your distribution network operator (see supported distributors below).
    *   **Price Unit:** PLN/kWh, PLN/MWh, EUR/kWh, or EUR/MWh.
    *   **VAT Rate:** Your applicable VAT rate (default: 0.23 for 23 %).
4.  **Step 2 — Tariffs:**
    *   **Dealer Tariff:** The tariff name offered by your seller (e.g. G11, G12, Dynamic).
    *   **Distributor Tariff:** The distribution tariff for your grid area (e.g. G11, G12, G13).
    *   For **dynamic** seller tariffs the exchange fee and trade fee are filled in automatically from the built-in tariff database.
    *   For **static** seller tariffs (G11, G12, G12w, G13) the seller's fixed energy prices are used; TGE spot prices are ignored.

### Supported Sellers

| Seller | Available Tariffs |
|---|---|
| PGE Obrót | G11, G12, G12w, Dynamic |
| Tauron Sprzedaż | G11, G12, G12w, G13, Dynamic |
| Enea | G11, G12 |
| Energa Obrót | G11, G12 |
| E.ON Polska | G11, G12 |
| Pstryk | Dynamic (negative prices allowed) |
| Custom | Custom (dynamic, fully manual) |

### Supported Distributors

| Distributor | Available Tariffs |
|---|---|
| PGE Dystrybucja | G11, G12, G12w |
| Tauron Dystrybucja | G11, G12, G12w, G13 |
| Enea Operator | G11, G12 |
| Energa Operator | G11, G12 |

## Entities Provided

| Entity | Polish name | Description |
|---|---|---|
| `sensor.tge_rdn_current_price` | Aktualna cena | Total cost for the current hour |
| `sensor.tge_rdn_next_hour_price` | Cena w następnej godzinie | Total cost for the next hour |
| `sensor.tge_rdn_daily_average` | Średnia dzienna | Average total price for today |
| `sensor.tge_rdn_fixed_transmission_fee` | Stała opłata przesyłowa | Fixed monthly transmission fee (PLN, gross) |
| `sensor.tge_rdn_transitional_fee` | Opłata przejściowa | Transitional fee (PLN, gross) |
| `sensor.tge_rdn_subscription_fee` | Opłata abonamentowa | Subscription fee (PLN, gross) |
| `sensor.tge_rdn_capacity_fee` | Opłata mocowa | Capacity fee (PLN, gross) |
| `sensor.tge_rdn_trade_fee` | Opłata handlowa | Trade fee (PLN, gross) |

All price sensors expose `prices_today_gross` and `prices_tomorrow_gross` attributes containing hourly breakdowns, as well as `is_working_day`, `price_source`, `dst_support`, and `last_update`.

## Technical Details

*   **Architecture:** Standard Home Assistant custom component using a `DataUpdateCoordinator`.
*   **Dependencies:** `requests`, `beautifulsoup4` (no heavy libraries like pandas).
*   **Data Source:** Parses the HTML table directly from TGE.
*   **Tariff Database:** `tariffs.json` — bundled JSON file with seller and distributor definitions (rates, zone schedules, fixed fees). All rates are netto (VAT applied at runtime).
*   **Update Interval:**
    *   00:05 – 01:00: Every 5 minutes (to catch late updates).
    *   11:00 – 12:00: Every 15 minutes.
    *   12:00 – 16:00: Every 10 minutes (to fetch tomorrow's prices ASAP).
    *   Otherwise: Every 30 minutes.

## Recent Changes

### v2.1.5
*   **Patch Release:** Bumped the integration version for the GitHub release and aligned package metadata across Home Assistant distribution files.

### v2.1.1
*   **Tariff System Overhaul:** Configuration now uses a 2-step flow — select your dealer and distributor, then select the specific tariffs. Rates, zones, and fixed fees are populated automatically from the built-in `tariffs.json` database.
*   **Static Tariff Support:** Non-dynamic tariffs (G11, G12, G12w, G13) use the seller's contracted fixed energy prices instead of TGE spot prices.
*   **Zone-based Distribution:** Distribution rates are resolved automatically using per-tariff zone schedules (hour, day type, season).
*   **Negative Price Handling:** Per-seller configuration for whether negative TGE prices are passed through or clamped to zero.
*   **New Sellers & Distributors:** Added Tauron Sprzedaż (G13 tariff), Pstryk (negative prices), E.ON Polska, Enea Operator, Energa Operator, Tauron Dystrybucja (G13 tariff).
*   **Update Interval:** Changed the default (off-peak) interval from 60 min to 30 min.

### v1.8.5
*   **Localization:** Fixed entity names language.

### v1.8.4
*   **Localization:** Added Polish entity names.
*   **Fixed Fees:** Added support for constant monthly fees (transmission, transitional, subscription, capacity, trade).

### v1.8.2
*   **Data Source:** Switched to "Fixing I" as the primary price source for better accuracy.
*   **Attribute:** Added `price_source` attribute to sensors.

### v1.8.1
*   **Fix:** Corrected date parameter handling in URL to ensure accurate daily data.
*   **Feature:** Added `is_working_day` attribute to current price sensor.

### v1.8.0
*   **Major Overhaul:** Switched from downloading Excel files to direct HTML parsing.
*   **Performance:** Removed `pandas` and `openpyxl` dependencies, significantly reducing size and memory usage.

## Credits

Created by @szczepuz999.