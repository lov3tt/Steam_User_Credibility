"""
Steam Player Credibility — Analyzer
Scores a player's review history across multiple dimensions.
"""
from __future__ import annotations   # enables list[x] / tuple / X | Y on Python 3.8+
import statistics
from collections import Counter


# ── Thresholds ──────────────────────────────────────────────────────────────
MIN_REVIEWS_FOR_FULL_SCORE = 10
LOW_HOUR_THRESHOLD = 2.0      # reviews written with < 2 hrs are suspect
SPAM_WORD_THRESHOLD = 5       # reviews < 5 words are very low quality
HIGH_QUALITY_WORDS = 50       # reviews >= 50 words score well for depth


def analyze(data: dict) -> dict:
    """
    Takes the output of scraper.scrape_reviews() and returns a rich
    analytics dict ready to be passed to the Jinja template.
    """
    reviews = data.get("reviews", [])
    total = len(reviews)

    if total == 0:
        return _empty_analysis()

    # ── Basic counts ────────────────────────────────────────────────────────
    positive = [r for r in reviews if r["recommended"]]
    negative = [r for r in reviews if not r["recommended"]]
    pos_count = len(positive)
    neg_count = len(negative)

    # ── Word / length stats ─────────────────────────────────────────────────
    word_counts = [r["word_count"] for r in reviews]
    avg_words = round(statistics.mean(word_counts), 1) if word_counts else 0
    median_words = round(statistics.median(word_counts), 1) if word_counts else 0

    spam_reviews = sum(1 for w in word_counts if w < SPAM_WORD_THRESHOLD)
    quality_reviews = sum(1 for w in word_counts if w >= HIGH_QUALITY_WORDS)

    # ── Hours played stats ──────────────────────────────────────────────────
    hours_list = [r["hours"] for r in reviews]
    avg_hours = round(statistics.mean(hours_list), 1) if hours_list else 0
    low_hour_reviews = sum(1 for h in hours_list if h < LOW_HOUR_THRESHOLD)
    pct_low_hours = round(low_hour_reviews / total * 100, 1)

    # ── Helpful votes ────────────────────────────────────────────────────────
    total_helpful = sum(r["helpful"] for r in reviews)
    avg_helpful = round(total_helpful / total, 2) if total else 0

    # ── Game diversity ───────────────────────────────────────────────────────
    game_counts = Counter(r["game"] for r in reviews)
    unique_games = len(game_counts)
    most_reviewed_game, most_reviewed_count = game_counts.most_common(1)[0]
    pct_single_game = round(most_reviewed_count / total * 100, 1)

    # ── Top games for bar chart ──────────────────────────────────────────────
    top_games = [
        {"game": g, "count": c}
        for g, c in game_counts.most_common(10)
    ]

    # ── Reviews over time (by year/month tag) ─────────────────────────────
    date_counter: Counter = Counter()
    for r in reviews:
        raw = r.get("date", "")
        # Steam dates look like "13 Jan" or "13 Jan, 2022"
        import re
        year_match = re.search(r"\b(20\d{2})\b", raw)
        if year_match:
            date_counter[year_match.group(1)] += 1
        else:
            date_counter["Unknown"] += 1

    timeline = [{"label": k, "count": v} for k, v in sorted(date_counter.items())]

    # ── Credibility scoring ──────────────────────────────────────────────────
    score, breakdown = _credibility_score(
        total=total,
        avg_words=avg_words,
        pct_low_hours=pct_low_hours,
        spam_ratio=spam_reviews / total,
        pos_ratio=pos_count / total if total else 0.5,
        avg_helpful=avg_helpful,
        unique_games=unique_games,
        pct_single_game=pct_single_game,
    )

    verdict, verdict_color, verdict_icon = _verdict(score)

    # ── Per-review sentiment labels ──────────────────────────────────────────
    review_list = []
    for r in reviews:
        review_list.append({
            **r,
            "sentiment": "Recommended" if r["recommended"] else "Not Recommended",
            "quality_tag": _quality_tag(r["word_count"], r["hours"]),
        })

    return {
        "total": total,
        "pos_count": pos_count,
        "neg_count": neg_count,
        "pos_pct": round(pos_count / total * 100, 1) if total else 0,
        "neg_pct": round(neg_count / total * 100, 1) if total else 0,
        "avg_words": avg_words,
        "median_words": median_words,
        "spam_reviews": spam_reviews,
        "quality_reviews": quality_reviews,
        "avg_hours": avg_hours,
        "low_hour_reviews": low_hour_reviews,
        "pct_low_hours": pct_low_hours,
        "total_helpful": total_helpful,
        "avg_helpful": avg_helpful,
        "unique_games": unique_games,
        "most_reviewed_game": most_reviewed_game,
        "most_reviewed_count": most_reviewed_count,
        "pct_single_game": pct_single_game,
        "top_games": top_games,
        "timeline": timeline,
        "credibility_score": score,
        "credibility_breakdown": breakdown,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "verdict_icon": verdict_icon,
        "reviews": review_list,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _credibility_score(
    total, avg_words, pct_low_hours, spam_ratio,
    pos_ratio, avg_helpful, unique_games, pct_single_game
) -> tuple[int, list[dict]]:
    """
    Returns (score 0-100, breakdown list).
    Each dimension contributes up to its stated max points.
    """
    breakdown = []

    def add(label: str, earned: float, max_pts: float, note: str):
        breakdown.append({
            "label": label,
            "earned": round(earned, 1),
            "max": max_pts,
            "note": note,
            "pct": round(earned / max_pts * 100),
        })
        return earned

    total_score = 0

    # 1. Volume (max 15 pts)
    vol_pts = min(15, (total / MIN_REVIEWS_FOR_FULL_SCORE) * 15)
    total_score += add("Review Volume", vol_pts, 15,
                       f"{total} review(s) — more reviews = more reliable signal")

    # 2. Depth / word count (max 25 pts)
    depth_pts = min(25, (avg_words / HIGH_QUALITY_WORDS) * 25)
    total_score += add("Review Depth", depth_pts, 25,
                       f"Avg {avg_words} words per review")

    # 3. Low-hour penalty (max 20 pts)
    low_hr_pts = max(0, 20 - (pct_low_hours / 5))  # lose 4 pts per 20%
    total_score += add("Playtime Legitimacy", low_hr_pts, 20,
                       f"{pct_low_hours}% of reviews posted with < {LOW_HOUR_THRESHOLD} hrs played")

    # 4. Spam penalty (max 15 pts)
    spam_pts = max(0, 15 * (1 - spam_ratio * 2))
    total_score += add("No Spam Reviews", spam_pts, 15,
                       f"{round(spam_ratio*100,1)}% reviews under {SPAM_WORD_THRESHOLD} words")

    # 5. Bias check — extreme positive ratio is suspicious (max 10 pts)
    balance_pts = 10 * (1 - abs(pos_ratio - 0.7) / 0.7) if abs(pos_ratio - 0.7) < 0.7 else 0
    balance_pts = max(0, min(10, balance_pts))
    total_score += add("Review Balance", balance_pts, 10,
                       f"{round(pos_ratio*100,1)}% positive — balanced reviewers score higher")

    # 6. Community trust – helpful votes (max 10 pts)
    help_pts = min(10, avg_helpful * 2)
    total_score += add("Community Trust", help_pts, 10,
                       f"Avg {avg_helpful} helpful votes per review")

    # 7. Game diversity (max 5 pts)
    div_pts = min(5, (unique_games / 5) * 5)
    total_score += add("Game Diversity", div_pts, 5,
                       f"{unique_games} unique game(s) reviewed")

    return round(min(100, max(0, total_score))), breakdown


def _verdict(score: int) -> tuple[str, str, str]:
    if score >= 80:
        return "Highly Credible", "#4ade80", "✔"
    elif score >= 60:
        return "Generally Credible", "#a3e635", "✔"
    elif score >= 40:
        return "Mixed Credibility", "#facc15", "⚠"
    elif score >= 20:
        return "Low Credibility", "#fb923c", "⚠"
    else:
        return "Suspected Fake / Spam", "#f87171", "✖"


def _quality_tag(words: int, hours: float) -> str:
    if words < SPAM_WORD_THRESHOLD:
        return "Spam"
    if hours < LOW_HOUR_THRESHOLD:
        return "Low Hours"
    if words >= HIGH_QUALITY_WORDS and hours >= 10:
        return "High Quality"
    if words >= HIGH_QUALITY_WORDS:
        return "Detailed"
    return "Standard"


def _empty_analysis() -> dict:
    return {
        "total": 0, "pos_count": 0, "neg_count": 0,
        "pos_pct": 0, "neg_pct": 0,
        "avg_words": 0, "median_words": 0,
        "spam_reviews": 0, "quality_reviews": 0,
        "avg_hours": 0, "low_hour_reviews": 0, "pct_low_hours": 0,
        "total_helpful": 0, "avg_helpful": 0,
        "unique_games": 0, "most_reviewed_game": "N/A",
        "most_reviewed_count": 0, "pct_single_game": 0,
        "top_games": [], "timeline": [],
        "credibility_score": 0,
        "credibility_breakdown": [],
        "verdict": "No Reviews Found", "verdict_color": "#94a3b8",
        "verdict_icon": "—",
        "reviews": [],
    }
      