import chess
import chess.pgn
import subprocess
import threading
import queue
import io
import time as _time
from app.config import settings
from app.models import FlaggedMove, Severity, MistakeType, GameAnalysis


class StockfishEngine:
    def __init__(self, path, depth=10):
        self.depth = depth
        self._q = queue.Queue()
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._send("uci")
        self._drain_until("uciok")
        self._send("isready")
        self._drain_until("readyok")

    def _read_loop(self):
        try:
            for line in iter(self.proc.stdout.readline, ""):
                self._q.put(line)
        except Exception:
            self._q.put(None)
        self._q.put(None)

    def _send(self, cmd):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _drain_until(self, token):
        deadline = _time.time() + 15
        while _time.time() < deadline:
            try:
                raw = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if raw is None:
                break
            line = raw.strip()
            if token in line:
                return line
        return ""

    def evaluate(self, fen):
        self._send(f"position fen {fen}")
        self._send(f"go depth {self.depth}")
        best_move = None
        score_cp = 0
        deadline = _time.time() + 30
        while _time.time() < deadline:
            try:
                raw = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if raw is None:
                break
            line = raw.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                best_move = parts[1] if len(parts) > 1 else None
                break
            elif line.startswith("info") and "score" in line:
                parts = line.split()
                try:
                    idx = parts.index("score")
                    score_type = parts[idx + 1]
                    score_val = int(parts[idx + 2])
                    if score_type == "cp":
                        score_cp = score_val
                    elif score_type == "mate":
                        score_cp = 10000 if score_val > 0 else -10000
                except (ValueError, IndexError):
                    pass
        return score_cp, best_move

    def quit(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def classify_mistake_type(board_before, move, eval_before, eval_after):
    move_num = board_before.fullmove_number
    if move_num <= 10:
        return MistakeType.OPENING

    piece_count = len(board_before.pieces(chess.PAWN, chess.WHITE)) + len(
        board_before.pieces(chess.PAWN, chess.BLACK)
    )
    minor_pieces = 0
    for pt in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        minor_pieces += len(board_before.pieces(pt, chess.WHITE)) + len(
            board_before.pieces(pt, chess.BLACK)
        )
    if piece_count + minor_pieces <= 8:
        return MistakeType.ENDGAME

    board_temp = board_before.copy()
    board_temp.push(move)
    to_square = move.to_square
    attackers = board_temp.attackers(not board_before.turn, to_square)
    defenders = board_temp.attackers(board_before.turn, to_square)
    if attackers and not defenders:
        return MistakeType.TACTICAL

    if abs(eval_after - eval_before) > 200:
        piece = board_before.piece_at(move.from_square)
        if piece and piece.piece_type in [chess.QUEEN, chess.ROOK]:
            return MistakeType.TACTICAL

    return MistakeType.POSITIONAL


def classify_severity(centipawn_loss):
    if centipawn_loss >= settings.blunder_threshold:
        return Severity.BLUNDER
    elif centipawn_loss >= settings.mistake_threshold:
        return Severity.MISTAKE
    return Severity.INACCURACY


def analyze_game_with_board(pgn_text, player_color="w"):
    sf = StockfishEngine(settings.stockfish_path, settings.analysis_depth)
    try:
        return _run_analysis(sf, pgn_text, player_color)
    finally:
        sf.quit()


def analyze_game(pgn_text, player_color="w"):
    sf = StockfishEngine(settings.stockfish_path, settings.analysis_depth)
    try:
        result = _run_analysis(sf, pgn_text, player_color)
        return result[0]
    finally:
        sf.quit()


def _eval_to_white_perspective(score_cp, is_white_turn):
    """Convert Stockfish eval (side-to-move perspective) to White's perspective."""
    return score_cp if is_white_turn else -score_cp


def _run_analysis(sf, pgn_text, player_color):
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse PGN. Make sure you paste a valid PGN.")

    board = game.board()
    flagged_moves = []
    board_states = []

    white = game.headers.get("White", "Unknown")
    black = game.headers.get("Black", "Unknown")
    result = game.headers.get("Result", "*")
    date = game.headers.get("Date", "Unknown")
    event = game.headers.get("Event", "Unknown")

    raw_eval, _ = sf.evaluate(board.fen())
    prev_eval_white = _eval_to_white_perspective(raw_eval, board.turn == chess.WHITE)

    moves = list(game.mainline_moves())
    total_moves = len(moves)
    all_moves_data = []

    for i, move in enumerate(moves):
        color = "w" if board.turn == chess.WHITE else "b"
        board_before = board.copy()
        san = board_before.san(move)

        board.push(move)

        raw_eval_after, _ = sf.evaluate(board.fen())
        eval_after_white = _eval_to_white_perspective(
            raw_eval_after, board.turn == chess.WHITE
        )

        if color == "w":
            cp_loss = prev_eval_white - eval_after_white
        else:
            cp_loss = eval_after_white - prev_eval_white

        best_move_san = ""
        best_move_uci = ""
        if cp_loss >= settings.inaccuracy_threshold:
            _, bm = sf.evaluate(board_before.fen())
            best_move_uci = bm or ""
            if best_move_uci and best_move_uci != "(none)":
                try:
                    best_move_san = board_before.san(chess.Move.from_uci(best_move_uci))
                except Exception:
                    best_move_san = best_move_uci

        move_data = {
            "move_number": (i // 2) + 1,
            "color": color,
            "san": san,
            "uci": move.uci(),
            "eval_before": prev_eval_white,
            "eval_after": eval_after_white,
            "centipawn_loss": max(0, cp_loss),
            "fen": board.fen(),
        }
        all_moves_data.append(move_data)

        if cp_loss >= settings.inaccuracy_threshold and i > 0:
            severity = classify_severity(cp_loss)
            mistake_type = classify_mistake_type(
                board_before, move, prev_eval_white, eval_after_white
            )

            flagged_move = FlaggedMove(
                move_number=(i // 2) + 1,
                color=color,
                san=san,
                uci=move.uci(),
                fen=board_before.fen(),
                eval_before=prev_eval_white,
                eval_after=eval_after_white,
                centipawn_loss=cp_loss,
                severity=severity,
                mistake_type=mistake_type,
                best_move_uci=best_move_uci,
                best_move_san=best_move_san,
            )
            flagged_moves.append(flagged_move)
            board_states.append(board_before.fen())

        prev_eval_white = eval_after_white

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
