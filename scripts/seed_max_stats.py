from statline.utils.config import DEFAULT_MAX_STATS
from statline.io.persistence import save_max_stats

if __name__ == "__main__":
    save_max_stats(DEFAULT_MAX_STATS, "max_stats.json")
    print("Wrote max_stats.json from defaults.")
