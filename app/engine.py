import chess
import chess.engine
from app.config import settings
from app.models import FlaggedMove, Severity, MistakeType, GameAnalysis
import chess.pgn
import io
import re


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = chess.engine.SimpleEngine.popen_uci(settings.stockfish_path)
    return _engine


def close_engine():
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None


def classify_mistake_type(
    board_before: chess.Board, move: chess.Move, eval_before: float, eval_after: float
) -> MistakeType:
    """Classify the type of mistake based on board context."""
    board = board_before.copy()

    # Check if it's an opening (first 10 moves)
    move_num = board.fullmove_number
    if move_num <= 10:
        return MistakeType.OPENING

    # Check if it's an endgame (few pieces left)
    piece_count = len(board.pieces(chess.PAWN, chess.WHITE)) + len(
        board.pieces(chess.PAWN, chess.BLACK)
    )
    minor_pieces = 0
    for piece_type in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        minor_pieces += len(board.pieces(piece_type, chess.WHITE)) + len(
            board.pieces(piece_type, chess.BLACK)
        )

    if piece_count + minor_pieces <= 8:
        return MistakeType.ENDGAME

    # Tactical checks: hanging pieces, forks, pins
    moved_piece = board.piece_at(move.from_square)
    if moved_piece:
        # Check if we left a piece undefended
        board.push(move)
        captured = board.board_fen()
        board.pop()

    # Check for common tactical patterns
    if abs(eval_after - eval_before) > 200:
        # Large eval swing suggests tactical oversight
        piece = board_before.piece_at(move.from_square)
        if piece and piece.piece_type in [chess.QUEEN, chess.ROOK]:
            return MistakeType.TACTICAL

    # Check if the move allows a simple capture
    board_temp = board_before.copy()
    board_temp.push(move)
    to_square = move.to_square

    # If opponent can simply capture the moved piece for free
    attackers = board_temp.attackers(not board_before.turn, to_square)
    defenders = board_temp.attackers(board_before.turn, to_square)
    if attackers and not defenders:
        return MistakeType.TACTICAL

    # Default to positional
    return MistakeType.POSITIONAL


def classify_severity(centipawn_loss: int) -> Severity:
    if centipawn_loss >= settings.blunder_threshold:
        return Severity.BLUNDER
    elif centipawn_loss >= settings.mistake_threshold:
        return Severity.MISTAKE
    elif centipawn_loss >= settings.inaccuracy_threshold:
        return Severity.INACCURACY
    return Severity.INACCURACY


def analyze_game(pgn_text: str, player_color: str = "w") -> GameAnalysis:
    """Analyze a single game from PGN text."""
    engine = get_engine()

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse PGN")

    board = game.board()
    flagged_moves = []

    # Extract metadata
    white = game.headers.get("White", "Unknown")
    black = game.headers.get("Black", "Unknown")
    result = game.headers.get("Result", "*")
    date = game.headers.get("Date", "Unknown")
    event = game.headers.get("Event", "Unknown")

    # Analyze initial position
    info = engine.analyse(board, chess.engine.Limit(depth=settings.analysis_depth))
    prev_eval = info["score"].relative.score(mate_score=10000)
    if prev_eval is None:
        prev_eval = 0

    moves = list(game.mainline_moves())
    total_moves = len(moves)

    for i, move in enumerate(moves):
        color = "w" if board.turn == chess.WHITE else "b"

        # Store board state before move
        board_before = board.copy()

        # Make the move
        board.push(move)

        # Analyze new position
        info = engine.analyse(board, chess.engine.Limit(depth=settings.analysis_depth))
        current_eval = info["score"].relative.score(mate_score=10000)
        if current_eval is None:
            current_eval = 0

        # Calculate centipawn loss (from the perspective of the player who moved)
        if color == "w":
            cp_loss = prev_eval - current_eval
        else:
            cp_loss = current_eval - prev_eval

        # Get best move from analysis
        best_move = info.get("pv", [None])[0] if info.get("pv") else None
        best_move_san = board.san(best_move) if best_move else ""
        best_move_uci = best_move.uci() if best_move else ""

        # Only flag if it's a significant loss
        if cp_loss >= settings.inaccuracy_threshold:
            severity = classify_severity(cp_loss)
            mistake_type = classify_mistake_type(
                board_before, move, prev_eval, current_eval
            )

            move_number = (i // 2) + 1
            san = board_before.san(move)

            flagged_move = FlaggedMove(
                move_number=move_number,
                color=color,
                san=san,
                uci=move.uci(),
                eval_before=prev_eval,
                eval_after=current_eval,
                centipawn_loss=cp_loss,
                severity=severity,
                mistake_type=mistake_type,
                best_move_uci=best_move_uci,
                best_move_san=best_move_san,
            )
            flagged_moves.append(flagged_move)

        prev_eval = current_eval

    # Count by severity and color
    analysis = GameAnalysis(
        white=white,
        black=black,
        result=result,
        date=date,
        event=event,
        total_moves=total_moves,
        flagged_moves=flagged_moves,
        player_color=player_color,
    )

    for fm in flagged_moves:
        if fm.color == "w":
            if fm.severity == Severity.BLUNDER:
                analysis.white_blunders += 1
            elif fm.severity == Severity.MISTAKE:
                analysis.white_mistakes += 1
            elif fm.severity == Severity.INACCURACY:
                analysis.white_inaccuracies += 1
        else:
            if fm.severity == Severity.BLUNDER:
                analysis.black_blunders += 1
            elif fm.severity == Severity.MISTAKE:
                analysis.black_mistakes += 1
            elif fm.severity == Severity.INACCURACY:
                analysis.black_inaccuracies += 1

    return analysis


def analyze_game_with_board(pgn_text: str, player_color: str = "w"):
    """Analyze and return both the analysis and the game object for board display."""
    engine = get_engine()

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse PGN")

    board = game.board()
    flagged_moves = []
    board_states = []  # Store FEN at each flagged move

    white = game.headers.get("White", "Unknown")
    black = game.headers.get("Black", "Unknown")
    result = game.headers.get("Result", "*")
    date = game.headers.get("Date", "Unknown")
    event = game.headers.get("Event", "Unknown")

    info = engine.analyse(board, chess.engine.Limit(depth=settings.analysis_depth))
    prev_eval = info["score"].relative.score(mate_score=10000)
    if prev_eval is None:
        prev_eval = 0

    moves = list(game.mainline_moves())
    total_moves = len(moves)
    all_moves_data = []

    for i, move in enumerate(moves):
        color = "w" if board.turn == chess.WHITE else "b"
        board_before = board.copy()
        san = board_before.san(move)

        board.push(move)

        info = engine.analyse(board, chess.engine.Limit(depth=settings.analysis_depth))
        current_eval = info["score"].relative.score(mate_score=10000)
        if current_eval is None:
            current_eval = 0

        if color == "w":
            cp_loss = prev_eval - current_eval
        else:
            cp_loss = current_eval - prev_eval

        best_move = info.get("pv", [None])[0] if info.get("pv") else None
        best_move_san = board.san(best_move) if best_move else ""
        best_move_uci = best_move.uci() if best_move else ""

        move_data = {
            "move_number": (i // 2) + 1,
            "color": color,
            "san": san,
            "uci": move.uci(),
            "eval_before": prev_eval,
            "eval_after": current_eval,
            "centipawn_loss": max(0, cp_loss),
            "fen": board.fen(),
        }
        all_moves_data.append(move_data)

        if cp_loss >= settings.inaccuracy_threshold:
            severity = classify_severity(cp_loss)
            mistake_type = classify_mistake_type(
                board_before, move, prev_eval, current_eval
            )

            flagged_move = FlaggedMove(
                move_number=(i // 2) + 1,
                color=color,
                san=san,
                uci=move.uci(),
                eval_before=prev_eval,
                eval_after=current_eval,
                centipawn_loss=cp_loss,
                severity=severity,
                mistake_type=mistake_type,
                best_move_uci=best_move_uci,
                best_move_san=best_move_san,
            )
            flagged_moves.append(flagged_move)
            board_states.append(board_before.fen())

        prev_eval = current_eval

    analysis = GameAnalysis(
        white=white,
        black=black,
        result=result,
        date=date,
        event=event,
        total_moves=total_moves,
        flagged_moves=flagged_moves,
        player_color=player_color,
    )

    for fm in flagged_moves:
        if fm.color == "w":
            if fm.severity == Severity.BLUNDER:
                analysis.white_blunders += 1
            elif fm.severity == Severity.MISTAKE:
                analysis.white_mistakes += 1
            elif fm.severity == Severity.INACCURACY:
                analysis.white_inaccuracies += 1
        else:
            if fm.severity == Severity.BLUNDER:
                analysis.black_blunders += 1
            elif fm.severity == Severity.MISTAKE:
                analysis.black_mistakes += 1
            elif fm.severity == Severity.INACCURACY:
                analysis.black_inaccuracies += 1

    return analysis, all_moves_data, board_states
