"""Run this FIRST to check your setup is correct before running the pipeline.

Usage:
    python setup_check.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

ok = f"{GREEN}[OK]{RESET}"
fail = f"{RED}[MISSING]{RESET}"
warn = f"{YELLOW}[OPTIONAL]{RESET}"


def check(label, value, required=True):
    if value:
        print(f"  {ok}  {label}")
        return True
    else:
        tag = fail if required else warn
        print(f"  {tag}  {label}")
        return False


def test_groq(key):
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def test_yelp(key):
    try:
        resp = requests.get(
            "https://api.yelp.com/v3/businesses/search",
            headers={"Authorization": f"Bearer {key}"},
            params={"term": "clothing", "location": "New York", "limit": 1},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def test_google(key):
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": "New York", "key": key},
            timeout=5,
        )
        data = resp.json()
        return data.get("status") not in ("REQUEST_DENIED", "INVALID_REQUEST")
    except Exception:
        return False


def test_osm():
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "New York", "format": "json", "limit": 1},
            headers={"User-Agent": "OutreachAutopilot/1.0"},
            timeout=5,
        )
        return resp.status_code == 200 and len(resp.json()) > 0
    except Exception:
        return False


def test_replicate(token):
    try:
        resp = requests.get(
            "https://api.replicate.com/v1/account",
            headers={"Authorization": f"Token {token}"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


print(f"\n{BOLD}=== Outreach Autopilot — Setup Check ==={RESET}\n")

print(f"{BOLD}1. Checking .env file...{RESET}")
if not os.path.exists(".env"):
    print(f"  {RED}[ERROR]{RESET} .env file not found!")
    print(f"  Run: cp .env.example .env  then fill in your keys\n")
    sys.exit(1)
else:
    print(f"  {ok}  .env file found\n")

GOOGLE = os.getenv("GOOGLE_MAPS_API_KEY", "")
YELP = os.getenv("YELP_API_KEY", "")
GROQ = os.getenv("GROQ_API_KEY", "")
REPLICATE = os.getenv("REPLICATE_API_TOKEN", "")
LOB = os.getenv("LOB_API_KEY", "")
SMTP = os.getenv("SMTP_USER", "")

print(f"{BOLD}2. Checking API keys in .env...{RESET}")
if YELP:
    check("YELP_API_KEY (store discovery — free)", YELP)
elif GOOGLE:
    check("GOOGLE_MAPS_API_KEY (store discovery)", GOOGLE)
else:
    print(f"  {YELLOW}[INFO]{RESET}  No Yelp or Google key — will use OpenStreetMap (--source osm). That's fine!")
discovery_ok = bool(YELP or GOOGLE or True)  # OSM always available
gr_ok = check("GROQ_API_KEY (AI vision — free)", GROQ)
r_ok = check("REPLICATE_API_TOKEN (virtual try-on)", REPLICATE)
l_ok = check("LOB_API_KEY (postcard mailing)", LOB)
check("SMTP_USER (email follow-up — optional)", SMTP, required=False)
print()

print(f"{BOLD}3. Testing API connections...{RESET}")

if YELP:
    if test_yelp(YELP):
        print(f"  {ok}  Yelp API — connected and working (FREE)")
    else:
        print(f"  {RED}[FAIL]{RESET}  Yelp API — key invalid")
        print(f"         → Go to docs.developer.yelp.com → My Apps → Create App → copy API Key")
elif GOOGLE:
    if test_google(GOOGLE):
        print(f"  {ok}  Google Maps API — connected and working")
    else:
        print(f"  {RED}[FAIL]{RESET}  Google Maps API — key invalid or Places API not enabled")
        print(f"         → Go to console.cloud.google.com → Enable 'Places API' and 'Geocoding API'")
else:
    if test_osm():
        print(f"  {ok}  OpenStreetMap — connected (FREE, no signup needed)")
        print(f"         Run with: --source osm")

if GROQ:
    if test_groq(GROQ):
        print(f"  {ok}  Groq API — connected and working (FREE)")
    else:
        print(f"  {RED}[FAIL]{RESET}  Groq API — key invalid")
        print(f"         → Go to console.groq.com → API Keys → create a new key")

if REPLICATE:
    if test_replicate(REPLICATE):
        print(f"  {ok}  Replicate API — connected and working")
    else:
        print(f"  {RED}[FAIL]{RESET}  Replicate API — token invalid")
        print(f"         → Go to replicate.com → Account Settings → API Tokens")

print()

all_required = gr_ok and r_ok
if all_required:
    print(f"{GREEN}{BOLD}✓ All required keys are set! You're ready to run.{RESET}")
    src = "yelp" if YELP else ("google" if GOOGLE else "osm")
    print(f"\n{BOLD}Try a demo run (no API calls):{RESET}")
    print(f"  python -m pipeline.run --demo")
    print(f"\n{BOLD}Run a real campaign (dry-run — discovers but doesn't mail):{RESET}")
    print(f"  python -m pipeline.run --city \"Los Angeles\" --limit 3 --dry-run --source {src}")
    print(f"\n{BOLD}Full run — finds stores, makes reels, mails postcards:{RESET}")
    print(f"  python -m pipeline.run --city \"Los Angeles\" --limit 3 --source {src}")
    print(f"\n{BOLD}Launch the web dashboard:{RESET}")
    print(f"  python -m webapp")
    print(f"  → Open http://localhost:5000\n")
else:
    print(f"{RED}{BOLD}✗ Some required keys are missing. Fill them in .env and run this again.{RESET}")
    print(f"\n{BOLD}Where to get each key:{RESET}")
    if not YELP and not GOOGLE:
        print(f"  Store discovery: You can use OpenStreetMap for free (no key needed)")
        print(f"    Or get a free Yelp key → https://docs.developer.yelp.com/")
        print(f"    1. Sign up → My Apps → Create App → copy 'API Key'")
    elif YELP and not test_yelp(YELP):
        print(f"  Yelp → https://docs.developer.yelp.com/")
        print(f"    1. Sign up → My Apps → Create App → copy 'API Key'")
    if not gr_ok:
        print(f"  Groq (FREE) → https://console.groq.com")
        print(f"    1. Sign up free → API Keys → Create API Key → copy it")
    if not r_ok:
        print(f"  Replicate   → https://replicate.com")
        print(f"    1. Sign up free → Account Settings → API Tokens → copy it")
    print()
