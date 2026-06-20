import openai
from app.config import settings
from app.models import FlaggedMove, Severity, MistakeType, GameAnalysis
import json


def _build_explanation_prompt(
    move: FlaggedMove, game: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    """Build a prompt for explaining a chess mistake to a beginner."""

    severity_desc = {
        Severity.BLUNDER: "a blunder (a very bad move that loses significant material or the game)",
        Severity.MISTAKE: "a mistake (a move that significantly worsens your position)",
        Severity.INACCURACY: "an inaccuracy (a move that slightly worsens your position)",
    }

    type_desc = {
        MistakeType.TACTICAL: "tactical oversight (missed a fork, pin, skewer, or hanging piece)",
        MistakeType.POSITIONAL: "positional weakness (poor piece placement or pawn structure)",
        MistakeType.ENDGAME: "endgame technique error",
        MistakeType.OPENING: "opening deviation from good principles",
        MistakeType.UNKNOWN: "general error",
    }

    rating_context = f"""
You are coaching a chess player rated {player_rating} who wants to reach {target_rating}.
Your explanations must be:
- Written in simple language a {player_rating}-rated player can understand
- Focus on practical lessons, not engine variations
- Explain the CONCEPT behind why the move was bad, not just the engine line
- Suggest what to study/practice to avoid this type of mistake
- Keep it to 2-3 sentences max per explanation
- Never use raw eval numbers like "+2.3" — translate to chess concepts
"""

    prompt = f"""{rating_context}

Game: {game.white} vs {game.black}, Result: {game.result}

Move: {move.san} (move {move.move_number}, {"White" if move.color == "w" else "Black"})
This was {severity_desc[move.severity]}, specifically a {type_desc[move.mistake_type]}.

The eval went from roughly {"winning" if move.eval_before > 100 else "equal" if abs(move.eval_before) < 100 else "losing"} for {"White" if move.color == "w" else "Black"} to {"winning" if move.eval_after > 100 else "equal" if abs(move.eval_after) < 100 else "losing"}.
Best move was: {move.best_move_san}

Explain this mistake to the player in 2-3 simple sentences. What went wrong, what should they have done instead, and what to practice?"""

    return prompt


async def explain_move_with_llm(
    move: FlaggedMove, game: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    """Use OpenAI to generate a beginner-friendly explanation."""
    if not settings.openai_api_key:
        return _fallback_explanation(move, game, player_rating)

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        prompt = _build_explanation_prompt(move, game, player_rating, target_rating)

        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a friendly chess coach who explains things simply.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.7,
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        return _fallback_explanation(move, game, player_rating)


def _fallback_explanation(
    move: FlaggedMove, game: GameAnalysis, player_rating: int
) -> str:
    """Template-based explanation when no LLM is available."""
    type_explanations = {
        MistakeType.TACTICAL: {
            Severity.BLUNDER: "This was a tactical blunder — you likely left a piece hanging or missed a forcing sequence. At your level, always check: 'Is this square defended? Can my opponent capture it for free?'",
            Severity.MISTAKE: "A tactical mistake — you missed something concrete. Before moving, ask: 'What does my opponent's last move threaten?' and 'Am I leaving anything undefended?'",
            Severity.INACCURACY: "A slight tactical slip. Try to develop the habit of checking your opponent's threats before every move.",
        },
        MistakeType.POSITIONAL: {
            Severity.BLUNDER: "A serious positional error — this move likely created a permanent weakness (doubled pawns, open file toward your king, or a piece with no squares). Think about pawn structure and piece safety.",
            Severity.MISTAKE: "A positional mistake — this move doesn't improve your position. Focus on: control the center, develop pieces to active squares, and keep your pawns solid.",
            Severity.INACCURACY: "A minor positional inaccuracy. Your pieces work best when they control key squares and work together. Try to place pieces where they have scope.",
        },
        MistakeType.ENDGAME: {
            Severity.BLUNDER: "An endgame blunder — in the endgame, every tempo counts. Focus on king activity and passed pawns. One bad move can turn a won endgame into a draw.",
            Severity.MISTAKE: "An endgame mistake — review basic king+pawn vs king endings and rook endgame principles. These are where most games at your level are decided.",
            Severity.INACCURACY: "A slight endgame inaccuracy. Practice basic endgame patterns — they're the most points you can gain for the least study time.",
        },
        MistakeType.OPENING: {
            Severity.BLUNDER: "A serious opening error — you likely violated basic opening principles. Remember: develop knights before bishops, control the center, don't move the same piece twice, and castle early.",
            Severity.MISTAKE: "An opening mistake — you may have brought your queen out too early or neglected development. Stick to simple openings and focus on getting your pieces out.",
            Severity.INACCURACY: "A minor opening inaccuracy. At your level, just follow the basic principles and you'll be fine — no need to memorize theory.",
        },
        MistakeType.UNKNOWN: {
            Severity.BLUNDER: "This was a significant mistake. Review this position carefully — what was the threat you missed? Building the habit of checking opponent's threats will help you avoid these.",
            Severity.MISTAKE: "A notable error. Take a moment to understand why the engine prefers a different move. The pattern here is worth remembering.",
            Severity.INACCURACY: "A small inaccuracy. These add up over the game, but focus on the bigger mistakes first for the most improvement.",
        },
    }

    return type_explanations.get(move.mistake_type, {}).get(
        move.severity,
        "Review this position to understand what went wrong and what to do differently next time.",
    )


async def generate_game_summary(
    analysis: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    """Generate a per-game summary."""
    if settings.openai_api_key:
        return await _llm_summary(analysis, player_rating, target_rating)
    return _fallback_summary(analysis, player_rating)


async def _llm_summary(
    analysis: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)

        player = analysis.white if analysis.player_color == "w" else analysis.black
        opp_color = "b" if analysis.player_color == "w" else "w"
        opponent = analysis.black if analysis.player_color == "w" else analysis.white

        player_blunders = (
            analysis.white_blunders
            if analysis.player_color == "w"
            else analysis.black_blunders
        )
        player_mistakes = (
            analysis.white_mistakes
            if analysis.player_color == "w"
            else analysis.black_mistakes
        )
        player_inacc = (
            analysis.white_inaccuracies
            if analysis.player_color == "w"
            else analysis.black_inaccuracies
        )

        mistake_types = {}
        for fm in analysis.flagged_moves:
            if fm.color == analysis.player_color:
                mistake_types[fm.mistake_type.value] = (
                    mistake_types.get(fm.mistake_type.value, 0) + 1
                )

        type_breakdown = ", ".join(
            f"{v} {k}" for k, v in sorted(mistake_types.items(), key=lambda x: -x[1])
        )

        prompt = f"""You are a chess coach. Summarize this game for a {player_rating}-rated player aiming for {target_rating}.

Player: {player} vs {opponent}. Result: {analysis.result}
Player made: {player_blunders} blunders, {player_mistakes} mistakes, {player_inacc} inaccuracies
Breakdown: {type_breakdown}

Write a 3-5 sentence summary:
1. One thing the player did WELL
2. The main recurring issue
3. One specific, actionable thing to practice

Keep it encouraging and specific. No raw eval numbers."""

        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a supportive chess coach for beginner-intermediate players.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )

        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_summary(analysis, player_rating)


def _fallback_summary(analysis: GameAnalysis, player_rating: int) -> str:
    player = analysis.white if analysis.player_color == "w" else analysis.black
    player_blunders = (
        analysis.white_blunders
        if analysis.player_color == "w"
        else analysis.black_blunders
    )
    player_mistakes = (
        analysis.white_mistakes
        if analysis.player_color == "w"
        else analysis.black_mistakes
    )
    player_inacc = (
        analysis.white_inaccuracies
        if analysis.player_color == "w"
        else analysis.black_inaccuracies
    )

    total_issues = player_blunders + player_mistakes + player_inacc

    mistake_types = {}
    for fm in analysis.flagged_moves:
        if fm.color == analysis.player_color:
            mistake_types[fm.mistake_type.value] = (
                mistake_types.get(fm.mistake_type.value, 0) + 1
            )

    main_issue = (
        max(mistake_types, key=lambda k: mistake_types[k])
        if mistake_types
        else "general play"
    )

    if total_issues == 0:
        return f"Great game, {player}! You played cleanly with no major errors. Keep focusing on consistent development and you'll keep improving."

    lines = [f"Game Summary for {player}:"]

    if player_blunders > 0:
        lines.append(
            f"You made {player_blunders} blunder(s) — moves that significantly worsened your position."
        )
    if player_mistakes > 0:
        lines.append(
            f"You made {player_mistakes} mistake(s) — moves that could have been improved."
        )
    if player_inacc > 0:
        lines.append(
            f"You made {player_inacc} inaccuracy(ies) — minor inaccuracies that added up."
        )

    lines.append(f"Your main issue was {main_issue}.")

    practice_tips = {
        "tactical": "Practice solving tactical puzzles daily (forks, pins, skewers). Focus on 'hanging piece' awareness.",
        "positional": "Study basic pawn structures and piece placement. Ask 'where does this piece belong?' before moving.",
        "endgame": "Review basic endgame principles. King activity and passed pawns are critical.",
        "opening": "Stick to simple openings and focus on rapid development. Knights before bishops, control the center.",
        "unknown": "Review your games after playing to understand what you missed.",
    }

    lines.append(
        f"Practice tip: {practice_tips.get(main_issue, practice_tips['unknown'])}"
    )

    return "\n".join(lines)
