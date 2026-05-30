"""
Steam Player Credibility — Flask Application
Run:  python app.py
Then open http://127.0.0.1:5000
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask, render_template, request, redirect, url_for, jsonify
from scraper import scrape_reviews, resolve_steamid, get_steam_api_key
from analyzer import analyze
import logging
import re

app = Flask(__name__)
app.secret_key = "steam-player-credibility-2024"
app.config["TEMPLATES_AUTO_RELOAD"] = True

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _public_error(exc: ValueError) -> str:
    """Hide API-key / .env setup details from the UI."""
    msg = str(exc).lower()
    if "steam_api_key" in msg or "api key" in msg:
        log.error("Steam API configuration error: %s", exc)
        return "Unable to reach Steam right now. Please try again in a moment."
    return str(exc)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    username = request.form.get("username", "").strip()

    if not username:
        return render_template("index.html", error="Please enter a Steam username.")

    try:
        steamid = resolve_steamid(username, get_steam_api_key())
    except ValueError as e:
        return render_template("index.html", error=_public_error(e))

    return redirect(url_for("dashboard", steamid=steamid))


@app.route("/dashboard/<steamid>")
def dashboard(steamid: str):
    if not re.fullmatch(r"\d{17}", steamid):
        return render_template("index.html", error="Invalid profile link.")

    try:
        data = scrape_reviews(steamid)
        analytics = analyze(data)
        note = data.get("note", "")
        return render_template(
            "dashboard.html",
            profile=data["profile"],
            analytics=analytics,
            note=note,
        )
    except ValueError as e:
        return render_template("index.html", error=_public_error(e))
    except Exception:
        log.exception(f"Unexpected error for steamid {steamid}")
        return render_template(
            "index.html",
            error=(
                "Something went wrong. Check that the username is correct "
                "and the profile is Public (Profile + Game Details)."
            ),
        )


@app.route("/api/reviews/<steamid>")
def api_reviews(steamid: str):
    if not re.fullmatch(r"\d{17}", steamid):
        return jsonify({"status": "error", "message": "Invalid SteamID64"}), 400
    try:
        data = scrape_reviews(steamid)
        return jsonify({"status": "ok", **data})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception:
        log.exception(f"API error for steamid {steamid}")
        return jsonify({"status": "error", "message": "Failed to fetch reviews"}), 500


if __name__ == "__main__":
    print("Steam Player Credibility running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
