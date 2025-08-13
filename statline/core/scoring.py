import math
from .normalization import norm, clamp01
from .weights import MVP_WEIGHTS_PCT_BY_ROLE, OFF_WEIGHTS_PCT, DEF_WEIGHTS_PCT, as_unit_weights
from ..utils.config import TEAM_WEIGHT, TEAM_FACTOR_MIN, TEAM_FACTOR_MAX, M_SCALE, M_OFFSET, DEFAULT_MAX_STATS

TOV_PENALTY = {"mvp": 0.12, "offensive": 0.15, "defensive": 0.00}
DEF_STEAL_W, DEF_BLOCK_W = 0.6, 0.4
DEF_STEAL_W_DEF, DEF_BLOCK_W_DEF = 0.5, 0.5

def turnover_efficiency(points, assists, turnovers, ratio_mode="dynamic"):
    turnovers = max(turnovers, 1e-6)
    if ratio_mode == "ast/tov":
        ratio, used = assists / turnovers, "ast/tov"
    elif ratio_mode == "pts/tov":
        ratio, used = points / turnovers, "pts/tov"
    else:
        ratio, used = (assists / turnovers, "ast/tov (dynamic)") if assists >= 10 else (points / turnovers, "pts/tov (dynamic)")
    ratio = min(ratio, 8.0)
    return 1 / (1 + math.exp(-0.9 * (ratio - 2.0))), used

def approx_efg(ppg, fgm, fga):
    if fga <= 0 or fgm <= 0:
        return 0.0, 0.0
    est_3pm = max(0.0, min(fgm, ppg - 2.0 * fgm))
    actual = (fgm + 0.5 * est_3pm) / fga
    personal_max = 1.0 + 0.5 * (est_3pm / fgm)  # 1.0 → 1.5
    return actual, clamp01(actual / personal_max)

def choose_weights(mode: str, role: str):
    if mode == "defensive_score":
        return as_unit_weights(DEF_WEIGHTS_PCT)
    if mode == "offensive_score":
        return as_unit_weights(OFF_WEIGHTS_PCT)
    return as_unit_weights(MVP_WEIGHTS_PCT_BY_ROLE.get(role.lower(), MVP_WEIGHTS_PCT_BY_ROLE["wing"]))

def calculate_scores(
    stats: dict,
    team_wins: int = 0,
    team_losses: int = 0,
    ratio_mode: str = "dynamic",
    mode: str = "mvp_score",
    role: str = "wing",
    max_stats: dict | None = None,
):
    max_stats = max_stats or DEFAULT_MAX_STATS

    def_term = (
        DEF_STEAL_W_DEF * norm(stats["spg"], max_stats["spg"]) + DEF_BLOCK_W_DEF * norm(stats["bpg"], max_stats["bpg"])
        if mode == "defensive_score" else
        DEF_STEAL_W * norm(stats["spg"], max_stats["spg"]) + DEF_BLOCK_W * norm(stats["bpg"], max_stats["bpg"])
    )

    weights = choose_weights(mode, role)
    n_ppg  = norm(stats["ppg"],  max_stats["ppg"])
    n_apg  = norm(stats["apg"],  max_stats["apg"])
    n_orpg = norm(stats.get("orpg", 0.0), max_stats["orpg"])
    n_drpg = norm(stats.get("drpg", 0.0), max_stats["drpg"])
    aefg_val, n_aefg = approx_efg(stats["ppg"], stats["fgm"], stats["fga"])
    n_tov, used_ratio = turnover_efficiency(stats["ppg"], stats["apg"], stats["tov"], ratio_mode)

    if mode == "mvp_score":
        wsum = (
            weights["ppg"] * n_ppg + weights["apg"] * n_apg +
            weights["orpg"] * n_orpg + weights["drpg"] * n_drpg +
            weights["def_"] * def_term + weights["aefg"] * n_aefg
        )
        tov_w = TOV_PENALTY["mvp"]
    elif mode == "offensive_score":
        wsum = weights["ppg"] * n_ppg + weights["apg"] * n_apg + weights["orpg"] * n_orpg + weights["aefg"] * n_aefg
        tov_w = TOV_PENALTY["offensive"]
    else:
        wsum = weights["drpg"] * n_drpg + weights["def_"] * def_term
        tov_w = TOV_PENALTY["defensive"]

    wsum -= tov_w * (1 - n_tov)
    base = M_SCALE * wsum + M_OFFSET

    total = team_wins + team_losses
    win_pct = (team_wins / total) if total > 0 else 0.0
    adj = max(0.0, win_pct - 0.50)
    team_factor = 1 + TEAM_WEIGHT * (adj / 0.50)
    team_factor = min(max(team_factor, TEAM_FACTOR_MIN), TEAM_FACTOR_MAX)

    final = max(0, min(base * team_factor, 99))
    comps = {
        "ppg": n_ppg, "apg": n_apg, "orpg": n_orpg, "drpg": n_drpg,
        "def_term": def_term, "aefg": n_aefg, "tov_eff": n_tov, "team_factor": team_factor
    }
    return final, used_ratio, aefg_val, comps, weights
