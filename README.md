# Clothing Store Outreach Autopilot

Automated system that discovers offline clothing stores, renders their clothes on cinematic model reels, and mails them postcards — on autopilot.

## Pipeline

```
Discovery → Qualification → Extraction → Selection → Rendering → Postcard → Mailing
```

1. **Discovery** — Watches Google Maps for offline clothing stores in a target area
2. **Qualification** — Filters for stores most likely to convert (real store, real inventory, no existing video presence)
3. **Clothing Extraction** — Scrapes clothes from their website or Google listing photos
4. **Best Piece Selection** — AI picks their single strongest garment
5. **Model Rendering** — Puts it on a real model in a cinematic 9:16 reel (Higgsfield)
6. **Postcard Generation** — Creates a print-ready postcard with a reel frame + QR code
7. **Mailing** — Sends it to the store owner by name via Lob/Stannp

## Free Stack

| Component | Tool | Cost |
|-----------|------|------|
| Store discovery | Google Places API | Free $200/mo |
| Web scraping | Playwright + BeautifulSoup | Free |
| AI vision/selection | Claude API | Pay-per-use |
| Virtual try-on | Replicate (IDM-VTON) | Free trial |
| Video generation | Replicate (SVD) / Runway ML / Kling | Free trial |
| Postcard design | Pillow + qrcode | Free |
| Physical mailing | Lob API | Free trial (300 cards) |
| Orchestration | Python | Free |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
python -m pipeline.run --city "Los Angeles" --radius 5000 --category "clothing store"
```

## Project Structure

```
pipeline/
├── config.py          — Central configuration
├── run.py             — Main orchestrator
├── discovery.py       — Google Maps store finder
├── qualification.py   — Store scoring & filtering
├── extraction.py      — Clothing image extraction
├── selection.py       — AI garment ranking
├── rendering.py       — Higgsfield cinematic reel generation
├── postcard.py        — Print-ready postcard with QR
├── mailing.py         — Physical mail via Lob/Stannp
├── models.py          — Data models
└── utils.py           — Shared helpers
samples/
├── sample_output/     — Example outputs for portfolio
templates/
├── postcard_front.py  — Postcard front template
└── postcard_back.py   — Postcard back template
```
