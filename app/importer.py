import httpx
import chess.pgn
import io
from app.models import LichessImportRequest, ChessComImportRequest


async def fetch_lichess_games(username: str, max_games: int = 5) -> list[str]:
    """Fetch recent games from Lichess public API."""
    url = f"https://lichess.org/api/games/user/{username}"
    params = {"max": max_games, "pgnInJson": False}
    headers = {"Accept": "application/x-chess-pgn"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

    pgn_text = response.text
    # Split multiple games
    games = []
    current_game = []
    for line in pgn_text.split("\n"):
        if line.startswith("[Event ") and current_game:
            games.append("\n".join(current_game))
            current_game = []
        current_game.append(line)
    if current_game:
        games.append("\n".join(current_game))

    return [g for g in games if g.strip()]


async def fetch_chesscom_games(username: str, max_games: int = 5) -> list[str]:
    """Fetch recent games from Chess.com public API."""
    async with httpx.AsyncClient() as client:
        # Get player's game archive list
        archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
        response = await client.get(archives_url, timeout=30)
        response.raise_for_status()
        archives = response.json().get("archives", [])

        if not archives:
            return []

        # Get latest archive
        latest_archive_url = archives[-1]
        response = await client.get(latest_archive_url, timeout=30)
        response.raise_for_status()
        games_data = response.json().get("games", [])

        # Extract PGN from games
        games = []
        for game_data in games_data[:max_games]:
            pgn = game_data.get("pgn", "")
            if pgn:
                games.append(pgn)

        return games


async def import_games(
    request: LichessImportRequest | ChessComImportRequest, platform: str
) -> list[str]:
    """Import games from specified platform."""
    if platform == "lichess":
        return await fetch_lichess_games(request.username, request.max_games)
    elif platform == "chesscom":
        return await fetch_chesscom_games(request.username, request.max_games)
    else:
        raise ValueError(f"Unknown platform: {platform}")
