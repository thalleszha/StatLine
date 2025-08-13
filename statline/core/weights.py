MVP_WEIGHTS_PCT_BY_ROLE = {
    "guard":  {"ppg":34,"apg":24,"orpg":4,"drpg":6,"def_":20,"aefg":12},
    "wing":   {"ppg":33,"apg":20,"orpg":6,"drpg":9,"def_":22,"aefg":10},
    "center": {"ppg":30,"apg":12,"orpg":10,"drpg":18,"def_":22,"aefg":8},
}
OFF_WEIGHTS_PCT = {"ppg":45,"apg":30,"orpg":10,"aefg":15}
DEF_WEIGHTS_PCT = {"drpg":35,"def_":65}

def as_unit_weights(weights_pct: dict) -> dict:
    total = sum(weights_pct.values())
    if total <= 0: raise ValueError("Weights must sum to > 0.")
    return {k: v/total for k,v in weights_pct.items()}
