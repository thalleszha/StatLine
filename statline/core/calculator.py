from .max_stats import load_max_stats, save_max_stats, DEFAULT_MAX_STATS
from .scoring import calculate_scores
from .normalization import clamp01, norm, get_input

def interactive_mode():
    load_max_stats()
    print("\n=== StatLine Calculator ===")

    while True:
        mode_type = input("\nType 'demo' for demo mode, anything else for live: ").strip().lower()
        if mode_type != 'demo':
            save_max_stats()

        ratio_mode = input("\nTurnover ratio mode [dynamic]: ").strip().lower() or 'dynamic'
        score_mode = input("Score mode [mvp_score]: ").strip().lower() or 'mvp_score'
        role = 'wing'
        if score_mode == 'mvp_score':
            role = input("Player Role (guard/wing/center) [wing]: ").strip().lower() or 'wing'

        while True:
            print("\n--- Enter Player Stats ---")
            name = input("Player Name (or 'exit'): ").strip()
            if name.lower() == 'exit':
                print("\nExiting StatLine.")
                return

            stats = {
                'ppg': get_input("PPG: "),
                'apg': get_input("APG: "),
                'orpg': get_input("ORPG: "),
                'drpg': get_input("DRPG: "),
                'spg': get_input("SPG: "),
                'bpg': get_input("BPG: "),
                'fgm': get_input("FGM: "),
                'fga': get_input("FGA: "),
                'tov': get_input("TOV: ")
            }
            team_wins = get_input("Team Wins: ", int, allow_empty=True, default=0) or 0
            team_losses = get_input("Team Losses: ", int, allow_empty=True, default=0) or 0


            score, used_ratio, aefg_val, comp, w = calculate_scores(
                stats, team_wins, team_losses, ratio_mode, score_mode, role
            )
            win_pct = team_wins / (team_wins + team_losses) if (team_wins + team_losses) else 0

            print("\n" + "="*50)
            print(f"{name} — {score_mode.replace('_', ' ').title()} (Role: {role.title()})")
            print(f"Final Score: {score:.2f} / 99")
            print(f"Turnover Ratio Used: {used_ratio}")
            print(f"Approx eFG%: {aefg_val:.3f} (Norm: {comp['aefg']:.3f})")
            print(f"Win%: {win_pct:.3f} | Team Factor: {comp['team_factor']:.3f}")
            print("="*50)

            choice = input("\n(N)ext Player | (C)hange Settings | (E)xit: ").strip().lower()
            if choice == 'c':
                break
            elif choice == 'e':
                return
