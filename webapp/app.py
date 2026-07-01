"""Flask web app — Dashboard, reel hosting, portfolio site, and API.

Run: python -m webapp.app
Visit: http://localhost:5000
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, send_from_directory, url_for

from pipeline.database import (
    init_db, get_campaign_stats, get_stores_for_campaign,
    get_reel_analytics, record_reel_view, create_campaign, get_db,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-change-in-prod")

REEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples", "sample_output")


@app.before_request
def ensure_db():
    init_db()


# ─── Portfolio Landing Page ───────────────────────────────────────────────

@app.route("/")
def portfolio():
    return render_template("portfolio.html")


# ─── Dashboard ────────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    campaigns = get_campaign_stats()
    analytics = get_reel_analytics()
    return render_template("dashboard.html", campaigns=campaigns, analytics=analytics)


@app.route("/dashboard/campaign/<int:campaign_id>")
def campaign_detail(campaign_id: int):
    stores = get_stores_for_campaign(campaign_id)
    return render_template("campaign_detail.html", stores=stores, campaign_id=campaign_id)


# ─── Reel Hosting & QR Landing ────────────────────────────────────────────

@app.route("/reel/<watch_token>")
def watch_reel(watch_token: str):
    """QR code lands here. Tracks the view and shows the reel."""
    ip = request.remote_addr or ""
    ua = request.headers.get("User-Agent", "")
    reel = record_reel_view(watch_token, ip, ua)

    if not reel:
        return render_template("reel_not_found.html"), 404

    with get_db() as db:
        reel_data = db.execute("SELECT * FROM reels WHERE watch_token = ?", (watch_token,)).fetchone()
        store_data = db.execute("SELECT * FROM stores WHERE id = ?", (reel_data["store_id"],)).fetchone()

    return render_template(
        "watch_reel.html",
        reel=dict(reel_data),
        store=dict(store_data),
        watch_token=watch_token,
    )


@app.route("/reel-video/<watch_token>")
def serve_reel_video(watch_token: str):
    """Serve the actual video file."""
    with get_db() as db:
        reel = db.execute("SELECT video_path FROM reels WHERE watch_token = ?", (watch_token,)).fetchone()
    if not reel or not reel["video_path"]:
        return "Not found", 404
    directory = os.path.dirname(reel["video_path"])
    filename = os.path.basename(reel["video_path"])
    return send_from_directory(directory, filename)


# ─── API Endpoints ────────────────────────────────────────────────────────

@app.route("/api/campaigns", methods=["GET"])
def api_campaigns():
    return jsonify(get_campaign_stats())


@app.route("/api/campaigns", methods=["POST"])
def api_create_campaign():
    data = request.json or {}
    city = data.get("city", "")
    radius = data.get("radius", 5000)
    if not city:
        return jsonify({"error": "city is required"}), 400
    campaign_id = create_campaign(city, radius)
    thread = threading.Thread(
        target=_run_campaign_async,
        args=(campaign_id, city, radius, data.get("limit", 10)),
        daemon=True,
    )
    thread.start()
    return jsonify({"campaign_id": campaign_id, "status": "started"})


@app.route("/api/analytics", methods=["GET"])
def api_analytics():
    return jsonify(get_reel_analytics())


@app.route("/api/stores/<int:campaign_id>", methods=["GET"])
def api_stores(campaign_id: int):
    return jsonify(get_stores_for_campaign(campaign_id))


# ─── CRM Webhook ──────────────────────────────────────────────────────────

@app.route("/api/webhook/reel-viewed", methods=["POST"])
def webhook_reel_viewed():
    """Webhook endpoint for CRM integration.

    When a store owner scans the QR and views their reel, this fires.
    Connect this to HubSpot, Salesforce, Pipedrive, or any CRM via Zapier/Make.

    Zapier setup:
    1. Create a Zap: Webhook trigger → CRM action
    2. Set this URL as the webhook
    3. Map fields: store_name, owner_name, phone, reel_url
    """
    data = request.json or {}
    return jsonify({"received": True, "data": data})


# ─── Static files ─────────────────────────────────────────────────────────

@app.route("/static/reels/<path:filename>")
def serve_static_reel(filename: str):
    return send_from_directory(REEL_DIR, filename)


@app.route("/samples/<path:filename>")
def serve_sample_file(filename: str):
    """Serve any file from the sample_output directory (used by portfolio page)."""
    return send_from_directory(REEL_DIR, filename)


def _run_campaign_async(campaign_id: int, city: str, radius: int, limit: int):
    """Run the pipeline in a background thread (triggered from dashboard)."""
    try:
        from pipeline.run import run_pipeline
        run_pipeline(city=city, radius=radius, limit=limit)
    except Exception as e:
        from pipeline.database import update_campaign
        update_campaign(campaign_id, status="failed")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
