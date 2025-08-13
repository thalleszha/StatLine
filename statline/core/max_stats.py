import os
import json

MAX_STATS_FILE = 'max_stats.json'
DEFAULT_MAX_STATS = {
    'ppg': 41.0, 'apg': 18.0, 'orpg': 7.0, 'drpg': 8.0,
    'spg': 5.0, 'bpg': 5.0, 'tov': 8.0, 'fgm': 16.0, 'fga': 28.0
}
MAX_STATS = {}

def load_max_stats():
    global MAX_STATS
    if os.path.exists(MAX_STATS_FILE):
        with open(MAX_STATS_FILE, 'r') as f:
            MAX_STATS = json.load(f)
    else:
        MAX_STATS = DEFAULT_MAX_STATS.copy()

def save_max_stats():
    with open(MAX_STATS_FILE, 'w') as f:
        json.dump(MAX_STATS, f, indent=4)
