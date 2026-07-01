"""Step 5: Render the garment on a model in a cinematic 9:16 reel.

Backends:
  --render-method replicate    IDM-VTON + Stable Video Diffusion (needs Replicate credits ~$0.05/run)
  --render-method fal          fal.ai IDM-VTON (free $1 signup credit, ~20 try-ons)
  --render-method segmind      Segmind virtual try-on (Indian startup, free credits, works in India)
  --render-method free         Hugging Face Inference API (truly free but unreliable)
"""

from __future__ import annotations

import logging
import os
import time

import requests

from pipeline.config import OUTPUT_DIR, REPLICATE_API_TOKEN, FAL_API_KEY, SEGMIND_API_KEY, WAVESPEED_API_KEY
from pipeline.models import Garment, ReelOutput, Store, StoreStatus

logger = logging.getLogger(__name__)

MODEL_PHOTOS = [
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&q=80",
    "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&q=80",
    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800&q=80",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&q=80",
]

HF_TRYON_API = "https://api-inference.huggingface.co/models/yisol/IDM-VTON"
FAL_TRYON_URL = "https://fal.run/fal-ai/idm-vton"
FAL_VIDEO_URL = "https://fal.run/fal-ai/stable-video"

WAVESPEED_VIDEO_URL = "https://api.wavespeed.ai/api/v3/alibaba/wan-2.7/image-to-video"
WAVESPEED_RESULT_URL = "https://api.wavespeed.ai/api/v3/predictions/{id}/result"


def render_reel(store: Store, garment: Garment, method: str = "replicate") -> ReelOutput:
    """Render a cinematic reel. Returns ReelOutput with video path and URL."""
    if method == "replicate":
        return _render_replicate(store, garment)
    elif method == "fal":
        return _render_fal(store, garment)
    elif method == "segmind":
        return _render_segmind(store, garment)
    elif method == "free":
        return _render_free(store, garment)
    elif method == "wavespeed":
        return _render_wavespeed(store, garment)
    raise ValueError(f"Unknown rendering method: {method}")


# ─── Free rendering via Hugging Face ─────────────────────────────────────────

def _render_free(store: Store, garment: Garment) -> ReelOutput:
    """Generate try-on + video using Hugging Face free inference.

    This is slower and lower quality than Replicate, but costs $0.
    If HF models are loading/unavailable, falls back to postcard-only mode.
    """
    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    tryon_path = garment.image_path
    video_url = ""
    video_path = ""

    # Step 1: Try virtual try-on via HF
    logger.info("Running free virtual try-on for %s (Hugging Face)...", store.name)
    try:
        model_resp = requests.get(MODEL_PHOTOS[0], timeout=15)
        model_resp.raise_for_status()

        with open(garment.image_path, "rb") as f:
            garment_bytes = f.read()

        resp = requests.post(
            HF_TRYON_API,
            headers={"Content-Type": "application/json"},
            json={
                "inputs": {
                    "image": _bytes_to_base64(model_resp.content),
                    "garment": _bytes_to_base64(garment_bytes),
                }
            },
            timeout=120,
        )

        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            tryon_path = os.path.join(store_dir, "tryon_result.png")
            with open(tryon_path, "wb") as f:
                f.write(resp.content)
            logger.info("Free try-on complete: %s", tryon_path)
        elif resp.status_code == 503:
            logger.warning("HF try-on model is loading — using original garment image")
        else:
            logger.warning("HF try-on returned %d — using original garment image", resp.status_code)

    except Exception as e:
        logger.error("Free try-on failed for %s: %s — using garment image", store.name, e)

    store.status = StoreStatus.REEL_RENDERED
    return ReelOutput(
        video_path=video_path,
        video_url=video_url,
        thumbnail_path=tryon_path,
        duration=4.0,
    )


def _fal_upload(file_path: str, headers: dict) -> str:
    """Upload a local file to fal.ai storage and return the public URL."""
    ext = os.path.splitext(file_path)[1].lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")
    upload_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://storage.fal.run/",
            headers=upload_headers,
            files={"file": (os.path.basename(file_path), f, mime)},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["url"]


def _bytes_to_base64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("utf-8")


# ─── fal.ai rendering (free $1 signup credit) ────────────────────────────────

def _render_fal(store: Store, garment: Garment) -> ReelOutput:
    """Virtual try-on + video via fal.ai. Free $1 credit on signup (~20 try-ons).

    Sign up: fal.ai → Dashboard → API Keys → copy key
    Add to .env: FAL_API_KEY=your_key_here
    """
    if not FAL_API_KEY:
        logger.warning("FAL_API_KEY not set — falling back to garment image for %s", store.name)
        store.status = StoreStatus.REEL_RENDERED
        return ReelOutput(thumbnail_path=garment.image_path)

    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)
    headers = {"Authorization": f"Key {FAL_API_KEY}", "Content-Type": "application/json"}

    tryon_path = garment.image_path
    video_path = ""
    video_url = ""

    # Step 1: Upload images to fal.ai storage (fal requires real URLs, not base64)
    logger.info("Uploading images to fal.ai storage for %s...", store.name)
    try:
        garment_url = _fal_upload(garment.image_path, headers)
        model_resp = requests.get(MODEL_PHOTOS[0], timeout=15)
        model_resp.raise_for_status()
        model_path = os.path.join(store_dir, "model.jpg")
        with open(model_path, "wb") as f:
            f.write(model_resp.content)
        model_url = _fal_upload(model_path, headers)
    except Exception as e:
        logger.error("fal.ai image upload failed for %s: %s — using garment image", store.name, e)
        store.status = StoreStatus.REEL_RENDERED
        return ReelOutput(thumbnail_path=tryon_path)

    # Step 2: Virtual try-on via fal.ai IDM-VTON
    logger.info("Running fal.ai virtual try-on for %s...", store.name)
    try:
        resp = requests.post(
            FAL_TRYON_URL,
            headers=headers,
            json={
                "human_image_url": model_url,
                "garment_image_url": garment_url,
                "garment_description": garment.description or "Fashion garment",
                "category": garment.category or "upper_body",
            },
            timeout=180,
        )
        resp.raise_for_status()
        result = resp.json()

        tryon_img_url = result.get("image", {}).get("url", "")
        if tryon_img_url:
            tryon_path = os.path.join(store_dir, "tryon_result.png")
            _download(tryon_img_url, tryon_path)
            logger.info("fal.ai try-on complete: %s", tryon_path)
        else:
            logger.warning("fal.ai try-on returned no image — using garment image. Response: %s", result)

    except Exception as e:
        logger.error("fal.ai try-on failed for %s: %s — using garment image", store.name, e)

    # Step 3: Animate to video via fal.ai stable-video
    logger.info("Generating video reel via fal.ai for %s...", store.name)
    try:
        tryon_url_for_video = _fal_upload(tryon_path, headers)
        resp = requests.post(
            FAL_VIDEO_URL,
            headers=headers,
            json={
                "image_url": tryon_url_for_video,
                "motion_bucket_id": 127,
                "fps": 6,
            },
            timeout=240,
        )
        resp.raise_for_status()
        result = resp.json()

        video_url = result.get("video", {}).get("url", "")
        if video_url:
            video_path = os.path.join(store_dir, "cinematic_reel.mp4")
            _download(video_url, video_path)
            logger.info("fal.ai reel rendered: %s", video_path)

    except Exception as e:
        logger.error("fal.ai video failed for %s: %s", store.name, e)

    store.status = StoreStatus.REEL_RENDERED
    return ReelOutput(
        video_path=video_path,
        video_url=video_url,
        thumbnail_path=tryon_path,
        duration=4.0,
    )


# ─── Segmind rendering (Indian startup — works in India, free credits) ───────

SEGMIND_TRYON_URL = "https://api.segmind.com/v1/idm-vton"
SEGMIND_VIDEO_URL = "https://api.segmind.com/v1/stable-video-diffusion"


def _render_segmind(store: Store, garment: Garment) -> ReelOutput:
    """Virtual try-on + video via Segmind API.

    Indian AI startup — accessible from India without VPN.
    Free credits on signup at segmind.com.
    Add to .env: SEGMIND_API_KEY=your_key
    """
    if not SEGMIND_API_KEY:
        logger.warning("SEGMIND_API_KEY not set — using garment image for %s", store.name)
        store.status = StoreStatus.REEL_RENDERED
        return ReelOutput(thumbnail_path=garment.image_path)

    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)
    headers = {"x-api-key": SEGMIND_API_KEY, "Content-Type": "application/json"}

    tryon_path = garment.image_path
    video_path = ""
    video_url = ""

    # Step 1: Virtual try-on
    logger.info("Running Segmind virtual try-on for %s...", store.name)
    try:
        with open(garment.image_path, "rb") as f:
            garment_b64 = _bytes_to_base64(f.read())
        model_resp = requests.get(MODEL_PHOTOS[0], timeout=15)
        model_resp.raise_for_status()
        model_b64 = _bytes_to_base64(model_resp.content)

        resp = requests.post(
            SEGMIND_TRYON_URL,
            headers=headers,
            json={
                "human_img": model_b64,
                "garm_img": garment_b64,
                "garment_des": garment.description or "Fashion garment",
                "category": garment.category or "upper_body",
                "crop": False,
                "seed": 42,
                "steps": 30,
            },
            timeout=120,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if content_type.startswith("image"):
            tryon_path = os.path.join(store_dir, "tryon_result.png")
            with open(tryon_path, "wb") as f:
                f.write(resp.content)
            logger.info("Segmind try-on complete: %s", tryon_path)
        elif "json" in content_type:
            result = resp.json()
            img_url = result.get("image", result.get("output", ""))
            if img_url and img_url.startswith("http"):
                tryon_path = os.path.join(store_dir, "tryon_result.png")
                _download(img_url, tryon_path)
                logger.info("Segmind try-on complete: %s", tryon_path)
            else:
                logger.warning("Segmind try-on response: %s", result)
        else:
            logger.warning("Segmind try-on unexpected content-type: %s — body: %s", content_type, resp.text[:200])

    except Exception as e:
        logger.error("Segmind try-on failed for %s: %s — using garment image", store.name, e)

    # Segmind does not offer video generation — try-on image is used on postcard directly
    logger.info("Segmind: using try-on image for postcard (no video generation available)")

    store.status = StoreStatus.REEL_RENDERED
    return ReelOutput(
        video_path=video_path,
        video_url=video_url,
        thumbnail_path=tryon_path,
        duration=4.0,
    )


# ─── Replicate rendering (paid credits) ──────────────────────────────────────

def _render_replicate(store: Store, garment: Garment) -> ReelOutput:
    """Virtual try-on + video generation using Replicate."""
    if not REPLICATE_API_TOKEN:
        logger.warning("REPLICATE_API_TOKEN not set — skipping render for %s", store.name)
        return ReelOutput(thumbnail_path=garment.image_path)

    import replicate
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


# ─── WaveSpeedAI rendering (free $1 credit, no card, globally accessible) ────

def _render_wavespeed(store: Store, garment: Garment) -> ReelOutput:
    """Virtual try-on (Segmind) + video via WaveSpeedAI WAN 2.7.

    WaveSpeedAI gives $1 free credit on signup — no credit card required.
    Sign up: wavespeed.ai → Dashboard → API Keys → copy key
    Add to .env: WAVESPEED_API_KEY=your_key_here

    WAN 2.7 image-to-video: ~$0.012 per second of video (4s ≈ $0.05)
    """
    if not WAVESPEED_API_KEY:
        logger.warning("WAVESPEED_API_KEY not set — falling back to garment image for %s", store.name)
        store.status = StoreStatus.REEL_RENDERED
        return ReelOutput(thumbnail_path=garment.image_path)

    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    tryon_path = garment.image_path
    video_path = ""
    video_url = ""

    # Step 1: Virtual try-on via Segmind (if key available), else use garment image
    if SEGMIND_API_KEY:
        logger.info("Running Segmind virtual try-on for %s (wavespeed pipeline)...", store.name)
        try:
            with open(garment.image_path, "rb") as f:
                garment_b64 = _bytes_to_base64(f.read())
            model_resp = requests.get(MODEL_PHOTOS[0], timeout=15)
            model_resp.raise_for_status()
            model_b64 = _bytes_to_base64(model_resp.content)

            seg_headers = {"x-api-key": SEGMIND_API_KEY, "Content-Type": "application/json"}
            resp = requests.post(
                SEGMIND_TRYON_URL,
                headers=seg_headers,
                json={
                    "human_img": model_b64,
                    "garm_img": garment_b64,
                    "garment_des": garment.description or "Fashion garment",
                    "category": garment.category or "upper_body",
                    "crop": False,
                    "seed": 42,
                    "steps": 30,
                },
                timeout=120,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if content_type.startswith("image"):
                tryon_path = os.path.join(store_dir, "tryon_result.png")
                with open(tryon_path, "wb") as f:
                    f.write(resp.content)
                logger.info("Segmind try-on complete: %s", tryon_path)
            elif "json" in content_type:
                result = resp.json()
                img_url = result.get("image", result.get("output", ""))
                if img_url and img_url.startswith("http"):
                    tryon_path = os.path.join(store_dir, "tryon_result.png")
                    _download(img_url, tryon_path)
                    logger.info("Segmind try-on complete: %s", tryon_path)
                else:
                    logger.warning("Segmind try-on returned no image — using garment image. Response: %s", result)
            else:
                logger.warning("Segmind unexpected content-type %s — using garment image", content_type)
        except Exception as e:
            logger.error("Segmind try-on failed: %s — using garment image", e)
    else:
        logger.info("SEGMIND_API_KEY not set — using garment image directly for WaveSpeed video")

    # Step 2: Convert try-on image to base64 for WaveSpeedAI
    logger.info("Generating video via WaveSpeedAI WAN 2.7 for %s...", store.name)
    try:
        with open(tryon_path, "rb") as f:
            image_b64 = _bytes_to_base64(f.read())

        ext = os.path.splitext(tryon_path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        image_data_uri = f"data:{mime};base64,{image_b64}"

        ws_headers = {
            "Authorization": f"Bearer {WAVESPEED_API_KEY}",
            "Content-Type": "application/json",
        }

        submit_resp = requests.post(
            WAVESPEED_VIDEO_URL,
            headers=ws_headers,
            json={
                "image": image_data_uri,
                "prompt": f"cinematic fashion reel, model wearing {garment.description or 'stylish clothing'}, smooth camera movement, professional lighting",
                "duration": 4,
                "resolution": "480p",
                "enable_safety_checker": True,
            },
            timeout=60,
        )
        submit_resp.raise_for_status()
        submit_data = submit_resp.json()

        prediction_id = (
            submit_data.get("data", {}).get("id")
            or submit_data.get("id")
            or submit_data.get("prediction_id")
        )
        if not prediction_id:
            logger.error("WaveSpeedAI: no prediction ID in response: %s", submit_data)
            raise ValueError("No prediction ID returned")

        logger.info("WaveSpeedAI job submitted: %s — polling for result...", prediction_id)

        # Poll for result (WAN 2.7 takes ~30-90 seconds)
        result_url = WAVESPEED_RESULT_URL.format(id=prediction_id)
        for attempt in range(60):
            time.sleep(5)
            poll_resp = requests.get(result_url, headers=ws_headers, timeout=30)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = (
                poll_data.get("data", {}).get("status")
                or poll_data.get("status")
                or ""
            )
            logger.debug("WaveSpeedAI poll %d: status=%s", attempt + 1, status)

            if status == "completed":
                outputs = (
                    poll_data.get("data", {}).get("outputs")
                    or poll_data.get("outputs")
                    or []
                )
                video_url = outputs[0] if outputs else ""
                if not video_url:
                    logger.error("WaveSpeedAI completed but no output URL: %s", poll_data)
                    break
                video_path = os.path.join(store_dir, "cinematic_reel.mp4")
                _download(video_url, video_path)
                logger.info("WaveSpeedAI reel rendered: %s", video_path)
                break
            elif status in ("failed", "error", "cancelled"):
                error_msg = (
                    poll_data.get("data", {}).get("error")
                    or poll_data.get("error")
                    or status
                )
                logger.error("WaveSpeedAI job %s: %s", status, error_msg)
                break
        else:
            logger.error("WaveSpeedAI timed out after 5 minutes for %s", store.name)

    except Exception as e:
        logger.error("WaveSpeedAI video failed for %s: %s", store.name, e)

    store.status = StoreStatus.REEL_RENDERED
    return ReelOutput(
        video_path=video_path,
        video_url=video_url,
        thumbnail_path=tryon_path,
        duration=4.0,
    )


def _extract_url(output) -> str:
    """Safely extract a URL from Replicate output (can be str, list, or FileOutput)."""
    if isinstance(output, list):
        return str(output[0])
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
