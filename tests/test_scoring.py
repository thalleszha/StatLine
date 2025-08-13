from statline.core.scoring import calculate_scores
from statline.utils.config import DEFAULT_MAX_STATS

def test_basic_guard_high_score():
    stats = {"ppg":41,"apg":9,"orpg":1,"drpg":2,"spg":0,"bpg":0,"fgm":14,"fga":19,"tov":1}
    score, *_ = calculate_scores(stats, 7, 1, mode="mvp_score", role="guard", max_stats=DEFAULT_MAX_STATS)
    assert score >= 70
