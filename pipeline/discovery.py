"""Step 1: Discover clothing stores via Google Maps Places API."""

from __future__ import annotations

import logging
import requests
from pipeline.config import GOOGLE_MAPS_API_KEY, PLACES_SEARCH_RADIUS
from pipeline.models import Store

logger = logging.getLogger(__name__)

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def search_clothing_stores(lat: float, lng: float, radius: int = PLACES_SEARCH_RADIUS) -> list[Store]:
    """Find clothing stores near a location using Google Places API.

    Uses the free $200/month Google Maps credit — roughly 10,000 nearby searches.
    """
    stores: list[Store] = []
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": "clothing_store",
        "key": GOOGLE_MAPS_API_KEY,
    }

    while True:
        resp = requests.get(PLACES_NEARBY_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for place in data.get("results", []):
            store = Store(
                place_id=place["place_id"],
                name=place.get("name", ""),
                address=place.get("vicinity", ""),
                rating=place.get("rating", 0.0),
                review_count=place.get("user_ratings_total", 0),
                lat=place["geometry"]["location"]["lat"],
                lng=place["geometry"]["location"]["lng"],
                photo_refs=[
                    p["photo_reference"] for p in place.get("photos", [])
                ],
            )
            stores.append(store)

        next_token = data.get("next_page_token")
        if not next_token:
            break
        params = {"pagetoken": next_token, "key": GOOGLE_MAPS_API_KEY}

    logger.info("Discovered %d clothing stores near (%.4f, %.4f)", len(stores), lat, lng)
    return stores


def enrich_store(store: Store) -> Store:
    """Fetch full details for a store: website, phone, owner name, all photos."""
    params = {
        "place_id": store.place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,photos,url,editorial_summary",
        "key": GOOGLE_MAPS_API_KEY,
    }
    resp = requests.get(PLACE_DETAILS_URL, params=params, timeout=10)
    resp.raise_for_status()
    result = resp.json().get("result", {})

    store.address = result.get("formatted_address", store.address)
    store.phone = result.get("formatted_phone_number", "")
    store.website = result.get("website", "")
    store.photo_refs = [p["photo_reference"] for p in result.get("photos", [])]

    return store


def geocode_city(city: str) -> tuple[float, float]:
    """Convert a city name to lat/lng coordinates."""
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": city, "key": GOOGLE_MAPS_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Could not geocode city: {city}")
    loc = results[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]
