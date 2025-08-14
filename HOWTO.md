# Creating a Compliant Adapter

> **Mission:** Adapters describe *your game’s stats*; the PRI engine normalizes and scores them. Follow this doc exactly.

---

## 0) Repo placement

```
StatLine/
  how-to.md        ← this file (top level)
  statline/
    core/
      adapters/
        defs/
          example.yaml
```

---

## 1) Metadata (required)

Keys: `key`, `version`
Optional: `aliases`, `title`

* **`key`**: unique ID, kebab/snake case (e.g., `valorant`, `legacy`).
* **`version`**: semver. Bump **major** for metric/bucket/clamp overhauls; **minor** for adding metrics/buckets; **patch** for bugfixes.
* **`aliases`**: list of alternate names to help auto-detection.
* **`title`**: human-readable label.

---

## 2) Dimensions (optional)

For grouping/filters in reports: `map`, `side`, `role`, `mode`, etc.

---

## 3) Buckets (required)

Define 3–6 semantic categories. Buckets are where weights apply.

---

## 4) Metrics (required)

Each metric:

* Belongs to one bucket
* Has realistic `clamp: [min, max]`
* Optional `invert: true` for penalty metrics

Use rates/ratios over totals to avoid match-length bias.

---

## 5) Efficiency (optional)

Make/attempt pairs converted to percentage internally.

---

## 6) Mapping (required)

Map raw input row (`raw`) to your `metrics.key` values.

---

## 7) Weights (optional)

Bucket weights by preset (e.g., `pri`, `mvp`). Engine normalizes automatically.

---

## 8) Penalties (optional)

Extra scaling for negative influence in specific buckets.

---

## 9) Sniff (optional)

Header hints for auto-selecting adapter.

---

## 10) Versioning

Major = structure change, Minor = additions/meaningful clamp shift, Patch = minor fixes.

---

## 11) Validation checklist

* Metrics match mapping keys
* Buckets exist for all metrics
* Clamps are realistic
* Penalty metrics have `invert: true`
* Efficiency pairs have valid fields
* Weights reference existing buckets
* Sniff headers match actual data
* All divides are guarded
* Use rates for match-length-varying stats

---

## 12) FAQ

**Q:** Why rates?
**A:** Totals inflate long matches.

**Q:** Must weights sum to 1?
**A:** No, engine normalizes.

**Q:** Low mistakes as positive?
**A:** No, use `invert: true`.

**Q:** Dimensions required?
**A:** Only if filtering/aggregation needed.

---

## 13) Future hooks (don’t use until supported)

* Metric transforms
* Per-dimension clamps
* Per-metric multipliers
* Team-factor modes in adapter

---

## 14) Minimal starter template

```yaml
key: your_game
version: 0.1.0

buckets:
  scoring: {}
  impact: {}
  utility: {}
  survival: {}
  discipline: {}

metrics:
  - { key: kpr,        bucket: scoring,    clamp: [0, 1.2] }
  - { key: adr,        bucket: impact,     clamp: [0, 300] }
  - { key: kast_pct,   bucket: survival,   clamp: [0.5, 1.0] }
  - { key: plants_r,   bucket: utility,    clamp: [0, 0.3] }
  - { key: deaths_r,   bucket: discipline, clamp: [0, 1.2], invert: true }

efficiency:
  - { key: acc, make: raw["hits"], attempt: raw["shots"], bucket: impact }

mapping:
  kpr:        (raw["kills"] or 0) / max(raw.get("rounds", 1), 1)
  adr:        (raw["damage"] or 0) / max(raw.get("rounds", 1), 1)
  kast_pct:   (raw["kast"] or 0) / 100
  plants_r:   (raw["plants"] or 0) / max(raw.get("rounds", 1), 1)
  deaths_r:   (raw["deaths"] or 0) / max(raw.get("rounds", 1), 1)

weights:
  pri:
    scoring: 0.30
    impact:  0.28
    utility: 0.16
    survival: 0.16
    discipline: 0.10

sniff:
  require_any_headers: [kills, deaths, damage, rounds, kast]
```
