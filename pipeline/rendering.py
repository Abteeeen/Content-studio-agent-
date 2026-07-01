"""Step 5: Render the garment on a model in a cinematic 9:16 reel.

Pipeline (all on Replicate free trial):
1. IDM-VTON — virtual try-on: puts the garment on a stock model photo
2. Stable Video Diffusion — animates the result into a cinematic 4s reel
"""

from __future__ import annotations

import logging
import os
import time

import replicate
import requests

from pipeline.config import OUTPUT_DIR, REPLICATE_API_TOKEN
from pipeline.models import Garment, ReelOutput, Store, StoreStatus

logger = logging.getLogger(__name__)

MODEL_PHOTOS = [
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&q=80",
    "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&q=80",
    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800&q=80",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&q=80",
]


def render_reel(store: Store, garment: Garment, method: str = "replicate") -> ReelOutput:
    """Render a cinematic reel. Returns ReelOutput with video path and URL."""
    if method == "replicate":
        return _render_replicate(store, garment)
    raise ValueError(f"Unknown rendering method: {method}")


def _render_replicate(store: Store, garment: Garment) -> ReelOutput:
    """Virtual try-on + video generation using Replicate free trial."""
    if not REPLICATE_API_TOKEN:
        logger.warning("REPLICATE_API_TOKEN not set — skipping render for %s", store.name)
        return ReelOutput(thumbnail_path=garment.image_path)

    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    # Step 1: Virtual try-on (IDM-VTON)
    logger.info("Running virtual try-on for %s...", store.name)
    try:
        with open(garment.image_path, "rb") as garm_file:
            tryon_output = client.run(
                "cuuupid/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f",
                input={
                    "crop": False,
                    "seed": 42,
                    "steps": 30,
                    "category": garment.category or "upper_body",
                    "garm_img": garm_file,
                    "human_img": MODEL_PHOTOS[0],
                    "garment_des": garment.description or "Fashion garment",
                },
            )

        # Replicate can return a list or a string — handle both
        tryon_url = _extract_url(tryon_output)
        tryon_path = os.path.join(store_dir, "tryon_result.png")
        _download(tryon_url, tryon_path)
        logger.info("Try-on complete: %s", tryon_path)

    except Exception as e:
        logger.error("Virtual try-on failed for %s: %s — using garment image", store.name, e)
        tryon_path = garment.image_path

    # Step 2: Animate to cinematic video (Stable Video Diffusion)
    logger.info("Generating cinematic reel for %s...", store.name)
    try:
        with open(tryon_path, "rb") as img_file:
            video_output = client.run(
                "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
                input={
                    "input_image": img_file,
                    "sizing_strategy": "maintain_aspect_ratio",
                    "frames_per_second": 6,
                    "motion_bucket_id": 127,
                },
            )

        video_url = _extract_url(video_output)
        video_path = os.path.join(store_dir, "cinematic_reel.mp4")
        _download(video_url, video_path)
        logger.info("Reel rendered: %s", video_path)

    except Exception as e:
        logger.error("Video generation failed for %s: %s", store.name, e)
        video_path = ""
        video_url = ""

    store.status = StoreStatus.REEL_RENDERED
    return ReelOutput(
        video_path=video_path,
        video_url=video_url if video_path else "",
        thumbnail_path=tryon_path,
        duration=4.0,
    )


def _extract_url(output) -> str:
    """Safely extract a URL from Replicate output (can be str, list, or FileOutput)."""
    if isinstance(output, list):
        return str(output[0])
    # replicate FileOutput objects have a .url attribute
    if hasattr(output, "url"):
        return str(output.url)
    return str(output)


def _download(url: str, path: str) -> None:
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^\w]", "_", text.lower()).strip("_")[:50]
