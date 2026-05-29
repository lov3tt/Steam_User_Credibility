"""
Steam Player Credibility — Flask Application
Run:  python app.py
Then open http://127.0.0.1:5000
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from scraper import scrape_reviews
from analyzer import analyze
import logging

app = Flask(__name__)
app.secret_key = "steam-player-credibility-2024"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    username = request.form.get("username", "").strip()
    api_key  = request.form.get("api_key", "").strip()

    if not username:
        return render_template("index.html", error="Please enter a Steam username.")
    if not api_key:
        return render_template("index.html", error="Please enter your Steam API key.")

    # Persist key in session so the user doesn't have to re-enter it
    session["api_key"] = api_key
    return redirect(url_for("dashboard", username=username))


@app.route("/dashboard/<username>")
def dashboard(username: str):
    api_key = session.get("api_key", "")
    if not api_key:
        return redirect(url_for("index"))

    try:
        data      = scrape_reviews(username, api_key)
        analytics = analyze(data)
        note      = data.get("note", "")
        return render_template(
            "dashboard.html",
            username=username,
            profile=data["profile"],
            analytics=analytics,
            note=note,
        )
    except ValueError as e:
        return render_template("index.html", error=str(e))
    except Exception as e:
        log.exception(f"Unexpected error for user {username}")
        return render_template(
            "index.html",
            error=(
                "Something went wrong. Check that the username is correct, "
                "the profile is Public, and the API key is valid."
            ),
        )


@app.route("/api/reviews/<username>")
def api_reviews(username: str):
    api_key = request.args.get("key", session.get("api_key", ""))
    if not api_key:
        return jsonify({"status": "error", "message": "API key required (?key=...)"}), 400
    try:
        data = scrape_reviews(username, api_key)
        return jsonify({"status": "ok", **data})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception:
        log.exception(f"API error for user {username}")
        return jsonify({"status": "error", "message": "Failed to fetch reviews"}), 500


if __name__ == "__main__":
    print("Steam Player Credibility running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)