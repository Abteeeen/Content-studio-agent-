"""Main orchestrator — runs the full outreach pipeline end-to-end.

Usage:
    python -m pipeline.run --city "Los Angeles" --radius 5000 --limit 10
    python -m pipeline.run --city "New York" --dry-run
    python -m pipeline.run --demo  # Run with sample data (no API keys needed)
"""

from __future__ import annotations

import argparse
import logging
import sys

from pipeline.discovery import geocode_city, search_clothing_stores, enrich_store
from pipeline.qualification import qualify_stores
from pipeline.extraction import extract_all
from pipeline.selection import select_best_garment
from pipeline.rendering import render_reel
from pipeline.postcard import generate_postcard
from pipeline.mailing import mail_postcard
from pipeline.models import OutreachResult, StoreStatus
from pipeline.utils import setup_logging, save_result, print_summary

logger = logging.getLogger(__name__)


def run_pipeline(
    city: str,
    radius: int = 5000,
    limit: int = 10,
    dry_run: bool = False,
    render_method: str = "replicate",
    mail_service: str = "lob",
    source: str = "yelp",
) -> list[OutreachResult]:
    """Execute the full pipeline: discover → qualify → extract → select → render → postcard → mail."""
    results: list[OutreachResult] = []

    # Step 1: Discover
    logger.info("Step 1/7: Discovering clothing stores in %s via %s...", city, source)
    lat, lng = geocode_city(city)
    stores = search_clothing_stores(lat, lng, radius, source=source)
    logger.info("Found %d stores", len(stores))

    # Step 2: Qualify
    logger.info("Step 2/7: Qualifying stores...")
    qualified = qualify_stores(stores)
    qualified = qualified[:limit]
    logger.info("Processing top %d qualified stores", len(qualified))

    for i, store in enumerate(qualified):
        result = OutreachResult(store=store)
        logger.info("\n--- Store %d/%d: %s ---", i + 1, len(qualified), store.name)

        try:
            # Enrich with full details
            enrich_store(store)

            # Step 3: Extract clothing images
            logger.info("Step 3/7: Extracting clothing images...")
            result.garments = extract_all(store)
            if not result.garments:
                result.error = "No clothing images found"
                results.append(result)
                continue

            # Step 4: Select best garment
            logger.info("Step 4/7: Selecting best garment...")
            result.selected_garment = select_best_garment(store, result.garments)
            if not result.selected_garment:
                result.error = "Could not select a garment"
                results.append(result)
                continue

            if dry_run:
                logger.info("DRY RUN — skipping render and mail for %s", store.name)
                results.append(result)
                continue

            # Step 5: Render cinematic reel
            logger.info("Step 5/7: Rendering cinematic reel...")
            result.reel = render_reel(store, result.selected_garment, method=render_method)

            # Step 6: Generate postcard
            logger.info("Step 6/7: Generating postcard...")
            reel_url = result.reel.video_url or f"https://youragency.com/reel/{store.place_id}"
            result.postcard = generate_postcard(store, result.reel, reel_url)

            # Step 7: Mail it
            logger.info("Step 7/7: Mailing postcard...")
            try:
                result.mail_tracking_id = mail_postcard(store, result.postcard, service=mail_service)
            except Exception as mail_err:
                logger.error("Mailing failed for %s (postcard still saved): %s", store.name, mail_err)
                result.mail_tracking_id = "MAIL_FAILED"

        except Exception as e:
            logger.error("Failed processing %s: %s", store.name, e, exc_info=True)
            result.error = str(e)
            store.status = StoreStatus.FAILED

        save_result(result)
        results.append(result)

    return results


def run_demo() -> list[OutreachResult]:
    """Run a demo with sample data — no API keys needed.

    Creates sample postcard outputs to show the pipeline works.
    Perfect for portfolio demonstration.
    """
    from pipeline.models import Store, Garment, ReelOutput

    logger.info("Running DEMO mode with sample data...")

    sample_stores = [
        Store(
            place_id="demo_001",
            name="Bella Moda Boutique",
            address="123 Fashion Ave, Los Angeles, CA 90015",
            phone="(213) 555-0101",
            website="https://bellamodaboutique.com",
            rating=4.5,
            review_count=87,
            owner_name="Maria Santos",
            score=85,
            status=StoreStatus.QUALIFIED,
        ),
        Store(
            place_id="demo_002",
            name="Urban Thread Co",
            address="456 Style Street, Los Angeles, CA 90017",
            phone="(213) 555-0202",
            website="https://urbanthread.co",
            rating=4.2,
            review_count=134,
            owner_name="James Chen",
            score=80,
            status=StoreStatus.QUALIFIED,
        ),
        Store(
            place_id="demo_003",
            name="The Velvet Hanger",
            address="789 Rodeo Drive, Beverly Hills, CA 90210",
            phone="(310) 555-0303",
            website="https://thevelvethanger.com",
            rating=4.8,
            review_count=212,
            owner_name="Sofia Laurent",
            score=95,
            status=StoreStatus.QUALIFIED,
        ),
    ]

    results = []
    for store in sample_stores:
        result = OutreachResult(store=store)

        result.selected_garment = Garment(
            image_url="",
            image_path="",
            source="demo",
            description=f"Demo garment for {store.name}",
            category="dress",
            score=9.0,
        )

        result.reel = ReelOutput(
            video_url=f"https://youragency.com/reel/{store.place_id}",
            thumbnail_path="",
        )

        store.status = StoreStatus.REEL_RENDERED

        reel_url = f"https://youragency.com/reel/{store.place_id}"
        result.postcard = generate_postcard(store, result.reel, reel_url)

        save_result(result)
        results.append(result)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Clothing Store Outreach Autopilot")
    parser.add_argument("--city", default="Los Angeles", help="Target city")
    parser.add_argument("--radius", type=int, default=5000, help="Search radius in meters")
    parser.add_argument("--limit", type=int, default=10, help="Max stores to process")
    parser.add_argument("--dry-run", action="store_true", help="Discover and select only, skip render/mail")
    parser.add_argument("--demo", action="store_true", help="Run with sample data, no API keys needed")
    parser.add_argument("--source", default="yelp", choices=["yelp", "osm", "google"],
                        help="Store discovery source (yelp=free/recommended, osm=no-signup, google=needs payment)")
    parser.add_argument("--render-method", default="replicate",
                        choices=["replicate", "fal", "segmind", "free"],
                        help="Render method: replicate=paid, fal=free credit, segmind=works in India, free=HuggingFace")
    parser.add_argument("--mail-service", default="lob", choices=["lob", "stannp"])
    parser.add_argument("--log-level", default="INFO")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if args.demo:
        results = run_demo()
    else:
        results = run_pipeline(
            city=args.city,
            radius=args.radius,
            limit=args.limit,
            dry_run=args.dry_run,
            render_method=args.render_method,
            mail_service=args.mail_service,
            source=args.source,
        )

    print_summary(results)


if __name__ == "__main__":
    main()
