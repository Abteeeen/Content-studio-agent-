"""Step 3: Extract clothing images from store website and Google listing."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from pipeline.config import GOOGLE_MAPS_API_KEY, OUTPUT_DIR
from pipeline.models import Garment, Store, StoreStatus

logger = logging.getLogger(__name__)

PHOTO_URL = "https://maps.googleapis.com/maps/api/place/photo"
CLOTHING_KEYWORDS = re.compile(
    r"(dress|shirt|jacket|coat|pants|skirt|blouse|top|sweater|hoodie|"
    r"jeans|suit|gown|wear|fashion|collection|outfit|apparel|cloth)",
    re.IGNORECASE,
)


def extract_from_website(store: Store, max_images: int = 20) -> list[Garment]:
    """Scrape product images from the store's website."""
    if not store.website:
        return []

    garments = []
    try:
        resp = requests.get(store.website, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        shop_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.get_text().lower()
            if any(kw in href or kw in text for kw in ["shop", "collection", "product", "catalog", "new-arrival"]):
                shop_links.append(urljoin(store.website, a["href"]))

        pages_to_scrape = [store.website] + shop_links[:3]

        seen_urls: set[str] = set()
        for page_url in pages_to_scrape:
            try:
                page_resp = requests.get(page_url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"
                })
                page_soup = BeautifulSoup(page_resp.text, "html.parser")

                for img in page_soup.find_all("img", src=True):
                    src = urljoin(page_url, img["src"])
                    if src in seen_urls:
                        continue
                    seen_urls.add(src)

                    alt = img.get("alt", "")
                    parent_text = img.parent.get_text(" ", strip=True)[:200] if img.parent else ""
                    context = f"{alt} {parent_text} {src}"

                    if _is_likely_product_image(src, context):
                        garments.append(Garment(
                            image_url=src,
                            source="website",
                            description=alt or parent_text[:100],
                        ))
                        if len(garments) >= max_images:
                            break
            except Exception:
                continue

    except Exception as e:
        logger.warning("Failed to scrape %s: %s", store.website, e)

    logger.info("Extracted %d images from website: %s", len(garments), store.website)
    return garments


def extract_from_google_photos(store: Store, max_photos: int = 10) -> list[Garment]:
    """Download clothing images from the store's Google listing photos."""
    garments = []
    for ref in store.photo_refs[:max_photos]:
        photo_url = f"{PHOTO_URL}?maxwidth=1200&photo_reference={ref}&key={GOOGLE_MAPS_API_KEY}"
        garments.append(Garment(
            image_url=photo_url,
            source="google_photos",
            description=f"Google listing photo for {store.name}",
        ))

    logger.info("Extracted %d Google listing photos for: %s", len(garments), store.name)
    return garments


def download_image(garment: Garment, store_dir: str) -> str:
    """Download a garment image to local disk."""
    os.makedirs(store_dir, exist_ok=True)
    filename = _safe_filename(garment.image_url)
    filepath = os.path.join(store_dir, filename)

    if os.path.exists(filepath):
        garment.image_path = filepath
        return filepath

    resp = requests.get(garment.image_url, timeout=15, stream=True)
    resp.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)

    garment.image_path = filepath
    return filepath


def extract_all(store: Store) -> list[Garment]:
    """Run both extraction methods and merge results."""
    garments = extract_from_website(store)
    garments.extend(extract_from_google_photos(store))

    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name), "garments")
    for g in garments:
        try:
            download_image(g, store_dir)
        except Exception as e:
            logger.warning("Failed to download %s: %s", g.image_url, e)

    if garments:
        store.status = StoreStatus.CLOTHES_EXTRACTED
    return garments


def _is_likely_product_image(url: str, context: str) -> bool:
    """Heuristic: is this URL likely a product/clothing image?"""
    parsed = urlparse(url)
    path = parsed.path.lower()

    skip_patterns = ["logo", "icon", "banner", "bg-", "background", "avatar", "payment", "social"]
    if any(p in path for p in skip_patterns):
        return False

    if not any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        return False

    if CLOTHING_KEYWORDS.search(context):
        return True

    if any(kw in path for kw in ["product", "collection", "item", "catalog"]):
        return True

    return False


def _safe_filename(url: str) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or "image.jpg"
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:100]


def _slugify(text: str) -> str:
    return re.sub(r"[^\w]", "_", text.lower()).strip("_")[:50]
