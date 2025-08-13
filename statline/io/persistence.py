import json, os
from ..utils.config import DEFAULT_MAX_STATS

def load_max_stats(path="max_stats.json"):
    if os.path.exists(path):
        with open(path,"r") as f: return json.load(f)
    return DEFAULT_MAX_STATS.copy()

def save_max_stats(max_stats, path="max_stats.json"):
    with open(path,"w") as f: json.dump(max_stats, f, indent=4)
