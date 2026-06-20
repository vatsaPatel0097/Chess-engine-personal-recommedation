from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio

from app.config import settings
from app.engine import analyze_game, analyze_game_with_board
from app.models import AnalysisRequest, LichessImportRequest, ChessComImportRequest
from app.importer import import_games
from app.explainer import explain_move_with_llm, generate_game_summary

app = FastAPI(title="Chess Coach", description="Personalized Chess Improvement Coach")

static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze-pgn")
async def analyze_pgn(
    request: Request,
    pgn: str = Form(...),
    player_rating: int = Form(1200),
    target_rating: int = Form(1400),
    player_color: str = Form("w"),
):
    try:
        analysis, all_moves, board_states = analyze_game_with_board(pgn, player_color)

        # Generate explanations for flagged moves
        for fm in analysis.flagged_moves:
            fm.explanation = await explain_move_with_llm(
                fm, analysis, player_rating, target_rating
            )

        # Generate summary
        analysis.summary = await generate_game_summary(
            analysis, player_rating, target_rating
        )

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "analysis": analysis,
                "all_moves": all_moves,
                "board_states": board_states,
                "player_rating": player_rating,
                "target_rating": target_rating,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
            },
        )


@app.post("/api/analyze")
async def api_analyze(req: AnalysisRequest):
    try:
        analysis, all_moves, board_states = analyze_game_with_board(
            req.pgn, req.player_color
        )

        for fm in analysis.flagged_moves:
            fm.explanation = await explain_move_with_llm(
                fm, analysis, req.player_rating, req.target_rating
            )

        analysis.summary = await generate_game_summary(
            analysis, req.player_rating, req.target_rating
        )

        return {
            "analysis": analysis.model_dump(),
            "all_moves": all_moves,
            "board_states": board_states,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/import-lichess")
async def api_import_lichess(req: LichessImportRequest):
    try:
        games = await import_games(req, "lichess")
        return {"games": games, "count": len(games)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/import-chesscom")
async def api_import_chesscom(req: ChessComImportRequest):
    try:
        games = await import_games(req, "chesscom")
        return {"games": games, "count": len(games)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/import-and-analyze")
async def import_and_analyze(
    request: Request,
    platform: str = Form(...),
    username: str = Form(...),
    player_rating: int = Form(1200),
    target_rating: int = Form(1400),
    player_color: str = Form("w"),
    max_games: int = Form(1),
):
    try:
        if platform == "lichess":
            req = LichessImportRequest(
                username=username,
                player_rating=player_rating,
                target_rating=target_rating,
                max_games=max_games,
            )
        else:
            req = ChessComImportRequest(
                username=username,
                player_rating=player_rating,
                target_rating=target_rating,
                max_games=max_games,
            )

        games = await import_games(req, platform)

        if not games:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": f"No games found for {username} on {platform}",
                },
            )

        # Analyze the first game
        pgn = games[0]
        analysis, all_moves, board_states = analyze_game_with_board(pgn, player_color)

        for fm in analysis.flagged_moves:
            fm.explanation = await explain_move_with_llm(
                fm, analysis, player_rating, target_rating
            )

        analysis.summary = await generate_game_summary(
            analysis, player_rating, target_rating
        )

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "analysis": analysis,
                "all_moves": all_moves,
                "board_states": board_states,
                "player_rating": player_rating,
                "target_rating": target_rating,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
            },
        )


@app.get("/health")
async def health():
    return {"status": "ok", "stockfish_path": settings.stockfish_path}
