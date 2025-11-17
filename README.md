News study pipeline
-------------------

This repository contains a small example pipeline to fetch articles from RSS
feeds and Wikipedia pages, extract place names, geocode them and export a
GeoJSON file that can be visualized on a Leaflet/OpenStreetMap web page.

Files added:
- `news_study.py` - main script to fetch feeds/wiki, extract places and geocode
- `feeds.txt` - example RSS feeds (edit to taste)
- `wiki_topics.txt` - example Wikipedia page titles
- `web/map.html` - Leaflet map that reads `web/data/articles.geojson`
- `requirements.txt` - Python dependencies

Basic usage (from project root):

1) Create a virtualenv and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Optional: download spaCy small English model
python -m spacy download en_core_web_sm
```

2) Run the pipeline and generate GeoJSON

```bash
python news_study.py --feeds feeds.txt --wikipedia wiki_topics.txt --out web/data/articles.geojson --limit 5
```

3) Preview the map locally. The simplest way is to serve the `web/` directory:

```bash
cd web
python -m http.server 8000
# then open http://localhost:8000/map.html
```

Notes and limitations
- This is a best-effort prototype. Real-world usage should obey robots.txt and
  the terms of service for each site. Use conservative rate-limiting.
- Geocoding uses Nominatim (OpenStreetMap) and must be used politely. For high
  volume you should run your own instance or use a commercial geocoding API.
- Place extraction uses spaCy if available; otherwise a simple heuristic is used
  which will generate many false positives.

Next steps you might want:
- Add deduplication and clustering of locations
- Save raw articles to a small DB for analysis
- Add topic classification or entity linking
- Visualize counts, timelines or heatmaps on the map
# ai
GEN AI EXPERIMENTS (offline and wikipedia only however connected to hardware!]
MAIN GOAL is to connect ARDUINO ATMEL MEGA 2560 HARDWARE with OFFLINE/ONLINE GEN AI.
python3 ai.py --prompt system.txt --history my_conversation.json
![my-cool-screenshot](https://github.com/htmlfarmer/ai/blob/main/command.png)
![my-cool-screenshot](https://github.com/htmlfarmer/ai/blob/main/serial.png)
![my-cool-screenshot](https://github.com/htmlfarmer/ai/blob/main/hardware.jpg)
![my-cool-screenshot](https://github.com/htmlfarmer/ai/blob/main/Screenshot.png)
