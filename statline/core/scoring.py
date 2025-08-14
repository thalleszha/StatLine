from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, Mapping, Any, Tuple, Optional, List

from .normalization import clamp01
from .weights import normalize_weights
from ..utils.config import (
    TEAM_WEIGHT,
    TEAM_FACTOR_MIN,
    TEAM_FACTOR_MAX,
    M_SCALE,
    M_OFFSET,
)

# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlayerStats:
    """Legacy hoops-shaped stats. Adapters for other games should not use this."""
    ppg: float
    apg: float
    orpg: float
    drpg: float
    spg: float
    bpg: float
    fgm: float
    fga: float
    tov: float

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "PlayerStats":
        def f(k: str) -> float:
            v = m[k]
            try:
                return float(v)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid value for {k!r}: {v!r}")
        return cls(
            ppg=f("ppg"), apg=f("apg"), orpg=f("orpg"), drpg=f("drpg"),
            spg=f("spg"), bpg=f("bpg"), fgm=f("fgm"), fga=f("fga"), tov=f("tov")
        )

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)  # dict[str, float]


@dataclass(frozen=True)
class ScoreResult:
    score: float                      # final score (0..99)
    components: Dict[str, float]      # normalized 0..1 per metric
    weights: Dict[str, float]         # unit (L1) weights used (sign-preserving)
    # Optional extras (legacy hoops)
    used_ratio: Optional[str] = None  # which TOV ratio was used
    aefg: Optional[float] = None      # raw approx eFG (not normalized)

# ──────────────────────────────────────────────────────────────────────────────
# Team factor, efficiency helpers (legacy-friendly)
# ──────────────────────────────────────────────────────────────────────────────

def _team_factor(wins: int, losses: int) -> float:
    total = wins + losses
    win_pct = (wins / total) if total > 0 else 0.0
    adj = max(0.0, win_pct - 0.50)
    tf = 1 + TEAM_WEIGHT * (adj / 0.50)
    return min(max(tf, TEAM_FACTOR_MIN), TEAM_FACTOR_MAX)

def _turnover_efficiency(points: float, assists: float, turnovers: float, ratio_mode: str = "dynamic") -> Tuple[float, str]:
    turnovers = max(float(turnovers), 1e-6)
    if ratio_mode == "ast/tov":
        ratio, used = assists / turnovers, "ast/tov"
    elif ratio_mode == "pts/tov":
        ratio, used = points / turnovers, "pts/tov"
    else:
        ratio, used = ((assists / turnovers), "ast/tov (dynamic)") if assists >= 10 else ((points / turnovers), "pts/tov (dynamic)")
    ratio = min(ratio, 8.0)
    eff = 1 / (1 + math.exp(-0.9 * (ratio - 2.0)))
    return eff, used

def _approx_efg(ppg: float, fgm: float, fga: float) -> Tuple[float, float]:
    if fga <= 0 or fgm <= 0:
        return 0.0, 0.0
    est_3pm = max(0.0, min(fgm, ppg - 2.0 * fgm))
    actual = (fgm + 0.5 * est_3pm) / fga
    personal_max = 1.0 + 0.5 * (est_3pm / fgm)  # 1.0 → 1.5
    return actual, clamp01(actual / personal_max)

def _safe_norm(value: float, cap: float) -> float:
    cap = float(cap)
    v = float(value)
    if cap <= 1e-12:
        return 0.0
    return clamp01(v / cap)

# ──────────────────────────────────────────────────────────────────────────────
# Spec-driven helpers (adapter/batch/DB context)
# ──────────────────────────────────────────────────────────────────────────────

def caps_from_context(
    metrics_keys: List[str],
    context: Dict[str, Dict[str, float]],
    *,
    invert: Optional[Dict[str, bool]] = None,
) -> Dict[str, float]:
    """
    Build caps map for PRI-AP:
      - positive metrics: cap = leader
      - inverted metrics: cap = |floor - leader| (we'll give negative weights)
    If context is missing a metric, fall back to 1.0 (benign) to avoid div0.
    """
    caps: Dict[str, float] = {}
    inv = invert or {}
    for k in metrics_keys:
        info = context.get(k)
        if not info:
            caps[k] = 1.0
            continue
        leader = float(info.get("leader", 1.0))
        floor  = float(info.get("floor", 0.0))
        if inv.get(k, False):
            caps[k] = max(1e-6, abs(floor - leader))
        else:
            caps[k] = max(1e-6, leader)
    return caps

def per_metric_weights_from_buckets(
    metric_to_bucket: Dict[str, str],
    bucket_weights: Dict[str, float],
) -> Dict[str, float]:
    """Spread each bucket's weight equally across its metrics."""
    counts: Dict[str, int] = {}
    for _, b in metric_to_bucket.items():
        counts[b] = counts.get(b, 0) + 1
    per_metric: Dict[str, float] = {}
    for m, b in metric_to_bucket.items():
        bw = float(bucket_weights.get(b, 0.0))
        n  = max(1, counts.get(b, 1))
        per_metric[m] = bw / n
    return per_metric

def _batch_context_from_rows(rows: List[Dict[str, Any]], metric_keys: List[str], invert: Dict[str, bool]) -> Dict[str, Dict[str, float]]:
    """Fallback when DB/Sheets context is unavailable: derive leader/floor from the batch."""
    vals: Dict[str, List[float]] = {k: [] for k in metric_keys}
    for r in rows:
        for k in metric_keys:
            v = r.get(k)
            try:
                if v is not None:
                    vals[k].append(float(v))
            except Exception:
                pass
    ctx: Dict[str, Dict[str, float]] = {}
    for k in metric_keys:
        xs = sorted(vals[k])
        if not xs:
            # benign defaults
            ctx[k] = {"leader": 1.0, "floor": 0.0} if not invert.get(k, False) else {"leader": 0.0, "floor": 1.0}
            continue
        if invert.get(k, False):
            ctx[k] = {"leader": xs[0], "floor": xs[-1]}   # lower is better
        else:
            ctx[k] = {"leader": xs[-1], "floor": xs[0]}   # higher is better
    return ctx

# ──────────────────────────────────────────────────────────────────────────────
# Generic PRI kernel (single-row). Internal helper.
# ──────────────────────────────────────────────────────────────────────────────

def _pri_kernel_single(
    metrics: Mapping[str, float],
    caps: Mapping[str, float],
    weights: Mapping[str, float],
    *,
    team_wins: int = 0,
    team_losses: int = 0,
    apply_team_factor: bool = True,
    scale: float = 100.0,
    clamp_upper: float = 99.0,
) -> ScoreResult:
    """Compute weighted, normalized score for one row."""
    unit_w = normalize_weights(weights)  # preserve sign, L1-normalize
    if not unit_w:
        return ScoreResult(score=0.0, components={}, weights={})

    comps: Dict[str, float] = {}
    wsum = 0.0
    for k, w in unit_w.items():
        norm = _safe_norm(float(metrics.get(k, 0.0)), float(caps.get(k, 0.0)))
        comps[k] = norm
        wsum += norm * w

    base = (M_SCALE if scale == 100.0 else scale) * wsum + M_OFFSET
    tf = _team_factor(team_wins, team_losses) if apply_team_factor else 1.0
    final = max(0.0, min(base * tf, clamp_upper))
    return ScoreResult(score=final, components=comps, weights=dict(unit_w))

# ──────────────────────────────────────────────────────────────────────────────
# Dynamic PRI (adapter-agnostic) — batch API
# ──────────────────────────────────────────────────────────────────────────────

def calculate_pri(
    mapped_rows: List[Dict[str, Any]],
    adapter: Any,   # concrete adapters vary; keep strong return typing
    *,
    team_wins: int = 0,
    team_losses: int = 0,
    weights_override: Optional[Dict[str, float]] = None,
    context: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[Dict[str, Any]]:
    """
    Fully dynamic PRI (0–99), driven by adapter specs.
    Returns list of dicts with pri, pri_raw, bucket scores, components, weights, context_used.
    """
    # 1) Collect spec info
    metric_keys = [m.key for m in adapter.metrics]
    metric_to_bucket: Dict[str, str] = {m.key: m.bucket for m in adapter.metrics}
    invert_map: Dict[str, bool] = {m.key: bool(m.invert) for m in adapter.metrics}

    # 2) Inject efficiency channels as derived metrics
    eff_list = list(getattr(adapter, "efficiency", []) or [])
    extended_rows: List[Dict[str, Any]] = []
    for raw in mapped_rows:
        r: Dict[str, Any] = dict(raw)
        for eff in eff_list:
            make = max(0.0, float(adapter.eval_expr(eff.make, raw)))
            att  = max(1.0, float(adapter.eval_expr(eff.attempt, raw)))
            pct  = make / att
            r[eff.key] = clamp01(pct)
            if eff.key not in metric_to_bucket:
                metric_to_bucket[eff.key] = eff.bucket
                invert_map[eff.key] = False
                metric_keys.append(eff.key)
        extended_rows.append(r)

    # 3) Resolve context (leaders/floors) & build caps
    ctx = context or _batch_context_from_rows(extended_rows, metric_keys, invert_map)
    caps = caps_from_context(metric_keys, ctx, invert=invert_map)

    # 4) Bucket weights → per-metric weights; flip sign for inverted metrics
    bucket_weights = dict(weights_override or getattr(adapter, "weights", {}).get("pri", {}) or {})
    per_metric_weights = per_metric_weights_from_buckets(metric_to_bucket, bucket_weights)
    for k, inv in invert_map.items():
        if inv and k in per_metric_weights:
            per_metric_weights[k] = -abs(per_metric_weights[k])

    # 5) Score each row and compute per-bucket averages for explainability
    out: List[Dict[str, Any]] = []
    for r in extended_rows:
        res = _pri_kernel_single(
            metrics=r,
            caps=caps,
            weights=per_metric_weights,
            team_wins=team_wins,
            team_losses=team_losses,
            apply_team_factor=True,
            scale=100.0,
            clamp_upper=99.0,
        )

        # per-bucket aggregation (mean of component scores inside each bucket)
        bucket_scores: Dict[str, float] = {b: 0.0 for b in getattr(adapter, "buckets", {}).keys()}
        bucket_counts: Dict[str, int]   = {b: 0 for b in getattr(adapter, "buckets", {}).keys()}
        for k, v in res.components.items():
            b = metric_to_bucket.get(k)
            if b is None:
                continue
            bucket_scores[b] += v
            bucket_counts[b] += 1
        for b in bucket_scores:
            c = bucket_counts[b]
            bucket_scores[b] = (bucket_scores[b] / c) if c else 0.0

        # normalize raw score back to 0..1 using configured scale/offset
        denom = max(1e-6, float(M_SCALE))
        pri_raw = clamp01((res.score - float(M_OFFSET)) / denom)

        out.append({
            "pri": int(round(res.score)),
            "pri_raw": pri_raw,
            "buckets": bucket_scores,
            "components": res.components,
            "weights": res.weights,
            "context_used": "batch" if context is None else "external",
        })
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Legacy hoops API (kept for backward compatibility)
# ──────────────────────────────────────────────────────────────────────────────

def calculate_scores(
    stats: Mapping[str, float],
    team_wins: int = 0,
    team_losses: int = 0,
    ratio_mode: str = "dynamic",
    mode: str = "mvp_score",
    role: str = "wing",
    max_stats: Optional[Mapping[str, float]] = None,
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> Tuple[float, str, float, Dict[str, float], Dict[str, float]]:
    aefg_raw, aefg_norm = _approx_efg(stats.get("ppg", 0.0), stats.get("fgm", 0.0), stats.get("fga", 0.0))
    tov_eff, used_ratio = _turnover_efficiency(stats.get("ppg", 0.0), stats.get("apg", 0.0), stats.get("tov", 0.0), ratio_mode)

    legacy_metrics: Dict[str, float] = {
        "ppg": stats.get("ppg", 0.0),
        "apg": stats.get("apg", 0.0),
        "orpg": stats.get("orpg", 0.0),
        "drpg": stats.get("drpg", 0.0),
        "spg": stats.get("spg", 0.0),
        "bpg": stats.get("bpg", 0.0),
        "aefg": aefg_norm,
        "tov_eff": tov_eff,
    }

    ms = max_stats or {
        "ppg": 41.0, "apg": 18.0, "orpg": 7.0, "drpg": 8.0,
        "spg": 5.0,  "bpg": 5.0,  "aefg": 1.0, "tov_eff": 1.0,
    }

    default_weights: Dict[str, float] = {
        "ppg": 0.33, "apg": 0.20, "orpg": 0.06, "drpg": 0.09,
        "spg": 0.16, "bpg": 0.10, "aefg": 0.10, "tov_eff": 0.06,
    }
    use_weights = dict(weights or default_weights)

    result = _pri_kernel_single(
        metrics=legacy_metrics,
        caps=ms,
        weights=use_weights,
        team_wins=team_wins,
        team_losses=team_losses,
        apply_team_factor=True,
        scale=100.0,
        clamp_upper=99.0,
    )

    return result.score, used_ratio, aefg_raw, result.components, result.weights


def calculate_scores_dc(
    stats: PlayerStats,
    team_wins: int = 0,
    team_losses: int = 0,
    ratio_mode: str = "dynamic",
    mode: str = "mvp_score",
    role: str = "wing",
    max_stats: Optional[Mapping[str, float]] = None,
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> ScoreResult:
    final, used_ratio, aefg_val, comps, w = calculate_scores(
        stats.as_dict(),
        team_wins=team_wins,
        team_losses=team_losses,
        ratio_mode=ratio_mode,
        mode=mode,
        role=role,
        max_stats=max_stats,
        weights=weights,
    )
    return ScoreResult(score=final, components=comps, weights=w, used_ratio=used_ratio, aefg=aefg_val)


__all__ = [
    "PlayerStats",
    "ScoreResult",
    "calculate_pri",
    "calculate_scores",
    "calculate_scores_dc",
]
