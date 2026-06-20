from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio
import traceback

from app.config import settings
from app.engine import analyze_game_with_board
from app.models import AnalysisRequest, LichessImportRequest, ChessComImportRequest
from app.importer import import_games
from app.explainer import explain_move_with_llm, generate_game_summary
from app.database import (
    save_game,
    get_all_games,
    get_game,
    get_game_count,
    get_stats_summary,
    delete_game,
)
from app.patterns import analyze_patterns, generate_study_plan, get_progress_data

app = FastAPI(title="Chess Coach", description="Personalized Chess Improvement Coach")

static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = get_stats_summary()
    return templates.TemplateResponse(
        "index.html", {"request": request, "stats": stats}
    )


@app.post("/analyze-pgn", response_class=HTMLResponse)
async def analyze_pgn(
    request: Request,
    pgn: str = Form(...),
    player_rating: int = Form(1200),
    target_rating: int = Form(1400),
    player_color: str = Form("w"),
):
    try:
        loop = asyncio.get_event_loop()
        analysis, all_moves, board_states = await loop.run_in_executor(
            None, analyze_game_with_board, pgn, player_color
        )

        for fm in analysis.flagged_moves:
            fm.explanation = await explain_move_with_llm(
                fm, analysis, player_rating, target_rating
            )

        analysis.summary = await generate_game_summary(
            analysis, player_rating, target_rating
        )

        game_id = save_game(analysis, pgn, player_rating, target_rating)

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "analysis": analysis,
                "all_moves": all_moves,
                "board_states": board_states,
                "player_rating": player_rating,
                "target_rating": target_rating,
                "game_id": game_id,
            },
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ANALYSIS ERROR: {e}\n{tb}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"{type(e).__name__}: {e}",
                "stats": get_stats_summary(),
            },
        )


@app.post("/import-and-analyze", response_class=HTMLResponse)
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
                    "stats": get_stats_summary(),
                },
            )

        pgn = games[0]
        loop = asyncio.get_event_loop()
        analysis, all_moves, board_states = await loop.run_in_executor(
            None, analyze_game_with_board, pgn, player_color
        )

        for fm in analysis.flagged_moves:
            fm.explanation = await explain_move_with_llm(
                fm, analysis, player_rating, target_rating
            )

        analysis.summary = await generate_game_summary(
            analysis, player_rating, target_rating
        )

        game_id = save_game(analysis, pgn, player_rating, target_rating)

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "analysis": analysis,
                "all_moves": all_moves,
                "board_states": board_states,
                "player_rating": player_rating,
                "target_rating": target_rating,
                "game_id": game_id,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"{type(e).__name__}: {e}",
                "stats": get_stats_summary(),
            },
        )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    games = get_all_games()
    return templates.TemplateResponse(
        "history.html", {"request": request, "games": games}
    )


@app.get("/game/{game_id}", response_class=HTMLResponse)
async def game_detail(request: Request, game_id: int):
    game, moves = get_game(game_id)
    if not game:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        "game_detail.html",
        {
            "request": request,
            "game": game,
            "moves": moves,
        },
    )


@app.post("/game/{game_id}/delete")
async def game_delete(game_id: int):
    delete_game(game_id)
    return RedirectResponse("/history", status_code=302)


@app.get("/patterns", response_class=HTMLResponse)
async def patterns_page(request: Request):
    patterns = analyze_patterns()
    return templates.TemplateResponse(
        "patterns.html", {"request": request, "patterns": patterns}
    )


@app.get("/study-plan", response_class=HTMLResponse)
async def study_plan_page(request: Request, rating: int = 1200, target: int = 1400):
    plan = generate_study_plan(rating, target)
    return templates.TemplateResponse(
        "study_plan.html",
        {"request": request, "plan": plan, "rating": rating, "target": target},
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    data = get_progress_data()
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "data": data}
    )


@app.get("/api/stats")
async def api_stats():
    return get_stats_summary()


@app.get("/api/patterns")
async def api_patterns():
    return analyze_patterns()


@app.get("/api/progress")
async def api_progress():
    return get_progress_data()


@app.get("/health")
async def health():
    return {"status": "ok", "stockfish_path": settings.stockfish_path}
