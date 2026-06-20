from app.database import (
    get_all_flagged_moves,
    get_all_games,
    get_stats_summary,
    get_type_distribution,
)


def analyze_patterns():
    moves = get_all_flagged_moves()
    games = get_all_games()

    if not moves:
        return {
            "top_patterns": [],
            "phase_breakdown": {},
            "rating_insight": "No games analyzed yet. Paste a game to get started!",
            "total_games": 0,
        }

    type_counts = {}
    phase_counts = {"opening": 0, "middlegame": 0, "endgame": 0}
    severity_by_type = {}
    move_numbers_by_type = {}

    for m in moves:
        mt = m["mistake_type"]
        sev = m["severity"]
        mn = m["move_number"]
        color = m["color"]

        type_counts[mt] = type_counts.get(mt, 0) + 1

        if mt not in severity_by_type:
            severity_by_type[mt] = {"blunder": 0, "mistake": 0, "inaccuracy": 0}
        if sev in severity_by_type[mt]:
            severity_by_type[mt][sev] += 1

        if mt not in move_numbers_by_type:
            move_numbers_by_type[mt] = []
        move_numbers_by_type[mt].append(mn)

        if mn <= 10:
            phase_counts["opening"] += 1
        elif mn <= 30:
            phase_counts["middlegame"] += 1
        else:
            phase_counts["endgame"] += 1

    total_flagged = len(moves)
    patterns = []
    for mt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = round(100 * count / total_flagged, 1)
        avg_move = 0
        if mt in move_numbers_by_type:
            nums = move_numbers_by_type[mt]
            avg_move = round(sum(nums) / len(nums), 1)

        dominant_phase = "middlegame"
        if mt in move_numbers_by_type:
            nums = move_numbers_by_type[mt]
            opening = sum(1 for n in nums if n <= 10)
            mid = sum(1 for n in nums if 10 < n <= 30)
            end = sum(1 for n in nums if n > 30)
            dominant_phase = max(
                [("opening", opening), ("middlegame", mid), ("endgame", end)],
                key=lambda x: x[1],
            )[0]

        top_sev = max(
            severity_by_type.get(mt, {}), key=lambda k: severity_by_type[mt].get(k, 0)
        )

        patterns.append(
            {
                "type": mt,
                "count": count,
                "percentage": pct,
                "avg_move_number": avg_move,
                "dominant_phase": dominant_phase,
                "worst_severity": top_sev,
                "severity_breakdown": severity_by_type.get(mt, {}),
            }
        )

    dominant_phase = (
        max(phase_counts, key=phase_counts.get)
        if any(phase_counts.values())
        else "middlegame"
    )

    return {
        "top_patterns": patterns,
        "phase_breakdown": phase_counts,
        "dominant_phase": dominant_phase,
        "total_games": len(games),
        "total_flagged": total_flagged,
    }


def generate_study_plan(current_rating, target_rating):
    gap = target_rating - current_rating
    patterns = analyze_patterns()

    if not patterns["top_patterns"]:
        return {
            "focus_areas": [],
            "general_advice": "Play some games and analyze them first. Then you'll get a personalized study plan.",
            "gap": gap,
        }

    priority_map = {
        "tactical": {
            "1200-1400": {
                "focus": "Tactical Pattern Recognition",
                "details": "Solve 10-15 puzzles daily. Focus on: forks, pins, skewers, and hanging piece detection. Tactics are the fastest way to gain rating in this range.",
                "resources": [
                    "Lichess puzzle storm",
                    "Chess.com puzzles",
                    "CT-ART (app)",
                ],
                "expected_gain": "100-200 points",
            },
            "1400-1600": {
                "focus": "Advanced Tactics & Combinations",
                "details": "Work on 2-3 move combinations. Focus on discovered attacks, deflection, and overloading. Start calculating variations before moving.",
                "resources": ["1001 Chess Exercises", "Lichess studies"],
                "expected_gain": "100-150 points",
            },
            "1600-1800": {
                "focus": "Calculation & Tactical Vision",
                "details": "Calculate 3-4 moves deep. Practice recognizing patterns in complex positions. Solve harder puzzles (2000+ rated).",
                "resources": ["Woodpecker Method", "CT-ART 4.0"],
                "expected_gain": "50-100 points",
            },
        },
        "positional": {
            "1200-1400": {
                "focus": "Piece Activity & Pawn Structure",
                "details": "Place pieces on active squares. Avoid doubled/isolated pawns. Control the center. Ask 'where does this piece belong?' before every move.",
                "resources": [
                    "Chess Fundamentals (Capablanca)",
                    "Beginner positional videos",
                ],
                "expected_gain": "50-100 points",
            },
            "1400-1600": {
                "focus": "Weak Squares & Outposts",
                "details": "Learn to identify and exploit weak squares. Place knights on outposts. Understand when to trade vs maintain tension.",
                "resources": [
                    "My System (Nimzowitsch) simplified",
                    "Positional chess exercises",
                ],
                "expected_gain": "50-100 points",
            },
        },
        "endgame": {
            "1200-1400": {
                "focus": "Basic Endgame Technique",
                "details": "Master king+pawn endings and basic rook endings. Learn opposition and the rule of the square. These are the most common endgames at your level.",
                "resources": [
                    "Silman's Complete Endgame Course",
                    "Lichess endgame practice",
                ],
                "expected_gain": "50-100 points",
            },
        },
        "opening": {
            "1200-1400": {
                "focus": "Opening Principles (Not Memorization)",
                "details": "Don't memorize lines. Follow principles: control center, develop knights before bishops, castle early, don't bring queen out too early.",
                "resources": [
                    "Logical Chess: Move by Move",
                    "Chess opening principles videos",
                ],
                "expected_gain": "30-50 points",
            },
        },
    }

    focus_areas = []
    rating_band = f"{current_rating // 200 * 200}-{current_rating // 200 * 200 + 200}"
    if current_rating < 1400:
        rating_band = "1200-1400"
    elif current_rating < 1600:
        rating_band = "1400-1600"
    else:
        rating_band = "1600-1800"

    for p in patterns["top_patterns"]:
        mt = p["type"]
        if mt in priority_map and rating_band in priority_map[mt]:
            plan = priority_map[mt][rating_band]
            focus_areas.append(
                {
                    "area": plan["focus"],
                    "problem_type": mt,
                    "percentage": p["percentage"],
                    "details": plan["details"],
                    "resources": plan["resources"],
                    "expected_gain": plan["expected_gain"],
                    "priority": p["percentage"],
                }
            )

    focus_areas.sort(key=lambda x: -x["priority"])

    if not focus_areas:
        general = f"You're rated {current_rating} aiming for {target_rating} ({gap} point gap). "
        general += "Your mistakes are fairly balanced. Focus on tactical puzzles daily — that's the fastest path to improvement at your level."
    else:
        general = f"You're rated {current_rating} aiming for {target_rating} ({gap} point gap). "
        general += f"Your main weakness is {focus_areas[0]['area'].lower()}. "
        general += (
            f"Addressing this alone could gain you {focus_areas[0]['expected_gain']}."
        )

    return {
        "focus_areas": focus_areas,
        "general_advice": general,
        "gap": gap,
        "rating_band": rating_band,
        "dominant_phase": patterns.get("dominant_phase", "middlegame"),
    }


def get_progress_data():
    games = get_all_games()
    if not games:
        return {"has_data": False}

    trend = []
    for g in reversed(games):
        player_blunders = (
            g["white_blunders"] if g["player_color"] == "w" else g["black_blunders"]
        )
        player_mistakes = (
            g["white_mistakes"] if g["player_color"] == "w" else g["black_mistakes"]
        )
        player_inacc = (
            g["white_inaccuracies"]
            if g["player_color"] == "w"
            else g["black_inaccuracies"]
        )
        total_issues = player_blunders + player_mistakes + player_inacc

        trend.append(
            {
                "date": g["created_at"],
                "game_id": g["id"],
                "opponent": g["black"] if g["player_color"] == "w" else g["white"],
                "result": g["result"],
                "blunders": player_blunders,
                "mistakes": player_mistakes,
                "inaccuracies": player_inacc,
                "total_issues": total_issues,
                "rating": g["player_rating"],
            }
        )

    type_dist = get_type_distribution()

    return {
        "has_data": True,
        "trend": trend,
        "type_distribution": type_dist,
        "total_games": len(games),
    }
