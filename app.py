"""
Steam Player Credibility — Flask Application
Run:  .venv\Scripts\python app.py  (or activate .venv first, then python app.py)
Then open http://127.0.0.1:5000
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask, render_template, request, redirect, url_for, jsonify
from scraper import scrape_reviews, resolve_steamid, get_steam_api_key
from analyzer import analyze
from llm_analysis import generate_credibility_analysis
import logging
import os
import re
import threading
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "steam-player-credibility-dev-key")
app.config["TEMPLATES_AUTO_RELOAD"] = True

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_search_jobs: dict[str, dict] = {}
_dashboard_cache: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _public_error(exc: ValueError) -> str:
    """Hide API-key / .env setup details from the UI."""
    msg = str(exc).lower()
    if "steam_api_key" in msg or ("api key" in msg and "openrouter" not in msg):
        log.error("Steam API configuration error: %s", exc)
        return "Unable to reach Steam right now. Please try again in a moment."
    if "openrouter" in msg:
        log.error("OpenRouter configuration error: %s", exc)
        return "AI analysis is unavailable. Check your OpenRouter API key in .env."
    return str(exc)


def _build_dashboard_context(data: dict) -> dict:
    analytics = analyze(data)
    note = data.get("note", "")

    ai_analysis = ""
    ai_analysis_error = ""
    try:
        ai_analysis = generate_credibility_analysis(data["profile"], analytics)
    except ValueError as e:
        ai_analysis_error = _public_error(e)
    except Exception:
        log.exception("AI analysis failed for %s", data["profile"].get("display_name"))
        ai_analysis_error = "Unable to generate AI analysis right now. Please try again later."

    return {
        "profile": data["profile"],
        "analytics": analytics,
        "note": note,
        "ai_analysis": ai_analysis,
        "ai_analysis_error": ai_analysis_error,
    }


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _search_jobs:
            _search_jobs[job_id].update(fields)


def _run_search_job(job_id: str, username: str) -> None:
    def on_progress(progress: int, label: str) -> None:
        _update_job(job_id, progress=progress, label=label)

    try:
        data = scrape_reviews(username, on_progress=on_progress)
        steamid = data["steamid"]

        on_progress(68, "Analyzing review credibility...")
        analytics = analyze(data)

        on_progress(82, "Generating AI summary...")
        ai_analysis = ""
        ai_analysis_error = ""
        try:
            ai_analysis = generate_credibility_analysis(data["profile"], analytics)
        except ValueError as e:
            ai_analysis_error = _public_error(e)
        except Exception:
            log.exception("AI analysis failed during search job")
            ai_analysis_error = "Unable to generate AI analysis right now. Please try again later."

        context = {
            "profile": data["profile"],
            "analytics": analytics,
            "note": data.get("note", ""),
            "ai_analysis": ai_analysis,
            "ai_analysis_error": ai_analysis_error,
        }

        with _jobs_lock:
            _dashboard_cache[steamid] = context

        _update_job(
            job_id,
            progress=100,
            label="Complete — opening dashboard...",
            done=True,
            steamid=steamid,
        )
    except ValueError as e:
        _update_job(
            job_id,
            progress=100,
            label="Search failed",
            done=True,
            error=_public_error(e),
        )
    except Exception:
        log.exception("Search job failed for username %s", username)
        _update_job(
            job_id,
            progress=100,
            label="Search failed",
            done=True,
            error=(
                "Something went wrong. Check that the username is correct "
                "and the profile is Public (Profile + Game Details)."
            ),
        )


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


@app.route("/api/search/start", methods=["POST"])
def search_start():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()

    if not username:
        return jsonify({"status": "error", "message": "Please enter a Steam username."}), 400

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _search_jobs[job_id] = {
            "progress": 0,
            "label": "Starting search...",
            "done": False,
            "error": "",
            "steamid": "",
        }

    thread = threading.Thread(
        target=_run_search_job,
        args=(job_id, username),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "ok", "job_id": job_id})


@app.route("/api/search/progress/<job_id>")
def search_progress(job_id: str):
    with _jobs_lock:
        job = _search_jobs.get(job_id)

    if not job:
        return jsonify({"status": "error", "message": "Search session not found."}), 404

    return jsonify({"status": "ok", **job})


@app.route("/dashboard/<steamid>")
def dashboard(steamid: str):
    if not re.fullmatch(r"\d{17}", steamid):
        return render_template("index.html", error="Invalid profile link.")

    cached = _dashboard_cache.pop(steamid, None)
    if cached:
        return render_template("dashboard.html", **cached)

    try:
        data = scrape_reviews(steamid)
        context = _build_dashboard_context(data)
        return render_template("dashboard.html", **context)
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
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Steam Player Credibility running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
