"""
Steam Player Credibility — Scraper
Uses the Steam Web API for profiles and Steam Community pages for reviews.
"""
from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

log = logging.getLogger(__name__)

BASE_API = "https://api.steampowered.com"
BASE_COMMUNITY = "https://steamcommunity.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SteamPlayerCredibility/1.1",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_REVIEW_PAGES = 40
_game_name_cache: dict[int, str] = {}
_display_name_aliases: dict[str, str] | None = None


def _load_display_name_aliases() -> dict[str, str]:
    """
    Optional map of display name -> SteamID64 from .env, e.g.
    STEAM_NAME_ALIASES=VenkraCade=76561198019362735,OtherName=76561198...
    """
    global _display_name_aliases
    if _display_name_aliases is not None:
        return _display_name_aliases

    aliases: dict[str, str] = {}
    raw = os.environ.get("STEAM_NAME_ALIASES", "")
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, steamid = entry.split("=", 1)
        name = name.strip().lower()
        steamid = steamid.strip()
        if name and steamid.isdigit() and len(steamid) == 17:
            aliases[name] = steamid

    _display_name_aliases = aliases
    return aliases


def get_steam_api_key() -> str:
    key = os.environ.get("STEAM_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "STEAM_API_KEY is not set, add the api key to the .env file"
        )
    return key


def _get(url: str, params: dict, timeout: int = 12) -> dict:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_html(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_profile_input(raw: str) -> tuple[str, str]:
    """
    Parse user input into (lookup_value, kind).
    kind is 'steamid' or 'vanity'.
    """
    raw = raw.strip().lstrip("@")
    if not raw:
        return "", "vanity"

    m = re.search(r"steamcommunity\.com/profiles/(\d{17})", raw, re.I)
    if m:
        return m.group(1), "steamid"

    m = re.search(r"steamcommunity\.com/id/([^/?#\s]+)", raw, re.I)
    if m:
        return m.group(1), "vanity"

    if raw.isdigit() and len(raw) == 17:
        return raw, "steamid"

    return raw, "vanity"


def _resolve_steamid_from_community(vanity: str) -> str | None:
    """Fallback when the Web API vanity lookup fails."""
    try:
        html = _get_html(f"{BASE_COMMUNITY}/id/{vanity}")
    except Exception:
        return None

    if "could not be found" in html.lower():
        return None

    m = re.search(r'g_steamID\s*=\s*"(\d{17})"', html)
    if m:
        return m.group(1)

    m = re.search(r"steamcommunity\.com/profiles/(\d{17})", html)
    if m:
        return m.group(1)

    return None


def validate_api_key(api_key: str) -> bool:
    try:
        data = _get(
            f"{BASE_API}/ISteamUser/GetPlayerSummaries/v2/",
            {"key": api_key, "steamids": "76561197960287930"},
        )
        return "response" in data
    except Exception:
        return False


def resolve_steamid(username: str, api_key: str) -> str:
    lookup, kind = parse_profile_input(username)

    if kind == "steamid":
        return lookup

    # Display names (e.g. "VenkraCade") are not the same as /id/ custom URLs.
    # Steam has no public API to search by display name — optional .env aliases only.
    alias_id = _load_display_name_aliases().get(lookup.lower())
    if alias_id:
        return alias_id

    data = _get(
        f"{BASE_API}/ISteamUser/ResolveVanityURL/v1/",
        {"key": api_key, "vanityurl": lookup},
    )
    result = data.get("response", {})
    if result.get("success") == 1:
        return result["steamid"]

    steamid = _resolve_steamid_from_community(lookup)
    if steamid:
        return steamid

    raise ValueError(
        f"Could not find a Steam profile for '{lookup}'. "
        "Display names (the name at the top of a profile) are not searchable on Steam. "
        "Paste the full profile link (steamcommunity.com/profiles/…) or the 17-digit SteamID64. "
        "If you use this tool often for the same person, add "
        "STEAM_NAME_ALIASES=TheirDisplayName=76561198019362735 to your .env file."
    )


def get_profile(steamid: str, api_key: str) -> dict:
    data = _get(
        f"{BASE_API}/ISteamUser/GetPlayerSummaries/v2/",
        {"key": api_key, "steamids": steamid},
    )
    players = data.get("response", {}).get("players", [])
    if not players:
        raise ValueError("Steam profile not found or is private.")

    p = players[0]
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


def _profile_reviews_path(steamid: str, vanity: str | None) -> str:
    if vanity:
        return f"id/{vanity}"
    return f"profiles/{steamid}"


def _game_store_url(appid: int) -> str:
    return f"https://store.steampowered.com/app/{appid}/"


def _game_thumbnail_url(appid: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_sm_120.jpg"


def _fetch_game_name(appid: int) -> str:
    if appid in _game_name_cache:
        return _game_name_cache[appid]

    name = f"App {appid}"
    try:
        data = _get(
            f"https://store.steampowered.com/api/appdetails",
            {"appids": appid, "filters": "basic"},
            timeout=10,
        )
        entry = data.get(str(appid), {})
        if entry.get("success"):
            name = entry.get("data", {}).get("name", name)
    except Exception as e:
        log.debug(f"Could not fetch name for app {appid}: {e}")

    _game_name_cache[appid] = name
    return name


def _parse_review_box(box) -> dict | None:
    link = box.select_one(".leftcol a[href*='/app/']")
    if not link:
        return None

    m = re.search(r"/app/(\d+)", link.get("href", ""))
    if not m:
        return None
    appid = int(m.group(1))

    thumb_el = link.select_one("img")
    thumbnail = thumb_el.get("src", "").strip() if thumb_el else ""
    if not thumbnail:
        thumbnail = _game_thumbnail_url(appid)

    title_el = box.select_one(".title a")
    title_text = title_el.get_text(strip=True) if title_el else ""
    recommended = title_text.lower() == "recommended"

    hours = 0.0
    hours_el = box.select_one(".hours")
    if hours_el:
        hm = re.search(r"([\d.]+)\s*hrs", hours_el.get_text())
        if hm:
            hours = float(hm.group(1))

    content_el = box.select_one(".content")
    text = content_el.get_text(" ", strip=True) if content_el else ""

    date_str = ""
    posted_el = box.select_one(".posted")
    if posted_el:
        pm = re.search(r"Posted\s+(.+)", posted_el.get_text(strip=True))
        if pm:
            date_str = pm.group(1).strip().rstrip(".")

    helpful = 0
    header_el = box.select_one(".header")
    if header_el:
        hm = re.search(
            r"(\d+)\s+people found this review helpful",
            header_el.get_text(" ", strip=True),
        )
        if hm:
            helpful = int(hm.group(1))

    return {
        "appid": appid,
        "game": _fetch_game_name(appid),
        "game_url": _game_store_url(appid),
        "game_thumbnail": thumbnail,
        "text": text,
        "recommended": recommended,
        "hours": hours,
        "date": date_str,
        "word_count": len(text.split()) if text else 0,
        "helpful": helpful,
    }


def scrape_community_reviews(steamid: str, vanity: str | None = None) -> tuple[list[dict], str]:
    """
    Scrape public reviews from the user's Steam Community recommended page.
    Returns (reviews, status_note).
    """
    path = _profile_reviews_path(steamid, vanity)
    reviews: list[dict] = []
    private = False

    for page in range(1, MAX_REVIEW_PAGES + 1):
        url = f"{BASE_COMMUNITY}/{path}/recommended/?p={page}&l=english"
        try:
            html = _get_html(url)
        except Exception as e:
            log.warning(f"Failed to load reviews page {page}: {e}")
            break

        if "This profile is private" in html:
            private = True
            break

        if "could not be found" in html.lower():
            break

        soup = BeautifulSoup(html, "lxml")
        boxes = soup.select(".review_box")
        if not boxes:
            break

        for box in boxes:
            parsed = _parse_review_box(box)
            if parsed:
                reviews.append(parsed)

        paging = soup.select_one(".workshopBrowsePagingInfo")
        if paging:
            pm = re.search(
                r"Showing\s+(\d+)-(\d+)\s+of\s+(\d+)",
                paging.get_text(strip=True),
            )
            if pm and int(pm.group(2)) >= int(pm.group(3)):
                break

        time.sleep(0.25)

    if private:
        return [], "private"
    return reviews, ""


def scrape_reviews(username: str) -> dict:
    """
    Resolve a Steam user, fetch profile + public reviews.
    Returns {profile, reviews, note}.
    """
    api_key = get_steam_api_key()
    if not validate_api_key(api_key):
        raise ValueError("Steam API key is invalid. Check STEAM_API_KEY in your .env file.")

    lookup, kind = parse_profile_input(username)
    steamid = resolve_steamid(username, api_key)

    # Only use /id/… paths when that vanity URL actually exists for this account.
    vanity = None
    if kind == "vanity":
        resolved = _resolve_steamid_from_community(lookup)
        if resolved == steamid:
            vanity = lookup

    profile = get_profile(steamid, api_key)
    reviews, status = scrape_community_reviews(steamid, vanity)

    note = ""
    if status == "private":
        note = (
            "Reviews are hidden — set your Steam profile to Public "
            "(Profile + Game Details) so reviews can be analyzed."
        )
    elif not reviews:
        note = (
            "No public reviews found. This user may not have written reviews, "
            "or the custom URL / SteamID may be incorrect."
        )

    return {"profile": profile, "reviews": reviews, "note": note}
