"""Shared utilities for the pipeline."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from pipeline.config import OUTPUT_DIR
from pipeline.models import OutreachResult, StoreStatus

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def save_result(result: OutreachResult) -> str:
    """Save an outreach result to a JSON file for tracking."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"result_{_slugify(result.store.name)}_{_timestamp()}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    data = {
        "store": {
            "name": result.store.name,
            "address": result.store.address,
            "phone": result.store.phone,
            "website": result.store.website,
            "rating": result.store.rating,
            "review_count": result.store.review_count,
            "score": result.store.score,
            "status": result.store.status.value,
            "owner_name": result.store.owner_name,
        },
        "garments_found": len(result.garments),
        "selected_garment": {
            "category": result.selected_garment.category,
            "description": result.selected_garment.description,
            "score": result.selected_garment.score,
            "source": result.selected_garment.source,
        } if result.selected_garment else None,
        "reel": {
            "video_path": result.reel.video_path,
            "video_url": result.reel.video_url,
            "thumbnail_path": result.reel.thumbnail_path,
        } if result.reel else None,
        "postcard": {
            "front_path": result.postcard.front_path,
            "back_path": result.postcard.back_path,
            "reel_url": result.postcard.reel_url,
        } if result.postcard else None,
        "mail_tracking_id": result.mail_tracking_id,
        "error": result.error,
        "timestamp": _timestamp(),
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved result to %s", filepath)
    return filepath


def print_summary(results: list[OutreachResult]) -> None:
    """Print a summary of all outreach results."""
    total = len(results)
    mailed = sum(1 for r in results if r.store.status == StoreStatus.MAILED)
    rendered = sum(1 for r in results if r.store.status == StoreStatus.REEL_RENDERED)
    failed = sum(1 for r in results if r.error)

    print(f"\n{'=' * 60}")
    print(f"  OUTREACH PIPELINE SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total stores processed: {total}")
    print(f"  Reels rendered:         {rendered}")
    print(f"  Postcards mailed:       {mailed}")
    print(f"  Failed:                 {failed}")
    print(f"{'=' * 60}")

    for r in results:
        status_icon = {
            StoreStatus.MAILED: "[OK]",
            StoreStatus.REEL_RENDERED: "[REEL]",
            StoreStatus.POSTCARD_CREATED: "[CARD]",
            StoreStatus.FAILED: "[FAIL]",
        }.get(r.store.status, "[...]")

        print(f"  {status_icon} {r.store.name} (score={r.store.score:.0f})")
        if r.error:
            print(f"        Error: {r.error}")
    print()


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^\w]", "_", text.lower()).strip("_")[:50]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
