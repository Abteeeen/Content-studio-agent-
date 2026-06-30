import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
LOB_API_KEY = os.getenv("LOB_API_KEY", "")
STANNP_API_KEY = os.getenv("STANNP_API_KEY", "")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples", "sample_output")

PLACES_SEARCH_RADIUS = 5000
MIN_STORE_RATING = 3.5
MIN_STORE_REVIEWS = 10
MIN_PHOTO_COUNT = 3

POSTCARD_WIDTH = 1875  # 6.25" x 300dpi
POSTCARD_HEIGHT = 1275  # 4.25" x 300dpi
POSTCARD_BLEED = 38    # 0.125" bleed

REEL_WIDTH = 1080
REEL_HEIGHT = 1920
