"""
OpenRouter LLM — AI credibility narrative for dashboard.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/owl-alpha"
TARGET_WORDS = 150


def _app_url() -> str:
    return (
        os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("APP_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")


def get_openrouter_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENROUTER_API_KEY is not set in .env")
    return key


def _build_prompt(profile: dict, analytics: dict) -> str:
    breakdown_lines = []
    for item in analytics.get("credibility_breakdown", []):
        breakdown_lines.append(
            f"- {item['label']}: {item['earned']}/{item['max']} pts — {item['note']}"
        )

    top_games = analytics.get("top_games", [])[:5]
    top_games_text = ", ".join(f"{g['game']} ({g['count']} reviews)" for g in top_games) or "N/A"

    return f"""Write a credibility assessment for this Steam reviewer.

Player: {profile.get('display_name', 'Unknown')}
Steam level: {profile.get('level', 'Unknown')}
Overall credibility score: {analytics.get('credibility_score', 0)}/100
Verdict: {analytics.get('verdict', 'Unknown')}

Review statistics:
- Total reviews: {analytics.get('total', 0)}
- Positive: {analytics.get('pos_count', 0)} ({analytics.get('pos_pct', 0)}%)
- Negative: {analytics.get('neg_count', 0)} ({analytics.get('neg_pct', 0)}%)
- Average words per review: {analytics.get('avg_words', 0)} (median: {analytics.get('median_words', 0)})
- Average hours at review time: {analytics.get('avg_hours', 0)}
- High-quality reviews (≥50 words & ≥10 hrs): {analytics.get('quality_reviews', 0)}
- Spam/short reviews (<5 words): {analytics.get('spam_reviews', 0)}
- Low-hour reviews (<2 hrs): {analytics.get('low_hour_reviews', 0)} ({analytics.get('pct_low_hours', 0)}%)
- Total helpful votes: {analytics.get('total_helpful', 0)} (avg {analytics.get('avg_helpful', 0)} per review)
- Unique games reviewed: {analytics.get('unique_games', 0)}
- Most reviewed game: {analytics.get('most_reviewed_game', 'N/A')} ({analytics.get('most_reviewed_count', 0)} reviews, {analytics.get('pct_single_game', 0)}% of all reviews)
- Top reviewed games: {top_games_text}

Score breakdown:
{chr(10).join(breakdown_lines)}

Write a clean, concise summary in plain English (no bullet points, no markdown headers).
In one or two short paragraphs, state whether this reviewer appears trustworthy, the strongest signal from the data, and the main red flag or caveat if any.
Be direct and balanced — cite only the most relevant stats, not every metric.
Target length: approximately {TARGET_WORDS} words."""


def generate_credibility_analysis(profile: dict, analytics: dict) -> str:
    """Call OpenRouter and return an ~150-word credibility summary."""
    if analytics.get("total", 0) == 0:
        return (
            "This profile has no public reviews to analyze. "
            "Without review history, credibility cannot be assessed."
        )

    api_key = get_openrouter_api_key()
    prompt = _build_prompt(profile, analytics)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert analyst evaluating Steam user review credibility. "
                    "Write a tight, clean summary for a dashboard audience — no filler, no repetition. "
                    "Do not use markdown formatting."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 280,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": _app_url(),
        "X-Title": "Steam Player Credibility",
    }

    try:
        resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("Empty response from OpenRouter")
        return content
    except requests.RequestException as exc:
        log.error("OpenRouter request failed: %s", exc)
        raise ValueError("Unable to generate AI analysis right now. Please try again later.") from exc
    except (KeyError, IndexError, TypeError) as exc:
        log.error("Unexpected OpenRouter response: %s", exc)
        raise ValueError("Received an invalid response from the AI service.") from exc
