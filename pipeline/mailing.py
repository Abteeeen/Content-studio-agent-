"""Step 7: Mail the postcard to the store owner.

Supports two free-trial mailing services:
- Lob (lob.com) — 300 free test postcards, US + international
- Stannp (stannp.com) — free trial credits, UK + US + EU

Both accept front/back images and a mailing address, and return tracking IDs.
"""

from __future__ import annotations

import json
import logging
import os

import requests

from pipeline.config import LOB_API_KEY, STANNP_API_KEY
from pipeline.models import PostcardOutput, Store, StoreStatus

logger = logging.getLogger(__name__)

LOB_POSTCARDS_URL = "https://api.lob.com/v1/postcards"
STANNP_POSTCARDS_URL = "https://dash.stannp.com/api/v1/letters/post"


def mail_postcard(
    store: Store,
    postcard: PostcardOutput,
    service: str = "lob",
) -> str:
    """Mail a physical postcard and return the tracking ID."""
    if service == "lob":
        return _mail_via_lob(store, postcard)
    elif service == "stannp":
        return _mail_via_stannp(store, postcard)
    else:
        raise ValueError(f"Unknown mailing service: {service}")


def _mail_via_lob(store: Store, postcard: PostcardOutput) -> str:
    """Send via Lob API. Free trial gives 300 test postcards.

    Sign up: lob.com → use test API key (starts with test_)
    Test mode prints are free and show up in the dashboard.
    """
    if not LOB_API_KEY:
        logger.warning("LOB_API_KEY not set — skipping mail for %s", store.name)
        return "SKIPPED_NO_KEY"

    address_parts = _parse_address(store.address)

    payload = {
        "description": f"Outreach postcard for {store.name}",
        "to": {
            "name": store.owner_name or store.name,
            "address_line1": address_parts.get("line1", store.address),
            "address_city": address_parts.get("city", ""),
            "address_state": address_parts.get("state", ""),
            "address_zip": address_parts.get("zip", ""),
            "address_country": "US",
        },
        "from": {
            "name": "Your Agency Name",
            "address_line1": "123 Agency Street",
            "address_city": "Los Angeles",
            "address_state": "CA",
            "address_zip": "90001",
            "address_country": "US",
        },
        "front": f"@{postcard.front_path}",
        "back": f"@{postcard.back_path}",
        "size": "6x4",
    }

    city = address_parts.get("city", "")
    state = address_parts.get("state", "")
    zipcode = address_parts.get("zip", "")

    if not city or not state or not zipcode:
        logger.warning("Incomplete address for %s: '%s' — skipping mail", store.name, store.address)
        return "SKIPPED_BAD_ADDRESS"

    with open(postcard.front_path, "rb") as front_f, open(postcard.back_path, "rb") as back_f:
        resp = requests.post(
            LOB_POSTCARDS_URL,
            auth=(LOB_API_KEY, ""),
            files={
                "front": ("front.png", front_f, "image/png"),
                "back": ("back.png", back_f, "image/png"),
            },
            data={
                "description": payload["description"],
                "to[name]": payload["to"]["name"],
                "to[address_line1]": payload["to"]["address_line1"],
                "to[address_city]": city,
                "to[address_state]": state,
                "to[address_zip]": zipcode,
                "to[address_country]": "US",
                "from[name]": os.getenv("AGENCY_NAME", "Your Agency Name"),
                "from[address_line1]": "123 Agency Street",
                "from[address_city]": "Los Angeles",
                "from[address_state]": "CA",
                "from[address_zip]": "90001",
                "from[address_country]": "US",
                "size": "6x4",
            },
            timeout=30,
        )
    resp.raise_for_status()
    result = resp.json()

    tracking_id = result.get("id", "")
    store.status = StoreStatus.MAILED
    logger.info("Mailed postcard to %s via Lob: %s", store.name, tracking_id)
    return tracking_id


def _mail_via_stannp(store: Store, postcard: PostcardOutput) -> str:
    """Send via Stannp API. Free trial credits available.

    Sign up: stannp.com → get API key from dashboard.
    """
    if not STANNP_API_KEY:
        logger.warning("STANNP_API_KEY not set — skipping mail for %s", store.name)
        return "SKIPPED_NO_KEY"

    address_parts = _parse_address(store.address)

    resp = requests.post(
        STANNP_POSTCARDS_URL,
        auth=(STANNP_API_KEY, ""),
        files={
            "file": ("postcard.png", open(postcard.front_path, "rb"), "image/png"),
            "file2": ("back.png", open(postcard.back_path, "rb"), "image/png"),
        },
        data={
            "test": "true",
            "recipient[title]": "",
            "recipient[firstname]": store.owner_name or store.name,
            "recipient[address1]": address_parts.get("line1", store.address),
            "recipient[city]": address_parts.get("city", ""),
            "recipient[state]": address_parts.get("state", ""),
            "recipient[zipcode]": address_parts.get("zip", ""),
            "recipient[country]": "US",
        },
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()

    tracking_id = str(result.get("data", {}).get("id", ""))
    store.status = StoreStatus.MAILED
    logger.info("Mailed postcard to %s via Stannp: %s", store.name, tracking_id)
    return tracking_id


def _parse_address(address: str) -> dict[str, str]:
    """Best-effort parse of a Google Maps formatted address into components."""
    parts = [p.strip() for p in address.split(",")]
    result: dict[str, str] = {"line1": parts[0] if parts else address}

    if len(parts) >= 3:
        result["city"] = parts[-3] if len(parts) >= 3 else ""
        state_zip = parts[-2] if len(parts) >= 2 else ""
        state_zip_parts = state_zip.strip().split()
        if state_zip_parts:
            result["state"] = state_zip_parts[0]
        if len(state_zip_parts) >= 2:
            result["zip"] = state_zip_parts[-1]
    elif len(parts) == 2:
        result["city"] = parts[0]
        state_zip_parts = parts[1].strip().split()
        if state_zip_parts:
            result["state"] = state_zip_parts[0]
        if len(state_zip_parts) >= 2:
            result["zip"] = state_zip_parts[-1]

    return result
