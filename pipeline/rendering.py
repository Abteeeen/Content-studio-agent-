"""Step 5: Render the garment on a model in a cinematic 9:16 reel.

Rendering paths (all free trial):
1. Replicate — IDM-VTON virtual try-on + Stable Video Diffusion animation
2. Runway ML — image-to-video cinematic generation (free trial credits)
3. Kling AI — free tier video generation alternative

The Replicate path is the default and gives the best portfolio results.
"""

from __future__ import annotations

import logging
import os

import replicate
import requests

from pipeline.config import OUTPUT_DIR, REPLICATE_API_TOKEN
from pipeline.models import Garment, ReelOutput, Store, StoreStatus

logger = logging.getLogger(__name__)


def render_reel(store: Store, garment: Garment, method: str = "replicate") -> ReelOutput:
    """Render a cinematic reel. Dispatches to the chosen method."""
    if method == "replicate":
        return _render_replicate(store, garment)
    elif method == "runway":
        return _render_runway_placeholder(store, garment)
    else:
        raise ValueError(f"Unknown rendering method: {method}")


def _render_replicate(store: Store, garment: Garment) -> ReelOutput:
    """Render using Replicate's free trial credits.

    Pipeline:
    1. Virtual try-on (IDM-VTON) — puts the garment on a model photo
    2. Image-to-video (Stable Video Diffusion) — animates to cinematic reel
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    # Step 1: Virtual try-on
    logger.info("Running virtual try-on for %s...", store.name)
    tryon_output = client.run(
        "cuuupid/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f",
        input={
            "crop": False,
            "seed": 42,
            "steps": 30,
            "category": "upper_body",
            "garm_img": open(garment.image_path, "rb"),
            "human_img": _get_model_image_url(),
            "garment_des": garment.description or f"Fashion {garment.category or 'garment'}",
        },
    )

    tryon_url = str(tryon_output)
    tryon_path = os.path.join(store_dir, "tryon_result.png")
    _download(tryon_url, tryon_path)
    logger.info("Try-on complete: %s", tryon_path)

    # Step 2: Animate to cinematic video
    logger.info("Generating cinematic reel for %s...", store.name)
    video_output = client.run(
        "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
        input={
            "input_image": open(tryon_path, "rb"),
            "sizing_strategy": "maintain_aspect_ratio",
            "frames_per_second": 6,
            "motion_bucket_id": 127,
        },
    )

    video_url = str(video_output)
    video_path = os.path.join(store_dir, "cinematic_reel.mp4")
    _download(video_url, video_path)

    store.status = StoreStatus.REEL_RENDERED
    logger.info("Reel rendered: %s", video_path)

    return ReelOutput(
        video_path=video_path,
        video_url=video_url,
        thumbnail_path=tryon_path,
        duration=4.0,
    )


def _render_runway_placeholder(store: Store, garment: Garment) -> ReelOutput:
    """Placeholder for Runway ML Gen-3 integration.

    Runway offers free trial credits. Their API accepts an image + text prompt
    and generates a cinematic video. Sign up at runwayml.com for free credits.

    To integrate:
    1. pip install runwayml
    2. Set RUNWAY_API_KEY in .env
    3. Use their image-to-video endpoint with the try-on result
    """
    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    logger.info(
        "Runway ML rendering not yet connected. "
        "Sign up at runwayml.com for free trial credits, then set RUNWAY_API_KEY."
    )
    return ReelOutput(
        video_path="",
        video_url="",
        thumbnail_path=garment.image_path,
    )


def build_cinematic_prompt(store: Store, garment: Garment) -> str:
    """Build the text prompt for any image-to-video model."""
    category = garment.category or "fashion piece"
    return (
        f"Cinematic fashion reel, 9:16 vertical. "
        f"A professional model wearing a stunning {category} walks toward camera "
        f"in dramatic studio lighting. Slow motion, multiple angles — "
        f"front view, side profile, detail close-up on fabric texture. "
        f"High-end fashion film look, shallow depth of field, warm golden tones. "
        f"The {category} is the hero — make it look aspirational and luxurious."
    )


def _get_model_image_url() -> str:
    """Stock model image for virtual try-on. Replace with your own model photos."""
    return "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800"


def _download(url: str, path: str) -> None:
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^\w]", "_", text.lower()).strip("_")[:50]
