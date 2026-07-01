# Clothing Store Outreach Autopilot — AI Agent

> An end-to-end autonomous AI agent that finds US clothing stores, picks their best product, animates it into a cinematic video reel, prints a physical postcard, and mails it to the store owner — all without human intervention.

---

## What This Does (in plain English)

1. You give it a city name
2. It finds real clothing stores in that city
3. It visits each store's website and pulls their clothing photos
4. AI picks which garment looks best on camera
5. It generates a cinematic video of that garment
6. It designs and prints a physical postcard with a QR code linking to the video
7. It mails the postcard to the store owner's address

**Zero human involvement after step 1.**

---

## Why This Is an AI Agent (not just automation)

Most pipelines are rule-based: if X then Y. This system makes autonomous decisions at every step:

| Step | What the AI decides |
|------|-------------------|
| Qualification | Scores each store 0–100 and decides which ones are worth pursuing |
| Garment selection | Looks at all scraped images and picks the one with most cinematic impact |
| Postcard copy | Writes personalized copy for each store using their name, garment, and rating |
| Fallback routing | If one video API fails, routes to the next available option automatically |

---

## Full Pipeline

```
City Name
    │
    ▼
[1] DISCOVER ──── OSM / Yelp / Google Maps ──── Finds all clothing stores nearby
    │
    ▼
[2] QUALIFY ───── AI Scoring (0–100) ─────────── Filters low-quality / chain stores
    │
    ▼
[3] EXTRACT ───── Web Scraper ────────────────── Pulls clothing images from website
    │
    ▼
[4] SELECT ────── Groq Vision AI ─────────────── Ranks garments, picks the best one
    │
    ▼
[5] RENDER ────── Virtual Try-On + Video AI ──── Puts garment on model, animates it
    │
    ▼
[6] POSTCARD ──── Pillow + QR Code ───────────── Designs print-ready 4×6 postcard
    │
    ▼
[7] MAIL ──────── Lob API ────────────────────── Physically mails it to store owner
```

---

## Paid vs Free Path — What Changes

This is the honest breakdown of what you get with free tools vs paid tools:

### Free Path (what we built and tested)
| Step | Tool | Cost | Quality |
|------|------|------|---------|
| Store discovery | OpenStreetMap (OSM) | $0 | Good — 56 stores found in LA |
| Geocoding | Nominatim | $0 | Excellent |
| AI garment selection | Groq (Llama 4 Scout) | $0 | Excellent — smart picks |
| Virtual try-on | Segmind IDM-VTON | ~$0.01/image | Partial — 406 errors in testing |
| Video generation | WaveSpeedAI WAN 2.7 | ~$0.06/video | Good — real cinematic output |
| Postcard design | Pillow + qrcode | $0 | Professional quality |
| Physical mailing | Lob (test mode) | $0 test / $0.80 live | Real postcard delivered |

**Total cost per store (free path): ~$0.06–$0.10**

### Paid Path (production-grade)
| Step | Tool | Cost | Quality |
|------|------|------|---------|
| Store discovery | Google Places API | ~$0.002/store | Best — includes photos, hours, owner |
| AI garment selection | Claude claude-sonnet-5 | ~$0.01/store | Best reasoning |
| Virtual try-on | Replicate IDM-VTON | ~$0.02/image | Excellent — model wearing garment |
| Video generation | Replicate SVD / Kling | ~$0.05/video | Cinematic quality |
| Physical mailing | Lob (live mode) | ~$0.80/postcard | Real tracked mail |

**Total cost per store (paid path): ~$0.90–$1.00**

### What You Lose on the Free Path
- Try-on quality: Without a working try-on, the video shows the garment alone instead of on a model
- Store data richness: OSM has less info than Google (no phone, fewer photos)
- Reliability: Free APIs have rate limits and occasional downtime

### What You Keep on the Free Path
- Everything that matters for the demo: real stores, real AI selection, real video, real mail

---

## Alternatives We Tried and Why They Failed

| Service | What it does | Why it didn't work |
|---------|-------------|-------------------|
| HuggingFace Inference API | Free virtual try-on | DNS blocked by Indian ISPs at routing level |
| fal.ai | Try-on + video | `storage.fal.run` DNS blocked in India; fal.run also blocked |
| Replicate | Try-on + video | Free trial credits exhausted ($0 left) |
| Segmind IDM-VTON | Virtual try-on | 406 errors — payload size / API issue |
| WaveSpeedAI 480p | Video | Invalid resolution value — fixed to 720p |
| Lob "6x4" size | Mailing | Invalid — fixed to "4x6" |
| Lob missing use_type | Mailing | Required field — added `use_type: marketing` |

Every error hit was diagnosed and fixed. The system now routes around failures automatically.

---

## Actual Results Generated

These are real outputs from running the pipeline on Los Angeles stores via OpenStreetMap:

### Store: Image Gear USA (Los Angeles, CA)
- Website scraped: `imagegearusa.com`
- Garment selected by AI: Blue apron (score 9/10 — "bold color, interesting silhouette")
- Video generated: `cinematic_reel.mp4` (5 seconds, WaveSpeedAI WAN 2.7)
- Postcard: Front + back designed with QR code
- Mailing: Sent via Lob API (tracking: `psc_14497c3c83e24fbf`)

---

## How to Run

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # fill in your keys

# Run on any city (free, no cards needed for basic run)
python -m pipeline.run --city "Los Angeles" --source osm --limit 5 --render-method wavespeed

# Skip specific stores
python -m pipeline.run --city "New York" --source osm --limit 3 --render-method wavespeed --exclude "H&M" "Zara"

# Demo mode — no API keys needed, uses sample data
python -m pipeline.run --demo
```

---

## API Keys Needed

| Key | Where to get it | Cost |
|-----|----------------|------|
| `WAVESPEED_API_KEY` | wavespeed.ai — sign up, no card | $1 free credit |
| `GROQ_API_KEY` | console.groq.com | Free tier |
| `LOB_API_KEY` | lob.com — use test key | Free (300 test postcards) |
| `SEGMIND_API_KEY` | segmind.com | Free credits |
| `YELP_API_KEY` | developer.yelp.com | Free 500/day |

Optional (better store data):
- `GOOGLE_MAPS_API_KEY` — Google Cloud Console (free $200/mo credit)
- `REPLICATE_API_TOKEN` — replicate.com (paid credits, best quality)

---

## Project Structure

```
pipeline/
├── config.py          — All env vars and constants
├── run.py             — Main orchestrator (7-step pipeline)
├── discovery.py       — Store finder: OSM / Yelp / Google
├── qualification.py   — Scoring engine (0–100)
├── extraction.py      — Web scraper for clothing images
├── selection.py       — Groq Vision AI garment ranker
├── rendering.py       — Try-on + video: Segmind / WaveSpeedAI / Replicate / fal
├── postcard.py        — Print-ready 4×6 postcard designer
├── mailing.py         — Physical mail via Lob / Stannp
├── models.py          — Pydantic data models
└── utils.py           — Logging, result saving
samples/
└── sample_output/     — Generated postcards, videos, JSON results
```

---

## Tech Stack

- **Python 3.11** — orchestration
- **Pydantic** — typed data models throughout the pipeline
- **BeautifulSoup** — clothing image extraction from websites
- **Pillow + qrcode** — postcard image generation
- **Groq (Llama 4 Scout)** — free vision AI for garment ranking
- **WaveSpeedAI WAN 2.7** — image-to-video generation
- **Segmind IDM-VTON** — virtual try-on (garment on model)
- **Lob API** — physical postcard mailing
- **OpenStreetMap / Nominatim** — store discovery and geocoding (free, no signup)
- **Flask** — web dashboard
