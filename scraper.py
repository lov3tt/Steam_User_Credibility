"""
Steam Player Credibility — Scraper
Uses the official Steam Web API (free key required).
Get a free API key at: https://steamcommunity.com/dev/apikey
"""
from __future__ import annotations   # enables list[x] / dict / X | Y on Python 3.8+

import requests
import time
import logging

log = logging.getLogger(__name__)

BASE_API   = "https://api.steampowered.com"
BASE_STORE = "https://store.steampowered.com"

HEADERS = {
    "User-Agent": "SteamPlayerCredibility/1.0 (github.com/local)",
    "Accept-Language": "en-US,en;q=0.9",
}

# Batch size for GetIndividualRecommendations
RECS_BATCH = 200

# Only check games the user has actually played (≥ 1 min playtime)
MIN_PLAYTIME_MINUTES = 1


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get(url: str, params: dict, timeout: int = 12) -> dict:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Public API ────────────────────────────────────────────────────────────────

def validate_api_key(api_key: str) -> bool:
    """Quick check that the API key is valid."""
    try:
        data = _get(
            f"{BASE_API}/ISteamUser/GetPlayerSummaries/v2/",
            {"key": api_key, "steamids": "76561197960287930"},
        )
        return "response" in data
    except Exception:
        return False


def resolve_steamid(username: str, api_key: str) -> str:
    """
    Accept a vanity URL name OR a 17-digit SteamID64.
    Returns the SteamID64 as a string.
    """
    username = username.strip()
    if username.isdigit() and len(username) == 17:
        return username

    data = _get(
        f"{BASE_API}/ISteamUser/ResolveVanityURL/v1/",
        {"key": api_key, "vanityurl": username},
    )
    result = data.get("response", {})
    if result.get("success") != 1:
        raise ValueError(
            f"Could not find Steam profile '{username}'. "
            "Make sure the username is the exact Steam community URL name."
        )
    return result["steamid"]


def get_profile(steamid: str, api_key: str) -> dict:
    """Fetch display name, avatar, and level."""
    # Summary
    data = _get(
        f"{BASE_API}/ISteamUser/GetPlayerSummaries/v2/",
        {"key": api_key, "steamids": steamid},
    )
    players = data.get("response", {}).get("players", [])
    if not players:
        raise ValueError("Steam profile not found or is private.")
    p = players[0]

    # Level (separate call)
    level = "?"
    try:
        lvl_data = _get(
            f"{BASE_API}/IPlayerService/GetSteamLevel/v1/",
            {"key": api_key, "steamid": steamid},
        )
        level = str(lvl_data.get("response", {}).get("player_level", "?"))
    except Exception:
        pass

    return {
        "display_name": p.get("personaname", "Unknown"),
        "avatar": p.get("avatarfull", ""),
        "level": level,
        "profile_url": p.get("profileurl", ""),
        "member_since": "",
    }


def get_owned_games(steamid: str, api_key: str) -> list[dict]:
    """
    Returns a list of dicts: {appid, name, playtime_forever (minutes)}.
    Only includes games with > MIN_PLAYTIME_MINUTES played.
    """
    data = _get(
        f"{BASE_API}/IPlayerService/GetOwnedGames/v1/",
        {
            "key": api_key,
            "steamid": steamid,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        },
    )
    games = data.get("response", {}).get("games", [])
    if not games:
        # Games list might be private
        return []

    return [
        {
            "appid": g["appid"],
            "name": g.get("name", f"App {g['appid']}"),
            "playtime": g.get("playtime_forever", 0),
        }
        for g in games
        if g.get("playtime_forever", 0) >= MIN_PLAYTIME_MINUTES
    ]


def get_recommendations(steamid: str, appids: list[int], api_key: str) -> list[dict]:
    """
    Batch-fetch the user's individual recommendations across all supplied appids.
    Returns a list of parsed review dicts.
    """
    reviews = []

    for start in range(0, len(appids), RECS_BATCH):
        batch = appids[start : start + RECS_BATCH]
        params = {"key": api_key, "steamid": steamid}
        for i, appid in enumerate(batch):
            params[f"appids[{i}]"] = appid

        try:
            data = _get(
                f"{BASE_API}/IRecommendationsService/GetIndividualRecommendations/v1/",
                params,
            )
            recs = data.get("response", {}).get("recommendations", [])
            for r in recs:
                reviews.append(_parse_recommendation(r))
        except requests.HTTPError as e:
            log.warning(f"Batch {start}–{start+len(batch)} failed: {e}")
        except Exception as e:
            log.warning(f"Unexpected error in batch {start}: {e}")

        if start + RECS_BATCH < len(appids):
            time.sleep(0.3)   # rate-limit courtesy

    return reviews


def _parse_recommendation(r: dict) -> dict:
    """Normalise a single recommendation object from the API."""
    from datetime import datetime

    appid     = r.get("appid", 0)
    game_name = r.get("title") or r.get("app_title") or f"App {appid}"
    text      = (r.get("review") or r.get("review_text") or "").strip()
    voted_up  = bool(r.get("voted_up") or r.get("recommended"))

    # playtime is in minutes from the API
    pt_minutes = (
        r.get("playtime_at_review")
        or r.get("playtime_forever")
        or r.get("hours_at_review")
        or 0
    )
    hours = round(pt_minutes / 60, 1) if pt_minutes > 0 else 0.0

    # date
    ts = r.get("timestamp_created") or r.get("time_created") or 0
    try:
        date_str = datetime.fromtimestamp(ts).strftime("%b %d, %Y") if ts else ""
    except Exception:
        date_str = ""

    word_count = len(text.split()) if text else 0
    helpful = int(r.get("votes_up") or r.get("votes_helpful") or 0)

    return {
        "appid": appid,
        "game": game_name,
        "text": text,
        "recommended": voted_up,
        "hours": hours,
        "date": date_str,
        "word_count": word_count,
        "helpful": helpful,
    }


def scrape_reviews(username: str, api_key: str) -> dict:
    """
    Resolve a Steam user, fetch their profile, owned games, and recommendations.
    Returns {profile, reviews, note}.
    """
    if not validate_api_key(api_key):
        raise ValueError("Invalid Steam API key. Check your key at steamcommunity.com/dev/apikey.")

    steamid = resolve_steamid(username, api_key)
    profile = get_profile(steamid, api_key)
    games = get_owned_games(steamid, api_key)

    note = ""
    if not games:
        note = (
            "Game library is private or empty — no reviews could be fetched. "
            "Set Profile and Game Details to Public in Steam privacy settings."
        )
        return {"profile": profile, "reviews": [], "note": note}

    appids = [g["appid"] for g in games]
    name_by_appid = {g["appid"]: g["name"] for g in games}
    reviews = get_recommendations(steamid, appids, api_key)

    for rev in reviews:
        aid = rev.get("appid")
        if aid in name_by_appid:
            rev["game"] = name_by_appid[aid]

    if not reviews:
        note = (
            "No written reviews found for this account. "
            "They may only use the recommend / not recommend buttons without text."
        )

    return {"profile": profile, "reviews": reviews, "note": note}