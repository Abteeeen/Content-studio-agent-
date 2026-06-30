"""Virtual Try-On Module — How a model wears the dress.

This is the core AI magic: we take a garment image from the store and
digitally place it onto a model photo, as if the model is actually wearing it.

How it works (IDM-VTON on Replicate):

1. INPUT: Two images
   - Garment image (scraped from the store's website/Google listing)
   - Model image (a stock photo of a person in a neutral pose)

2. AI PROCESSING:
   - The model segments the garment from its background
   - It understands the garment's shape, texture, color, and draping
   - It maps the garment onto the model's body, matching pose and proportions
   - It re-renders lighting, shadows, and fabric folds realistically

3. OUTPUT: A photorealistic image of the model wearing that exact garment

Available free-trial models:
- IDM-VTON (Replicate) — best quality, handles dresses/tops/jackets
- OOTDiffusion (Replicate) — good alternative, faster
- KlingAI Try-On — free tier available

After try-on, the result image feeds into video generation (Stable Video
Diffusion) to create the cinematic reel with movement.
"""

from __future__ import annotations

import logging
import os

import replicate
import requests

from pipeline.config import REPLICATE_API_TOKEN, OUTPUT_DIR

logger = logging.getLogger(__name__)

MODEL_PHOTOS = {
    "female_1": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800",
    "female_2": "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800",
    "male_1": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800",
    "male_2": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800",
}

TRYON_MODELS = {
    "idm_vton": "cuuupid/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f",
    "ootd": "viktorfa/ootd:629e50f764be47a681208c8e7ba0a3f2f4fce8bc1105cc0772f9faded5402423",
}

VIDEO_MODELS = {
    "svd": "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
    "animate_diff": "lucataco/animate-diff:beecf59c4aee8d81bf04f0381033dfa10dc16e845b4ae00d281e2fa377e48a9f",
}


def virtual_tryon(
    garment_image_path: str,
    output_dir: str,
    model_photo: str = "female_1",
    category: str = "upper_body",
    garment_description: str = "",
    engine: str = "idm_vton",
) -> str:
    """Put a garment onto a model using AI virtual try-on.

    Args:
        garment_image_path: Local path to the garment image
        output_dir: Where to save the result
        model_photo: Key from MODEL_PHOTOS or a direct URL
        category: "upper_body", "lower_body", or "full_body"
        garment_description: Text description of the garment
        engine: "idm_vton" or "ootd"

    Returns:
        Path to the try-on result image
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    os.makedirs(output_dir, exist_ok=True)

    model_url = MODEL_PHOTOS.get(model_photo, model_photo)
    model_id = TRYON_MODELS.get(engine, TRYON_MODELS["idm_vton"])

    logger.info("Running virtual try-on with %s...", engine)

    if engine == "idm_vton":
        output = client.run(
            model_id,
            input={
                "crop": False,
                "seed": 42,
                "steps": 30,
                "category": category,
                "garm_img": open(garment_image_path, "rb"),
                "human_img": model_url,
                "garment_des": garment_description or "Fashion garment",
            },
        )
    elif engine == "ootd":
        output = client.run(
            model_id,
            input={
                "seed": 42,
                "steps": 20,
                "model_type": "half" if category == "upper_body" else "full",
                "cloth_image": open(garment_image_path, "rb"),
                "model_image": model_url,
            },
        )
    else:
        raise ValueError(f"Unknown try-on engine: {engine}")

    result_url = str(output)
    result_path = os.path.join(output_dir, "tryon_result.png")
    _download(result_url, result_path)

    logger.info("Try-on complete: %s", result_path)
    return result_path


def generate_cinematic_video(
    image_path: str,
    output_dir: str,
    engine: str = "svd",
    fps: int = 6,
) -> str:
    """Animate the try-on result into a cinematic video reel.

    Args:
        image_path: Path to the try-on result image
        output_dir: Where to save the video
        engine: "svd" (Stable Video Diffusion) or "animate_diff"
        fps: Frames per second

    Returns:
        Path to the generated video
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    os.makedirs(output_dir, exist_ok=True)

    model_id = VIDEO_MODELS.get(engine, VIDEO_MODELS["svd"])

    logger.info("Generating cinematic video with %s...", engine)

    if engine == "svd":
        output = client.run(
            model_id,
            input={
                "input_image": open(image_path, "rb"),
                "sizing_strategy": "maintain_aspect_ratio",
                "frames_per_second": fps,
                "motion_bucket_id": 127,
            },
        )
    elif engine == "animate_diff":
        output = client.run(
            model_id,
            input={
                "path": image_path,
                "seed": 42,
                "steps": 25,
                "prompt": "fashion model walking, cinematic lighting, slow motion, studio",
                "n_prompt": "blurry, low quality, distorted",
            },
        )
    else:
        raise ValueError(f"Unknown video engine: {engine}")

    video_url = str(output)
    video_path = os.path.join(output_dir, "cinematic_reel.mp4")
    _download(video_url, video_path)

    logger.info("Video generated: %s", video_path)
    return video_path


def full_pipeline(
    garment_image_path: str,
    output_dir: str,
    garment_description: str = "",
    model_photo: str = "female_1",
    category: str = "upper_body",
) -> dict:
    """Run the complete try-on + video pipeline.

    Returns dict with paths to all generated assets.
    """
    tryon_path = virtual_tryon(
        garment_image_path=garment_image_path,
        output_dir=output_dir,
        model_photo=model_photo,
        category=category,
        garment_description=garment_description,
    )

    video_path = generate_cinematic_video(
        image_path=tryon_path,
        output_dir=output_dir,
    )

    return {
        "tryon_image": tryon_path,
        "video": video_path,
        "model_photo": model_photo,
        "category": category,
    }


def _download(url: str, path: str) -> None:
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
