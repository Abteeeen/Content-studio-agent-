from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class StoreStatus(Enum):
    DISCOVERED = "discovered"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    CLOTHES_EXTRACTED = "clothes_extracted"
    GARMENT_SELECTED = "garment_selected"
    REEL_RENDERED = "reel_rendered"
    POSTCARD_CREATED = "postcard_created"
    MAILED = "mailed"
    FAILED = "failed"


@dataclass
class Store:
    place_id: str
    name: str
    address: str
    phone: str = ""
    website: str = ""
    rating: float = 0.0
    review_count: int = 0
    photo_refs: list[str] = field(default_factory=list)
    lat: float = 0.0
    lng: float = 0.0
    owner_name: str = ""
    status: StoreStatus = StoreStatus.DISCOVERED
    score: float = 0.0


@dataclass
class Garment:
    image_url: str
    image_path: str = ""
    source: str = ""  # "website" or "google_photos"
    description: str = ""
    category: str = ""  # "dress", "jacket", "top", etc.
    score: float = 0.0


@dataclass
class ReelOutput:
    video_path: str = ""
    video_url: str = ""
    thumbnail_path: str = ""
    duration: float = 0.0


@dataclass
class PostcardOutput:
    front_path: str = ""
    back_path: str = ""
    qr_code_path: str = ""
    reel_url: str = ""


@dataclass
class OutreachResult:
    store: Store
    garments: list[Garment] = field(default_factory=list)
    selected_garment: Garment | None = None
    reel: ReelOutput | None = None
    postcard: PostcardOutput | None = None
    mail_tracking_id: str = ""
    error: str = ""
