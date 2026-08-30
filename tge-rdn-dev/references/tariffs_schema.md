# Tariffs JSON Schema Reference

This document defines the complete schema for `custom_components/tge_rdn/tariffs.json`.

> **Migration note**: the current file uses `"dealers"` and `"logic"` types. These will be replaced with the new `"sellers"` + data-driven zone schedule architecture described below.

## Top-Level Structure

```json
{
  "sellers": [ <SellerEntry>, ... ],
  "distributors": [ <DistributorEntry>, ... ]
}
```

---

## SellerEntry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Official Polish name (e.g., `"PGE Obrót"`, `"Tauron Sprzedaż"`) |
| `tariffs` | SellerTariff[] | yes | List of tariff plans offered by this seller |

### SellerTariff

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Tariff code (e.g., `"G11"`, `"G12"`, `"Dynamic"`) |
| `exchange_fee` | float | yes | — | TGE exchange fee in PLN/MWh |
| `vat_rate` | float | yes | — | VAT rate as decimal (e.g., `0.23` = 23%) |
| `trade_fee` | float | yes | — | Trade/handling fee in PLN/MWh |
| `is_dynamic` | boolean | no | `false` | If `true`, energy price comes from TGE RDN hourly data |
| `energy_prices` | ZonePrices | no | — | Fixed energy prices per zone (omit when `is_dynamic: true`) |

### ZonePrices

A map of zone name → price in PLN/kWh:

```json
{ "low": 0.51, "high": 0.67 }
```

For single-zone tariffs (G11), use `"all"`:

```json
{ "all": 0.62 }
```

---

## DistributorEntry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Official Polish name (e.g., `"PGE Dystrybucja"`, `"Stoen Operator"`) |
| `tariffs` | DistributorTariff[] | yes | List of distribution tariffs |

### DistributorTariff

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Tariff code (e.g., `"G11"`, `"G12"`, `"G13s"`) |
| `zones` | ZoneMap | yes | Zone definitions with rates and schedules |
| `fixed_fees` | FixedFees | yes | Monthly fixed charges |

---

## Zone Schedule System

### ZoneMap

A map of zone name → ZoneDefinition. Recommended zone names:

| Convention | Use For |
|------------|---------|
| `"all"` | Single-zone tariffs (G11) |
| `"low"`, `"high"` | Dual-zone tariffs (G12, G12w, G12n) |
| `"off_peak"`, `"mid_peak"`, `"peak"` | Triple-zone tariffs (G13, G13s) |
| `"recommended"`, `"normal"`, `"save"`, `"restrict"` | G14 dynamic distribution |

### ZoneDefinition

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rate` | float | yes | Distribution rate in PLN/MWh |
| `schedule` | ScheduleRule[] | yes | Ordered rules — first match wins |

### ScheduleRule

Two types of rule:

**Time-based rule:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hours` | int[] | yes | — | Hours 0–23 when rule applies (H = H:00–H:59) |
| `days` | string | no | `"all"` | `"workdays"`, `"weekends"`, `"holidays"`, `"all"` |
| `season` | string | no | `"all"` | `"summer"`, `"winter"`, `"all"` |
| `months` | int[] | no | — | Month filter 1–12. Overrides `season` if both present |

**Default rule (catch-all fallback):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `default` | boolean | yes | Must be `true` |

**Evaluation**: For a given datetime + is_holiday flag, iterate all zones in order. For each zone, check schedule rules top-to-bottom. Return the first zone whose rule matches. The zone with `{ "default": true }` catches everything else.

### Season Definitions

| Season | Date Range |
|--------|------------|
| `"summer"` | April 1 – September 30 |
| `"winter"` | October 1 – March 31 |
| `"all"` | Year-round |

### Day Definitions

| Day Type | Meaning |
|----------|---------|
| `"workdays"` | Mon–Fri, excluding Polish public holidays |
| `"weekends"` | Sat–Sun |
| `"holidays"` | Polish public holidays (any day of week) |
| `"all"` | Every day |

### Polish Public Holidays

| Date | Name |
|------|------|
| January 1 | Nowy Rok |
| January 6 | Trzech Króli |
| Easter Sunday | Wielkanoc (movable) |
| Easter Monday | Poniedziałek Wielkanocny (movable) |
| May 1 | Święto Pracy |
| May 3 | Święto Konstytucji 3 Maja |
| Corpus Christi | Boże Ciało (movable, 60 days after Easter) |
| August 15 | Wniebowzięcie NMP |
| November 1 | Wszystkich Świętych |
| November 11 | Święto Niepodległości |
| December 25 | Boże Narodzenie |
| December 26 | Drugi dzień Bożego Narodzenia |

### FixedFees

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fixed_transmission_fee` | float | yes | Opłata sieciowa stała (PLN/month) |
| `transitional_fee` | float | yes | Opłata przejściowa (PLN/month) |
| `subscription_fee` | float | yes | Opłata abonamentowa (PLN/month) |
| `capacity_fee` | float | yes | Opłata mocowa (PLN/month) |

---

## Complete Examples

### G11 — Single Zone (Tauron Dystrybucja)

```json
{
  "name": "G11",
  "zones": {
    "all": {
      "rate": 120.0,
      "schedule": [{ "default": true }]
    }
  },
  "fixed_fees": {
    "fixed_transmission_fee": 13.4,
    "transitional_fee": 0.0,
    "subscription_fee": 5.6,
    "capacity_fee": 21.13
  }
}
```

### G12 — Dual Zone with Seasonal Variation (PGE Dystrybucja)

```json
{
  "name": "G12",
  "zones": {
    "low": {
      "rate": 90.0,
      "schedule": [
        { "hours": [22,23,0,1,2,3,4,5], "days": "all", "season": "all" },
        { "hours": [13,14], "days": "all", "season": "winter" },
        { "hours": [15,16], "days": "all", "season": "summer" }
      ]
    },
    "high": {
      "rate": 490.0,
      "schedule": [{ "default": true }]
    }
  },
  "fixed_fees": {
    "fixed_transmission_fee": 12.3,
    "transitional_fee": 0.0,
    "subscription_fee": 5.5,
    "capacity_fee": 21.13
  }
}
```

### G12w — Dual Zone Weekend (Tauron Dystrybucja)

```json
{
  "name": "G12w",
  "zones": {
    "low": {
      "rate": 60.0,
      "schedule": [
        { "hours": [22,23,0,1,2,3,4,5], "days": "all", "season": "all" },
        { "hours": [13,14], "days": "workdays", "season": "all" },
        { "hours": [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23], "days": "weekends", "season": "all" },
        { "hours": [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23], "days": "holidays", "season": "all" }
      ]
    },
    "high": {
      "rate": 460.0,
      "schedule": [{ "default": true }]
    }
  },
  "fixed_fees": {
    "fixed_transmission_fee": 13.4,
    "transitional_fee": 0.0,
    "subscription_fee": 5.6,
    "capacity_fee": 21.13
  }
}
```

### G13 — Triple Zone Seasonal (Tauron Dystrybucja)

```json
{
  "name": "G13",
  "zones": {
    "mid_peak": {
      "rate": 330.0,
      "schedule": [
        { "hours": [7,8,9,10,11,12], "days": "workdays", "season": "all" }
      ]
    },
    "peak": {
      "rate": 540.0,
      "schedule": [
        { "hours": [19,20,21], "days": "workdays", "season": "summer" },
        { "hours": [16,17,18,19,20], "days": "workdays", "season": "winter" }
      ]
    },
    "off_peak": {
      "rate": 50.0,
      "schedule": [{ "default": true }]
    }
  },
  "fixed_fees": {
    "fixed_transmission_fee": 13.4,
    "transitional_fee": 0.0,
    "subscription_fee": 5.6,
    "capacity_fee": 21.13
  }
}
```

### Dynamic Seller Tariff (PGE Obrót)

```json
{
  "name": "Dynamic",
  "exchange_fee": 2.0,
  "vat_rate": 0.23,
  "trade_fee": 5.0,
  "is_dynamic": true
}
```

---

## Validation Rules

1. Every distributor tariff must have **exactly one** zone with `{ "default": true }`
2. No two zones should match the same hour/day/season combination (ambiguity)
3. `hours` values must be integers 0–23
4. `months` values must be integers 1–12
5. `rate` must be non-negative (0.0 allowed for Custom placeholders)
6. Seller and distributor names must be unique within their arrays
7. `"Custom"` entry must exist as the last item for both sellers and distributors
