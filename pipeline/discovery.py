"""Step 1: Discover clothing stores.

Three backends — pick whichever you have access to:

  --source yelp       Yelp Fusion API  (FREE 500/day, NO credit card needed)
  --source osm        OpenStreetMap    (100% FREE, no signup at all)
  --source google     Google Places    (FREE $200/mo credit, needs payment verification)

Recommended: start with 'osm' (zero signup), upgrade to 'yelp' for richer data.
"""

from __future__ import annotations

import logging
import time

import requests

from pipeline.config import GOOGLE_MAPS_API_KEY, YELP_API_KEY, PLACES_SEARCH_RADIUS
from pipeline.models import Store

logger = logging.getLogger(__name__)


# ─── Public entry points ──────────────────────────────────────────────────────

def search_clothing_stores(
    lat: float,
    lng: float,
    radius: int = PLACES_SEARCH_RADIUS,
    source: str = "yelp",
) -> list[Store]:
    """Find clothing stores near a location.

    source: 'yelp' | 'osm' | 'google'
    """
    if source == "yelp":
        return _search_yelp(lat, lng, radius)
    elif source == "osm":
        return _search_osm(lat, lng, radius)
    elif source == "google":
        return _search_google(lat, lng, radius)
    else:
        raise ValueError(f"Unknown source: {source}. Use 'yelp', 'osm', or 'google'.")


def enrich_store(store: Store) -> Store:
    """No-op for non-Google sources; Google enrichment fetches full details."""
    if store.place_id.startswith("google_") and GOOGLE_MAPS_API_KEY:
        return _enrich_google(store)
    return store


def geocode_city(city: str) -> tuple[float, float]:
    """Convert city name to lat/lng — uses Nominatim (OpenStreetMap), 100% free."""
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city, "format": "json", "limit": 1},
        headers={"User-Agent": "OutreachAutopilot/1.0 contact@youragency.com"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode city: {city}")
    return float(results[0]["lat"]), float(results[0]["lon"])


# ─── Yelp Fusion (FREE 500/day, no credit card) ───────────────────────────────

YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"


def _search_yelp(lat: float, lng: float, radius: int) -> list[Store]:
    """Search via Yelp Fusion API.

    Sign up free at: https://docs.developer.yelp.com/
    No credit card required. 500 API calls/day free.
    Returns: name, address, phone, website, rating, review_count.
    """
    if not YELP_API_KEY:
        logger.warning("YELP_API_KEY not set. Sign up free at docs.developer.yelp.com")
        return []

    stores: list[Store] = []
    offset = 0
    limit = 50  # max per request

    while True:
        resp = requests.get(
            YELP_SEARCH_URL,
            headers={"Authorization": f"Bearer {YELP_API_KEY}"},
            params={
                "latitude": lat,
                "longitude": lng,
                "radius": min(radius, 40000),  # Yelp max is 40km
                "categories": "womenscloth,menscloth,childrencloth,fashion,vintage,deptstores",
                "limit": limit,
                "offset": offset,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        businesses = data.get("businesses", [])
        if not businesses:
            break

        for biz in businesses:
            location = biz.get("location", {})
            address_parts = [
                location.get("address1", ""),
                location.get("city", ""),
                location.get("state", ""),
                location.get("zip_code", ""),
            ]
            address = ", ".join(p for p in address_parts if p)

            coords = biz.get("coordinates", {})
            stores.append(Store(
                place_id=f"yelp_{biz['id']}",
                name=biz.get("name", ""),
                address=address,
                phone=biz.get("display_phone", ""),
                website=biz.get("url", ""),
                rating=float(biz.get("rating", 0)),
                review_count=int(biz.get("review_count", 0)),
                lat=float(coords.get("latitude", lat)),
                lng=float(coords.get("longitude", lng)),
            ))

        total = data.get("total", 0)
        offset += limit
        if offset >= min(total, 200):  # Yelp caps at 1000, we cap at 200
            break

        time.sleep(0.2)  # be polite

    logger.info("Yelp: discovered %d clothing stores near (%.4f, %.4f)", len(stores), lat, lng)
    return stores


# ─── OpenStreetMap / Overpass (100% FREE, no signup) ─────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _search_osm(lat: float, lng: float, radius: int) -> list[Store]:
    """Search via OpenStreetMap Overpass API — zero cost, zero signup.

    Finds all nodes/ways tagged shop=clothes or shop=fashion within the radius.
    Data quality varies by city — works best in US, UK, EU major cities.
    """
    query = f"""
    [out:json][timeout:25];
    (
      node["shop"~"clothes|fashion|boutique|vintage"](around:{radius},{lat},{lng});
      way["shop"~"clothes|fashion|boutique|vintage"](around:{radius},{lat},{lng});
    );
    out center tags;
    """

    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "OutreachAutopilot/1.0"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    stores: list[Store] = []
    for i, element in enumerate(data.get("elements", [])):
        tags = element.get("tags", {})

        name = tags.get("name", "")
        if not name:
            continue

        # Get coordinates (nodes have lat/lon directly, ways have a center)
        if element["type"] == "node":
            elat, elng = element.get("lat", lat), element.get("lon", lng)
        else:
            center = element.get("center", {})
            elat, elng = center.get("lat", lat), center.get("lon", lng)

        address_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", ""),
            tags.get("addr:state", ""),
            tags.get("addr:postcode", ""),
        ]
        address = " ".join(p for p in address_parts if p).strip() or f"near ({elat:.4f}, {elng:.4f})"

        stores.append(Store(
            place_id=f"osm_{element['type']}_{element['id']}",
            name=name,
            address=address,
            phone=tags.get("phone", tags.get("contact:phone", "")),
            website=tags.get("website", tags.get("contact:website", "")),
            rating=0.0,  # OSM doesn't have ratings
            review_count=0,
        ))

    logger.info("OSM: discovered %d clothing stores near (%.4f, %.4f)", len(stores), lat, lng)
    return stores


# ─── Google Places (needs payment verification but most data-rich) ────────────

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def _search_google(lat: float, lng: float, radius: int) -> list[Store]:
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("GOOGLE_MAPS_API_KEY not set.")
        return []

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
                place_id=f"google_{place['place_id']}",
                name=place.get("name", ""),
                address=place.get("vicinity", ""),
                rating=float(place.get("rating", 0.0)),
                review_count=int(place.get("user_ratings_total", 0)),
                lat=place["geometry"]["location"]["lat"],
                lng=place["geometry"]["location"]["lng"],
                photo_refs=[p["photo_reference"] for p in place.get("photos", [])],
            )
            stores.append(store)

        next_token = data.get("next_page_token")
        if not next_token:
            break
        time.sleep(2)
        params = {"pagetoken": next_token, "key": GOOGLE_MAPS_API_KEY}

    logger.info("Google: discovered %d clothing stores near (%.4f, %.4f)", len(stores), lat, lng)
    return stores


def _enrich_google(store: Store) -> Store:
    real_id = store.place_id.replace("google_", "")
    params = {
        "place_id": real_id,
        "fields": "name,formatted_address,formatted_phone_number,website,photos",
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
