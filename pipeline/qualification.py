"""Step 2: Score and filter stores — keep the ones most likely to convert."""

from __future__ import annotations

import logging
from pipeline.config import MIN_STORE_RATING, MIN_STORE_REVIEWS, MIN_PHOTO_COUNT
from pipeline.models import Store, StoreStatus

logger = logging.getLogger(__name__)


def score_store(store: Store) -> float:
    """Score a store 0-100 on likelihood to become a paying client.

    Signals that matter:
    - Has a real website (they care about presence)
    - Enough reviews (real traffic)
    - Good rating (quality inventory)
    - Multiple photos (they invest in visuals)
    - Has phone number (reachable)
    - No existing video presence on website (they need us)
    """
    score = 0.0

    if store.website:
        score += 25
    if store.rating >= 4.0:
        score += 20
    elif store.rating >= MIN_STORE_RATING:
        score += 10
    if store.review_count >= 50:
        score += 20
    elif store.review_count >= MIN_STORE_REVIEWS:
        score += 10
    if len(store.photo_refs) >= 10:
        score += 20
    elif len(store.photo_refs) >= MIN_PHOTO_COUNT:
        score += 10
    if store.phone:
        score += 15

    return score


def qualify_stores(stores: list[Store], min_score: float = 50.0) -> list[Store]:
    """Score all stores and return only qualified ones, sorted by score."""
    # OSM stores never have ratings/reviews — lower threshold if no store has ratings
    has_ratings = any(s.rating > 0 for s in stores)
    effective_min = min_score if has_ratings else 15.0

    qualified = []
    for store in stores:
        store.score = score_store(store)
        if store.score >= effective_min:
            store.status = StoreStatus.QUALIFIED
            qualified.append(store)
            logger.info("QUALIFIED: %s (score=%.0f)", store.name, store.score)
        else:
            store.status = StoreStatus.DISQUALIFIED
            logger.debug("Disqualified: %s (score=%.0f)", store.name, store.score)

    qualified.sort(key=lambda s: s.score, reverse=True)
    logger.info("Qualified %d / %d stores", len(qualified), len(stores))
    return qualified
