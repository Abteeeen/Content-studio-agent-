"""Step 6: Generate a print-ready postcard with a reel frame + QR code.

Produces two images:
- Front: Hero frame from the reel with store name overlay
- Back: QR code linking to the reel, personalized message, agency branding

Output is 6.25" x 4.25" at 300 DPI (1875 x 1275 px) with 0.125" bleed.
Uses only free Python libraries: Pillow + qrcode.
"""

from __future__ import annotations

import logging
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont

from pipeline.config import OUTPUT_DIR, POSTCARD_BLEED, POSTCARD_HEIGHT, POSTCARD_WIDTH
from pipeline.models import PostcardOutput, ReelOutput, Store, StoreStatus

logger = logging.getLogger(__name__)

AGENCY_NAME = "Your Agency Name"
AGENCY_TAGLINE = "We turn your clothes into cinematic content"
AGENCY_WEBSITE = "youragency.com"
AGENCY_EMAIL = "hello@youragency.com"


def generate_postcard(
    store: Store,
    reel: ReelOutput,
    reel_watch_url: str,
) -> PostcardOutput:
    """Generate front and back of a print-ready postcard."""
    store_dir = os.path.join(OUTPUT_DIR, _slugify(store.name))
    os.makedirs(store_dir, exist_ok=True)

    qr_path = _generate_qr(reel_watch_url, store_dir)
    front_path = _generate_front(store, reel, store_dir)
    back_path = _generate_back(store, qr_path, reel_watch_url, store_dir)

    store.status = StoreStatus.POSTCARD_CREATED
    logger.info("Postcard generated for %s", store.name)

    return PostcardOutput(
        front_path=front_path,
        back_path=back_path,
        qr_code_path=qr_path,
        reel_url=reel_watch_url,
    )


def _generate_front(store: Store, reel: ReelOutput, store_dir: str) -> str:
    """Create the postcard front: cinematic frame + store name overlay."""
    card = Image.new("RGB", (POSTCARD_WIDTH, POSTCARD_HEIGHT), (20, 20, 20))
    draw = ImageDraw.Draw(card)

    thumbnail_path = reel.thumbnail_path or reel.video_path
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            thumb = Image.open(thumbnail_path)
            thumb = thumb.convert("RGB")
            thumb = _cover_fit(thumb, POSTCARD_WIDTH, POSTCARD_HEIGHT)
            card.paste(thumb, (0, 0))
            draw = ImageDraw.Draw(card)

            overlay = Image.new("RGBA", (POSTCARD_WIDTH, POSTCARD_HEIGHT), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [(0, POSTCARD_HEIGHT - 300), (POSTCARD_WIDTH, POSTCARD_HEIGHT)],
                fill=(0, 0, 0, 160),
            )
            card = Image.alpha_composite(card.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(card)
        except Exception as e:
            logger.warning("Could not load thumbnail: %s", e)

    font_large = _get_font(48)
    font_small = _get_font(28)

    draw.text(
        (POSTCARD_BLEED + 40, POSTCARD_HEIGHT - 250),
        f"We made this for {store.name}",
        fill=(255, 255, 255),
        font=font_large,
    )
    draw.text(
        (POSTCARD_BLEED + 40, POSTCARD_HEIGHT - 180),
        "Your clothes. A cinematic reel. Zero effort from you.",
        fill=(200, 200, 200),
        font=font_small,
    )
    draw.text(
        (POSTCARD_BLEED + 40, POSTCARD_HEIGHT - 130),
        "Scan the QR on the back to watch it →",
        fill=(255, 200, 50),
        font=font_small,
    )

    front_path = os.path.join(store_dir, "postcard_front.png")
    card.save(front_path, "PNG", dpi=(300, 300))
    return front_path


def _generate_back(store: Store, qr_path: str, reel_url: str, store_dir: str) -> str:
    """Create the postcard back: QR code, message, and agency branding."""
    card = Image.new("RGB", (POSTCARD_WIDTH, POSTCARD_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    font_heading = _get_font(36)
    font_body = _get_font(24)
    font_small = _get_font(18)

    # Left side: personalized message
    owner = store.owner_name or "Store Owner"
    y = POSTCARD_BLEED + 60

    draw.text((POSTCARD_BLEED + 60, y), f"Hey {owner},", fill=(30, 30, 30), font=font_heading)
    y += 60

    message_lines = [
        f"We picked one piece from {store.name},",
        "put it on a model, and made you a",
        "cinematic reel — completely free.",
        "",
        "Scan the QR to watch your reel.",
        "If you like it, imagine what we",
        "could do with your full collection.",
        "",
        f"— {AGENCY_NAME}",
    ]
    for line in message_lines:
        draw.text((POSTCARD_BLEED + 60, y), line, fill=(60, 60, 60), font=font_body)
        y += 35

    # Right side: QR code
    if os.path.exists(qr_path):
        qr_img = Image.open(qr_path).resize((400, 400))
        qr_x = POSTCARD_WIDTH - POSTCARD_BLEED - 460
        qr_y = POSTCARD_BLEED + 80
        card.paste(qr_img, (qr_x, qr_y))

        draw.text(
            (qr_x + 40, qr_y + 420),
            "Watch your reel",
            fill=(30, 30, 30),
            font=font_body,
        )

    # Bottom: agency branding + mailing area
    draw.line(
        [(POSTCARD_BLEED + 40, POSTCARD_HEIGHT - 200),
         (POSTCARD_WIDTH - POSTCARD_BLEED - 40, POSTCARD_HEIGHT - 200)],
        fill=(200, 200, 200),
        width=2,
    )

    draw.text(
        (POSTCARD_BLEED + 60, POSTCARD_HEIGHT - 170),
        f"{AGENCY_NAME} | {AGENCY_WEBSITE} | {AGENCY_EMAIL}",
        fill=(140, 140, 140),
        font=font_small,
    )

    # Mailing address area (right side, bottom)
    addr_x = POSTCARD_WIDTH - POSTCARD_BLEED - 500
    addr_y = POSTCARD_HEIGHT - 170

    addr_lines = store.address.split(",") if store.address else ["[Store Address]"]
    draw.text((addr_x, addr_y - 30), store.name, fill=(30, 30, 30), font=font_body)
    for i, line in enumerate(addr_lines[:3]):
        draw.text((addr_x, addr_y + i * 28), line.strip(), fill=(60, 60, 60), font=font_small)

    back_path = os.path.join(store_dir, "postcard_back.png")
    card.save(back_path, "PNG", dpi=(300, 300))
    return back_path


def _generate_qr(url: str, store_dir: str) -> str:
    """Generate a QR code linking to the reel."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    qr_path = os.path.join(store_dir, "qr_code.png")
    img.save(qr_path)
    return qr_path


def _cover_fit(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize and crop image to cover target dimensions (like CSS cover)."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(target_h * img_ratio)
    else:
        new_w = target_w
        new_h = int(target_w / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a good font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^\w]", "_", text.lower()).strip("_")[:50]
