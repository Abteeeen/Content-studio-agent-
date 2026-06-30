"""Step 4: Use Claude Vision to pick the single best garment for the reel."""

from __future__ import annotations

import base64
import logging
import os

import anthropic

from pipeline.config import ANTHROPIC_API_KEY
from pipeline.models import Garment, Store, StoreStatus

logger = logging.getLogger(__name__)

SELECTION_PROMPT = """You are a fashion content strategist for a video production agency.

I'm showing you product images from a clothing store called "{store_name}".
Your job: pick the ONE garment that will make the most impressive cinematic reel.

Criteria (in order of importance):
1. Visual impact — bold colors, interesting textures, or striking silhouette
2. Reel-worthy — will look amazing on a model walking/posing in cinematic lighting
3. Universally appealing — not too niche, would impress a store owner
4. Clear product shot — the image is high quality enough to work with

For each image, give:
- category (dress, jacket, top, pants, etc.)
- score 1-10
- one-line reason

Then declare the WINNER by its number.

Respond in this exact format:
IMAGE 1: category=dress | score=8 | Stunning red evening dress, perfect for dramatic lighting
IMAGE 2: category=jacket | score=6 | Nice leather jacket but too dark for cinematic pop
...
WINNER: 1
"""


def select_best_garment(store: Store, garments: list[Garment]) -> Garment | None:
    """Use Claude Vision to analyze garment images and pick the best one."""
    if not garments:
        return None

    candidates = [g for g in garments if g.image_path and os.path.exists(g.image_path)]
    if not candidates:
        logger.warning("No downloaded images available for %s", store.name)
        return None

    candidates = candidates[:10]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    content = []
    for i, garment in enumerate(candidates):
        with open(garment.image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        ext = os.path.splitext(garment.image_path)[1].lower()
        media_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        content.append({"type": "text", "text": f"IMAGE {i + 1}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_data},
        })

    content.append({
        "type": "text",
        "text": SELECTION_PROMPT.format(store_name=store.name),
    })

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )

    result_text = response.content[0].text
    logger.info("Selection result for %s:\n%s", store.name, result_text)

    winner_idx = _parse_winner(result_text)
    if winner_idx is not None and 0 <= winner_idx < len(candidates):
        winner = candidates[winner_idx]
        winner.score = 10.0
        _parse_garment_details(result_text, winner_idx, winner)
        store.status = StoreStatus.GARMENT_SELECTED
        logger.info("Selected garment %d for %s: %s", winner_idx + 1, store.name, winner.description)
        return winner

    logger.warning("Could not parse winner for %s, defaulting to first", store.name)
    store.status = StoreStatus.GARMENT_SELECTED
    return candidates[0]


def _parse_winner(text: str) -> int | None:
    for line in text.strip().split("\n"):
        line = line.strip().upper()
        if line.startswith("WINNER:"):
            try:
                return int(line.split(":")[1].strip()) - 1
            except (ValueError, IndexError):
                return None
    return None


def _parse_garment_details(text: str, idx: int, garment: Garment) -> None:
    target = f"IMAGE {idx + 1}:"
    for line in text.split("\n"):
        if target in line.upper():
            parts = line.split("|")
            for part in parts:
                part = part.strip()
                if part.lower().startswith("category="):
                    garment.category = part.split("=", 1)[1].strip()
                elif part.lower().startswith("score="):
                    try:
                        garment.score = float(part.split("=", 1)[1].strip())
                    except ValueError:
                        pass
                else:
                    if "=" not in part and len(part) > 5:
                        garment.description = part
            break
