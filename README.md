# Steam Player Credibility

A web dashboard that analyzes a Steam player's public review history, scores their credibility across seven dimensions, and generates a short AI-written summary.

## Quick Start (Windows)

1. Copy `.env.example` to `.env` and add your API keys (see [API keys](#api-keys) below).
2. **Double-click `launch.bat`** — it creates a virtual environment if needed, installs dependencies, and opens the browser.

## Manual Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Requirements

- Python 3.10+
- A [Steam Web API key](https://steamcommunity.com/dev/apikey)
- An [OpenRouter API key](https://openrouter.ai/) for AI summaries
- Target Steam profile must be set to **Public** (Profile + Game Details)

## How it works

1. Enter a **profile link**, **SteamID64**, or **custom URL** (`/id/…`) on the homepage.
2. A progress bar tracks the search while the app:
   - Resolves the profile to a SteamID64
   - Fetches the player's profile and public reviews
   - Scores credibility across seven dimensions
   - Generates a ~150-word AI summary via OpenRouter
3. The dashboard shows charts, stats, the AI analysis, and a full review table.

**Note:** Steam display names alone usually cannot be searched. Copy the full profile link from Steam → View my profile → Share. For repeat lookups, you can map display names in `.env` (see below).

## Features

- **Search progress bar** — real-time status while fetching and analyzing
- **AI credibility summary** — ~150-word narrative powered by `openrouter/owl-alpha`
- **Positive / negative review** pie chart
- **Review quality distribution** doughnut chart
- **Reviews over time** line chart
- **7-dimension credibility score** (0–100) with breakdown
- **Review table** — filterable, searchable, with game thumbnails and links to the Steam Store

## Credibility Score Dimensions

| Dimension | Max Pts | Description |
|---|---|---|
| Review Volume | 15 | More reviews = stronger signal |
| Review Depth | 25 | Average word count per review |
| Playtime Legitimacy | 20 | % reviews with meaningful hours |
| No Spam Reviews | 15 | Penalizes very short reviews |
| Review Balance | 10 | All-positive accounts score lower |
| Community Trust | 10 | Helpful votes on reviews |
| Game Diversity | 5 | Reviews spread across multiple games |

## API keys

Copy `.env.example` to `.env` and set:

| Variable | Required | Description |
|---|---|---|
| `STEAM_API_KEY` | Yes | Steam Web API key for profiles and reviews |
| `OPENROUTER_API_KEY` | Yes | OpenRouter key for the AI credibility summary |
| `FLASK_SECRET_KEY` | Prod only | Random secret for Flask sessions (auto-generated on Render) |
| `STEAM_NAME_ALIASES` | No | Map display names to SteamID64, e.g. `Name=76561198019362735,Other=76561198…` |
| `APP_URL` | No | Public app URL for OpenRouter headers (Render sets `RENDER_EXTERNAL_URL`) |



## Project structure

```
app.py            Flask routes and search progress API
scraper.py        Steam profile and review fetching
analyzer.py       Credibility scoring and analytics
llm_analysis.py   OpenRouter AI summary generation
templates/        Homepage and dashboard HTML
Procfile          Optional — same start command for Render/Heroku-style hosts
runtime.txt       Python version for Render
launch.bat        Windows one-click launcher (uses .venv)
requirements.txt  Python dependencies
```
