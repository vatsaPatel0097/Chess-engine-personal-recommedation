import subprocess
import logging
from app.config import settings
from app.models import FlaggedMove, Severity, MistakeType, GameAnalysis

logger = logging.getLogger(__name__)


def _build_explanation_prompt(
    move: FlaggedMove, game: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    return f"""[Position]
FEN: {move.fen}
Game: {game.white} vs {game.black}
Move: {move.san} (move {move.move_number})
Better move: {move.best_move_san}
Severity: {move.severity.value} ({move.mistake_type.value})
Player rating: {player_rating}

You are a chess coach. Look at the FEN position above. Analyze {move.san} in THIS specific position only:
- What concrete problem does {move.san} create?
- Why is {move.best_move_san} better in this position?
- One specific thing to practice.

No eval numbers like "+2.3". Speak directly to the player."""


def _call_ollama(prompt: str, system: str) -> str:
    full_input = f"{system}\n\n{prompt}"
    result = subprocess.run(
        ["ollama", "run", settings.ollama_model],
        input=full_input.encode("utf-8"),
        capture_output=True,
        timeout=120,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


async def explain_move_with_llm(
    move: FlaggedMove, game: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    """Use local Ollama only for blunders. Templates for everything else."""
    if move.severity != Severity.BLUNDER:
        return _fallback_explanation(move, game, player_rating)

    try:
        prompt = _build_explanation_prompt(move, game, player_rating, target_rating)
        result = _call_ollama(
            prompt, "You are a friendly chess coach who explains things simply."
        )
        logger.info(
            "Ollama used for blunder on move %d (%s)", move.move_number, move.san
        )
        return result
    except Exception:
        logger.warning(
            "Ollama unavailable for move %d — falling back to template",
            move.move_number,
        )
        return _fallback_explanation(move, game, player_rating)


def _fallback_explanation(
    move: FlaggedMove, game: GameAnalysis, player_rating: int
) -> str:
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
    """Try local Ollama for summary. Falls back to template if Ollama is down."""
    try:
        result = await _llm_summary(analysis, player_rating, target_rating)
        logger.info("Game summary generated via Ollama")
        return result
    except Exception:
        logger.warning("Ollama unavailable for summary — using template")
        return _fallback_summary(analysis, player_rating)


async def _llm_summary(
    analysis: GameAnalysis, player_rating: int, target_rating: int
) -> str:
    player = analysis.white if analysis.player_color == "w" else analysis.black
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

    return _call_ollama(
        prompt,
        "You are a supportive chess coach for beginner-intermediate players.",
    )


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
