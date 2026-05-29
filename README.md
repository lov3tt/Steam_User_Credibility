# Steam Player Credibility

A professional web dashboard that analyzes a Steam player's review history and scores their credibility using the official Steam Web API.

## Quick Start (Windows)

**Double-click `launch.bat`** — it installs dependencies and opens the browser automatically.

## Manual Start

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Requirements

- Python 3.10+
- A **free** Steam Web API key → https://steamcommunity.com/dev/apikey
  (Sign in, enter any website name, done)
- Target Steam profile must be set to **Public** (Profile + Game Details)

## How it works

1. Enter a Steam username + your free API key on the homepage
2. The app uses the official Steam Web API to:
   - Resolve the username to a SteamID64
   - Fetch the player's profile and game library
   - Retrieve all individual game recommendations by the player
3. The dashboard shows charts, stats, and a credibility score

## Features

- Positive / negative review pie chart
- Top reviewed games bar chart
- Review quality distribution doughnut chart
- Reviews over time line chart
- 7-dimension credibility scoring (0–100)
- Filterable & searchable review table

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

## Privacy

Your API key is stored only in your browser session and is never sent anywhere except the official Steam API.