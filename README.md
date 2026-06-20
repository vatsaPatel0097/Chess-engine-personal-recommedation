# Chess Coach - Personalized Improvement

A personal chess coaching web app that analyzes your games, classifies mistakes, and gives plain-language explanations tailored to your rating level.

## What It Does

- **Import games** via PGN paste, Lichess API, or Chess.com API
- **Stockfish engine analysis** on every move
- **Mistake classification**: Blunder / Mistake / Inaccuracy
- **Type tagging**: Tactical, Positional, Endgame, Opening
- **Plain-language explanations** written for your rating level (not raw engine evals)
- **Eval chart** showing evaluation over time
- **Per-game summary** with what went well and what to practice

## Prerequisites

1. **Python 3.10+**
2. **Stockfish engine** - Download from https://stockfishchess.org/download/
   - Windows: Extract `stockfish-windows-x86-64-avx2.exe` (or similar)
   - macOS: `brew install stockfish`
   - Linux: `sudo apt install stockfish` or download binary

## Setup

```bash
# 1. Clone or navigate to project directory
cd chess-coach

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure Stockfish path
# Copy .env.example to .env and update STOCKFISH_PATH
copy .env.example .env
# Edit .env and set STOCKFISH_PATH to your Stockfish executable path
```

## .env Configuration

```
# Path to Stockfish executable
STOCKFISH_PATH=C:\stockfish\stockfish-windows-x86-64-avx2.exe

# Ollama model for AI-powered explanations (must be available locally)
# Run 'ollama list' to see your available models
OLLAMA_MODEL=gemma4:e2b

# Analysis depth (higher = slower but more accurate)
ANALYSIS_DEPTH=15

# Thresholds in centipawns
BLUNDER_THRESHOLD=300
MISTAKE_THRESHOLD=100
INACCURACY_THRESHOLD=50
```

## Run

```bash
python run.py
```

Open http://localhost:8000 in your browser.

## Usage

### Paste PGN
1. Go to the "Paste PGN" tab
2. Paste your game in PGN format
3. Set your rating, target rating, and color
4. Click "Analyze Game"

### Import from Lichess
1. Go to "Import from Lichess" tab
2. Enter your Lichess username
3. Set ratings and color
4. Click "Import & Analyze Latest Game"

### Import from Chess.com
1. Go to "Import from Chess.com" tab
2. Enter your Chess.com username
3. Set ratings and color
4. Click "Import & Analyze Latest Game"

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main page |
| `/analyze-pgn` | POST | Analyze pasted PGN (form submit) |
| `/import-and-analyze` | POST | Import and analyze from platform (form submit) |
| `/api/analyze` | POST | API: Analyze PGN (JSON) |
| `/api/import-lichess` | POST | API: Import from Lichess (JSON) |
| `/api/import-chesscom` | POST | API: Import from Chess.com (JSON) |
| `/health` | GET | Health check |

## Project Structure

```
chess-coach/
├── run.py                  # Entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment config template
├── app/
│   ├── main.py            # FastAPI routes
│   ├── config.py          # Settings
│   ├── models.py          # Pydantic models
│   ├── engine.py          # Stockfish analysis + classification
│   ├── importer.py        # Lichess/Chess.com game import
│   ├── explainer.py       # LLM explanations + summaries
│   ├── static/
│   │   ├── style.css      # Dark theme styles
│   │   └── app.js         # Tab switching
│   └── templates/
│       ├── index.html     # Main page
│       └── result.html    # Analysis results
```

## How It Works

1. **PGN Parsing**: `python-chess` parses the game into a sequence of moves
2. **Engine Analysis**: Stockfish evaluates each position, capturing eval before/after
3. **Mistake Detection**: Compares evals to detect moves with significant centipawn loss
4. **Classification**: Categorizes by severity (blunder/mistake/inaccuracy) and type (tactical/positional/endgame/opening)
5. **Explanation**: Generates beginner-friendly explanation for each flagged move
6. **Summary**: Produces a per-game summary with actionable practice tips

## Notes

- Analysis depth of 15 takes ~2-5 seconds per move depending on position complexity
- Ollama is optional — if the service isn't running, template-based explanations work without it
- Games must be in standard PGN format
- The app analyzes public games only (Lichess/Chess.com public game history)
