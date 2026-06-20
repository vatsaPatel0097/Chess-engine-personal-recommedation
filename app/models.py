from pydantic import BaseModel
from enum import Enum


class Severity(str, Enum):
    BLUNDER = "blunder"
    MISTAKE = "mistake"
    INACCURACY = "inaccuracy"


class MistakeType(str, Enum):
    TACTICAL = "tactical"
    POSITIONAL = "positional"
    ENDGAME = "endgame"
    OPENING = "opening"
    UNKNOWN = "unknown"


class FlaggedMove(BaseModel):
    move_number: int
    color: str  # "w" or "b"
    san: str  # move in standard algebraic notation
    uci: str  # move in UCI notation
    fen: str = ""  # FEN position BEFORE the move
    eval_before: float  # centipawns
    eval_after: float  # centipawns
    centipawn_loss: int
    severity: Severity
    mistake_type: MistakeType
    best_move_uci: str
    best_move_san: str
    explanation: str = ""


class GameAnalysis(BaseModel):
    white: str
    black: str
    result: str
    date: str
    event: str
    total_moves: int
    flagged_moves: list[FlaggedMove]
    white_blunders: int = 0
    white_mistakes: int = 0
    white_inaccuracies: int = 0
    black_blunders: int = 0
    black_mistakes: int = 0
    black_inaccuracies: int = 0
    summary: str = ""
    player_color: str = "w"


class AnalysisRequest(BaseModel):
    pgn: str
    player_rating: int = 1200
    target_rating: int = 1400
    player_color: str = "w"


class LichessImportRequest(BaseModel):
    username: str
    player_rating: int = 1200
    target_rating: int = 1400
    max_games: int = 5


class ChessComImportRequest(BaseModel):
    username: str
    player_rating: int = 1200
    target_rating: int = 1400
    max_games: int = 5
