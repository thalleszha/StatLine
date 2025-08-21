# Creating a Compliant Adapter

> **Mission:** Adapters describe *your game's stats*; the PRI engine normalizes and scores them. Follow this document exactly.

---

## 0) Repository Placement

```plaintext
StatLine/
├── HOWTO.md        ← this file (top level)
└── statline/
    └── core/
        └── adapters/
            └── defs/
                └── example.yaml
```

---

## 1) Metadata (required)

**Purpose:** Identifies and labels the adapter so the PRI engine knows what it represents.

Keys:

* **`key`** (required): Unique ID for the adapter, in kebab or snake case. Example: `valorant`, `legacy`.
* **`version`** (required): Semantic version number.

  * **Major**: Structure overhauls (metrics, buckets, clamps changes).
  * **Minor**: Adding new metrics/buckets.
  * **Patch**: Bug fixes or minor adjustments.
* **`aliases`** (optional): Alternative names to help auto-detection. Example: `[ex, sample]`.
* **`title`** (optional): Human-readable game name.

**Example:**

```yaml
key: example_game
version: 0.1.0
aliases: [ex, sample]
title: Example Game
```

---

## 2) Dimensions (optional)

**Purpose:** Define grouping/filtering categories for reports.

These are labels used for breakdowns like per-map, per-role, per-side.

**Example:**

```yaml
dimensions:
  map:   { values: [MapA, MapB, MapC] }
  side:  { values: [Attack, Defense] }
  role:  { values: [Carry, Support, Flex] }
  mode:  { values: [Pro, Ranked, Scrim] }
```

---

## 3) Buckets (required)

**Purpose:** Group metrics into categories that weights apply to.

3–6 categories recommended.

**Example:**

```yaml
buckets:
  scoring: {}
  impact: {}
  utility: {}
  survival: {}
  discipline: {}
```

---

## 4) Metrics (required)

**Purpose:** Define the specific stats tracked in this adapter.

Each metric:

* Belongs to one bucket.
* Has a realistic **`clamp: [min, max]`**.

  * Example: For points per game, `clamp: [0, 60]` means the floor is 0 and ceiling is 60.
  * If your sheets are set up for auto-calculation based on your league's data, clamps may not be necessary.
* Optional `invert: true` for penalty metrics (where lower is better).
* **`source.field`**: Points to the raw field name.

**Example:**

```yaml
metrics:
  - { key: stat3_count, bucket: utility,    clamp: [0, 50],  source: { field: stat3_count } }
  - { key: mistakes,    bucket: discipline, clamp: [0, 25], invert: true, source: { field: mistakes } }
```

---

## 5) Efficiency (optional)

**Purpose:** Define make/attempt pairs that are converted to percentages internally.

Good for ratios like accuracy, win rates, or success rates.

**Example:**

```yaml
efficiency:
  - { key: stat1_per_round, make: raw["stat1_total"], attempt: raw["rounds_played"], bucket: scoring }
  - { key: stat2_rate,      make: raw["stat2_numer"], attempt: raw["stat2_denom"],   bucket: impact }
  - { key: stat4_quality,   make: raw["stat4_good"],  attempt: raw["stat4_total"],   bucket: survival }
```

---

## 6) Mapping (not used in this example)

In older formats, mapping translated raw data to metric keys directly. In this example, source fields and efficiency definitions replace that.

---

## 7) Weights (optional)

**Purpose:** Assign importance to each bucket for different scoring presets.

Weights don’t need to sum to 1; the engine normalizes automatically.

**Example:**

```yaml
weights:
  pri:
    scoring:    0.30
    impact:     0.28
    utility:    0.16
    survival:   0.16
    discipline: 0.10
  mvp:
    scoring:    0.34
    impact:     0.30
    utility:    0.12
    survival:   0.14
    discipline: 0.10
  support:
    scoring:    0.16
    impact:     0.18
    utility:    0.40
    survival:   0.16
    discipline: 0.10
```

---

## 8) Penalties (optional)

**Purpose:** Add extra scaling for negative influence in specific buckets.

**Example:**

```yaml
penalties:
  pri:     { discipline: 0.10 }
  mvp:     { discipline: 0.12 }
  support: { discipline: 0.08 }
```

---

## 9) Sniff (optional)

**Purpose:** Help the engine auto-select the adapter by matching headers in the raw data.

**Example:**

```yaml
sniff:
  require_any_headers: [stat1_total, stat2_numer, stat2_denom, rounds_played, mistakes]
```

---

## 10) Versioning Rules

* **Major** = Structural change.
* **Minor** = Additions or meaningful clamp shifts.
* **Patch** = Minor fixes.

---

## 11) Validation Checklist

* All metrics match mapping/source fields.
* Buckets exist for all metrics.
* Clamps are realistic.
* Penalty metrics have `invert: true`.
* Efficiency pairs have valid fields.
* Weights reference existing buckets.
* Sniff headers match actual data.
* All divides are guarded.
* Use rates for stats that vary with match length.

---

## 12) FAQ

**Q:** Why rates instead of totals?
**A:** Totals inflate long matches and bias results.

**Q:** Must weights sum to 1?
**A:** No, normalization is automatic.

**Q:** Should fewer mistakes be treated as positive?
**A:** Yes — mark with `invert: true`.

**Q:** Are dimensions required?
**A:** Only if you want filtering/aggregation.

---

## 13) Future Hooks (not yet supported)

* Metric transforms.
* Per-dimension clamps.
* Per-metric multipliers.
* Team-factor modes.

---

## 14) Minimal Starter Template (Updated Example)

```yaml
key: example_game
version: 0.1.0
aliases: [ex, sample]
title: Example Game

dimensions:
  map:   { values: [MapA, MapB, MapC] }
  side:  { values: [Attack, Defense] }
  role:  { values: [Carry, Support, Flex] }
  mode:  { values: [Pro, Ranked, Scrim] }

buckets:
  scoring: {}
  impact: {}
  utility: {}
  survival: {}
  discipline: {}

metrics:
  - { key: stat3_count, bucket: utility,    clamp: [0, 50],  source: { field: stat3_count } }
  - { key: mistakes,    bucket: discipline, clamp: [0, 25], invert: true, source: { field: mistakes } }

efficiency:
  - { key: stat1_per_round, make: raw["stat1_total"], attempt: raw["rounds_played"], bucket: scoring }
  - { key: stat2_rate,      make: raw["stat2_numer"], attempt: raw["stat2_denom"],   bucket: impact }
  - { key: stat4_quality,   make: raw["stat4_good"],  attempt: raw["stat4_total"],   bucket: survival }

weights:
  pri:
    scoring:    0.30
    impact:     0.28
    utility:    0.16
    survival:   0.16
    discipline: 0.10
  mvp:
    scoring:    0.34
    impact:     0.30
    utility:    0.12
    survival:   0.14
    discipline: 0.10
  support:
    scoring:    0.16
    impact:     0.18
    utility:    0.40
    survival:   0.16
    discipline: 0.10

penalties:
  pri:     { discipline: 0.10 }
  mvp:     { discipline: 0.12 }
  support: { discipline: 0.08 }

sniff:
  require_any_headers: [stat1_total, stat2_numer, stat2_denom, rounds_played, mistakes]
```
