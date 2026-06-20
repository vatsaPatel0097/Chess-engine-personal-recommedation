import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "chess_coach.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT,
            date TEXT,
            event TEXT,
            player_color TEXT DEFAULT 'w',
            player_rating INTEGER DEFAULT 1200,
            target_rating INTEGER DEFAULT 1400,
            pgn TEXT,
            total_moves INTEGER DEFAULT 0,
            white_blunders INTEGER DEFAULT 0,
            white_mistakes INTEGER DEFAULT 0,
            white_inaccuracies INTEGER DEFAULT 0,
            black_blunders INTEGER DEFAULT 0,
            black_mistakes INTEGER DEFAULT 0,
            black_inaccuracies INTEGER DEFAULT 0,
            summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS flagged_moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            move_number INTEGER,
            color TEXT,
            san TEXT,
            uci TEXT,
            eval_before REAL DEFAULT 0,
            eval_after REAL DEFAULT 0,
            centipawn_loss INTEGER DEFAULT 0,
            severity TEXT,
            mistake_type TEXT,
            best_move_uci TEXT DEFAULT '',
            best_move_san TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            description TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            severity_avg REAL DEFAULT 0,
            phase TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            games TEXT DEFAULT '[]'
        );
    """)
    conn.commit()
    conn.close()


def save_game(analysis, pgn_text, player_rating, target_rating):
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO games
        (white, black, result, date, event, player_color, player_rating, target_rating,
         pgn, total_moves, white_blunders, white_mistakes, white_inaccuracies,
         black_blunders, black_mistakes, black_inaccuracies, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            analysis.white,
            analysis.black,
            analysis.result,
            analysis.date,
            analysis.event,
            analysis.player_color,
            player_rating,
            target_rating,
            pgn_text,
            analysis.total_moves,
            analysis.white_blunders,
            analysis.white_mistakes,
            analysis.white_inaccuracies,
            analysis.black_blunders,
            analysis.black_mistakes,
            analysis.black_inaccuracies,
            analysis.summary,
        ),
    )
    game_id = cursor.lastrowid

    for fm in analysis.flagged_moves:
        conn.execute(
            """INSERT INTO flagged_moves
            (game_id, move_number, color, san, uci, eval_before, eval_after,
             centipawn_loss, severity, mistake_type, best_move_uci, best_move_san, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                game_id,
                fm.move_number,
                fm.color,
                fm.san,
                fm.uci,
                fm.eval_before,
                fm.eval_after,
                fm.centipawn_loss,
                fm.severity.value if hasattr(fm.severity, "value") else fm.severity,
                fm.mistake_type.value
                if hasattr(fm.mistake_type, "value")
                else fm.mistake_type,
                fm.best_move_uci,
                fm.best_move_san,
                fm.explanation,
            ),
        )

    conn.commit()
    conn.close()
    return game_id


def get_all_games(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM games ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_game(game_id):
    conn = get_db()
    game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if not game:
        conn.close()
        return None, []
    moves = conn.execute(
        "SELECT * FROM flagged_moves WHERE game_id = ? ORDER BY move_number, color",
        (game_id,),
    ).fetchall()
    conn.close()
    return dict(game), [dict(m) for m in moves]


def get_all_flagged_moves():
    conn = get_db()
    rows = conn.execute(
        """SELECT fm.*, g.white, g.black, g.date, g.player_color, g.player_rating
        FROM flagged_moves fm
        JOIN games g ON fm.game_id = g.id
        ORDER BY g.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_game_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM games").fetchone()["c"]
    conn.close()
    return count


def get_stats_summary():
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*) as total_games,
            SUM(total_moves) as total_moves,
            SUM(white_blunders + black_blunders) as total_blunders,
            SUM(white_mistakes + black_mistakes) as total_mistakes,
            SUM(white_inaccuracies + black_inaccuracies) as total_inaccuracies,
            AVG(player_rating) as avg_rating
        FROM games
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_mistake_trend():
    conn = get_db()
    rows = conn.execute("""
        SELECT
            g.created_at,
            g.id,
            SUM(CASE WHEN fm.severity = 'blunder' THEN 1 ELSE 0 END) as blunders,
            SUM(CASE WHEN fm.severity = 'mistake' THEN 1 ELSE 0 END) as mistakes,
            SUM(CASE WHEN fm.severity = 'inaccuracy' THEN 1 ELSE 0 END) as inaccuracies
        FROM games g
        LEFT JOIN flagged_moves fm ON fm.game_id = g.id
        GROUP BY g.id
        ORDER BY g.created_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_type_distribution(player_color=None):
    conn = get_db()
    query = "SELECT mistake_type, COUNT(*) as count FROM flagged_moves"
    params = []
    if player_color:
        query += " WHERE color = ?"
        params.append(player_color)
    query += " GROUP BY mistake_type ORDER BY count DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_game(game_id):
    conn = get_db()
    conn.execute("DELETE FROM flagged_moves WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()


init_db()
