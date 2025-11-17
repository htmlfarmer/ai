#!/usr/bin/env python3
"""
news_study.py

Fetch recent articles from RSS feeds and Wikipedia topics, extract place names,
geocode them and produce a GeoJSON file suitable for display on an OpenStreetMap
frontend (Leaflet). Designed as a starting point — respect robots.txt, rate
limits and site terms of service.

Usage:
  python news_study.py --feeds feeds.txt --wikipedia wiki_topics.txt --out web/data/articles.geojson --limit 10

"""
import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import Counter

import feedparser
import requests
from bs4 import BeautifulSoup

try:
    import spacy
    NLP = spacy.load("en_core_web_sm")
except Exception:
    NLP = None

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import sqlite3
import re
import time as _time


def read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def fetch_rss_items(feeds: List[str], limit_per_feed: int = 5) -> List[Dict]:
    items = []
    for url in feeds:
        try:
            fp = feedparser.parse(url)
            for entry in fp.entries[:limit_per_feed]:
                items.append({
                    "source": url,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                })
        except Exception as e:
            print(f"Failed to parse feed {url}: {e}")
    return items


def fetch_wikipedia_summaries(titles: List[str]) -> List[Dict]:
    out = []
    session = requests.Session()
    # polite user agent to avoid being blocked by API
    session.headers.update({"User-Agent": "news_study_bot/1.0 (+https://github.com/htmlfarmer/ai)"})
    API = "https://en.wikipedia.org/w/api.php"
    for t in titles:
        params = {
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "format": "json",
            "titles": t,
        }
        try:
            r = session.get(API, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            pages = data["query"]["pages"]
            page = next(iter(pages.values()))
            out.append({
                "source": "wikipedia",
                "title": page.get("title", t),
                "link": f"https://en.wikipedia.org/wiki/{t.replace(' ', '_')}",
                "summary": page.get("extract", ""),
            })
        except Exception as e:
            print(f"Failed to fetch wiki {t}: {e}")
        time.sleep(0.5)
    return out


# small stoplist to avoid common words being treated as places
_STOPWORDS = set([w.lower() for w in [
    "and", "but", "it", "the", "a", "an", "one", "lets", "let's",
    "he", "she", "they", "his", "her", "this", "that", "is", "was",
    "in", "on", "at", "by", "for", "from", "with", "as", "of",
    "news", "update", "report",
    # days/months and generic words
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
    "january","february","march","april","may","june","july","august","september","october","november","december",
    "several","many","most","hundreds","thousands","dozens","months","years"
]])

# candidate must include a letter and not be mostly punctuation or digits
_candidate_re = re.compile(r"^[\w\s\-\.'’()]+$")


def clean_place_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    # remove surrounding quotes/brackets
    s = re.sub(r'[\'"`\u2018\u2019\u201c\u201d\(\[]+|[\'"`\u2018\u2019\u201c\u201d\)\]]+$', '', s)
    # remove trailing punctuation
    s = s.rstrip('.,:;!?)\"')
    # remove possessive 's or ’s
    s = re.sub(r"\b's$|’s$", "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def extract_place_names(text: str) -> List[str]:
    if not text:
        return []
    if NLP:
        doc = NLP(text)
        places_raw = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC", "FAC")]
        seen = set(); out = []
        for p in places_raw:
            p2 = clean_place_name(p)
            if not p2:
                continue
            # filter short tokens and obvious stopwords
            if len(p2) < 3 and ' ' not in p2:
                continue
            low = p2.lower()
            if low in _STOPWORDS:
                continue
            # skip short uppercase acronyms (IDF, etc.) unless multiword
            if p2.isupper() and len(p2) <= 3 and ' ' not in p2:
                continue
            if p2 not in seen:
                seen.add(p2); out.append(p2)
        return out
    else:
        # fallback: simple heuristics - capitalized words sequences of length 1-4
        words = BeautifulSoup(text, "html.parser").get_text().split()
        out = []
        i = 0
        while i < len(words):
            w = words[i]
            if w and w[0].isupper():
                j = i
                buf = [w]
                j += 1
                while j < len(words) and words[j] and words[j][0].isupper() and len(buf) < 4:
                    buf.append(words[j]); j += 1
                candidate = clean_place_name(" ".join(buf))
                low = candidate.lower()
                if candidate and low not in _STOPWORDS and (len(candidate) >= 3 or ' ' in candidate) and not (candidate.isupper() and len(candidate) <= 3):
                    out.append(candidate)
                i = j
            else:
                i += 1
        # dedupe
        seen = set(); res = []
        for p in out:
            if p not in seen:
                seen.add(p); res.append(p)
        return res



def _cache_db_path() -> Path:
    d = Path('.cache')
    d.mkdir(exist_ok=True)
    return d / 'geocode_cache.sqlite'


def _init_cache(conn: sqlite3.Connection):
    conn.execute('''CREATE TABLE IF NOT EXISTS geocode (place TEXT PRIMARY KEY, lat REAL, lon REAL, resolved TEXT, ts INTEGER)''')
    conn.commit()


def _get_cached(conn: sqlite3.Connection, place: str) -> Optional[Tuple[float, float, str]]:
    cur = conn.execute('SELECT lat, lon, resolved FROM geocode WHERE place = ?', (place,))
    row = cur.fetchone()
    return (row[0], row[1], row[2]) if row else None


def _set_cached(conn: sqlite3.Connection, place: str, lat: float, lon: float, resolved: str):
    conn.execute('REPLACE INTO geocode(place, lat, lon, resolved, ts) VALUES (?, ?, ?, ?, ?)', (place, lat, lon, resolved, int(_time.time())))
    conn.commit()


def geocode_places(places: List[str], user_agent: str = "news_study_app") -> Dict[str, Tuple[float, float]]:
    geolocator = Nominatim(user_agent=user_agent)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, max_retries=1)
    coords: Dict[str, Tuple[float, float]] = {}

    # open cache
    dbp = _cache_db_path()
    conn = sqlite3.connect(str(dbp))
    _init_cache(conn)

    for p in places:
        p_clean = clean_place_name(p)
        if not p_clean:
            print(f"Skipping empty candidate: '{p}'")
            continue
        # basic filters
        if len(p_clean) < 3 and ' ' not in p_clean:
            print(f"Skipping too-short token: '{p_clean}'")
            continue
        if p_clean.lower() in _STOPWORDS:
            print(f"Skipping stopword candidate: '{p_clean}'")
            continue
        if p_clean.isupper() and len(p_clean) <= 3 and ' ' not in p_clean:
            print(f"Skipping short uppercase acronym: '{p_clean}'")
            continue

        # check cache
        cached = _get_cached(conn, p_clean)
        if cached:
            lat, lon, resolved = cached
            coords[p_clean] = (lat, lon)
            print(f"Cache hit: {p_clean} -> {(lat, lon)} (resolved: {resolved})")
            continue

        # try geocoding with retries/backoff
        attempts = 0
        max_attempts = 3
        backoff = 1.0
        success = False
        while attempts < max_attempts and not success:
            try:
                attempts += 1
                # give geopy a longer read timeout
                loc = geocode(p_clean, exactly_one=True, addressdetails=True, timeout=10)
                if loc:
                    # check that the result looks like a real place; prefer class/type that indicate place
                    raw = getattr(loc, 'raw', {})
                    typ = raw.get('type') or raw.get('class') or ''
                    typ = typ.lower() if isinstance(typ, str) else ''
                    # accept types that are place-like
                    place_like = any(k in typ for k in ('city', 'town', 'village', 'hamlet', 'suburb', 'county', 'state', 'country', 'locality', 'square', 'island', 'borough', 'neighbourhood', 'region'))
                    if place_like or ',' in getattr(loc, 'address', ''):
                        coords[p_clean] = (loc.latitude, loc.longitude)
                        _set_cached(conn, p_clean, loc.latitude, loc.longitude, getattr(loc, 'address', p_clean))
                        print(f"Geocoded: {p_clean} -> {coords[p_clean]} (type={typ})")
                    else:
                        print(f"Rejected geocode (not place-like) for {p_clean}: type={typ} address={getattr(loc,'address', '')}")
                success = True
            except (GeocoderTimedOut, GeocoderUnavailable, requests.exceptions.RequestException) as e:
                print(f"Geocode attempt {attempts} failed for '{p_clean}': {e}")
                if attempts < max_attempts:
                    _time.sleep(backoff)
                    backoff *= 2
                else:
                    print(f"Giving up on geocoding '{p_clean}' after {attempts} attempts")
                    break
            except Exception as e:
                print(f"Geocode error for {p_clean}: {e}")
                break

    conn.close()
    return coords


def article_text_from_summary(summary: str, link: str) -> str:
    # try to fetch full content (best-effort); fall back to summary
    try:
        r = requests.get(link, timeout=8, headers={"User-Agent": "news_study_bot/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # join text blocks
        paragraphs = [p.get_text().strip() for p in soup.find_all("p")]
        text = "\n\n".join([p for p in paragraphs if p])
        return text if len(text) > 200 else summary
    except Exception:
        return summary


def to_geojson(features: List[Dict]) -> Dict:
    return {"type": "FeatureCollection", "features": features}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feeds", default="feeds.txt", help="newline list of RSS feed URLs")
    p.add_argument("--wikipedia", default="wiki_topics.txt", help="newline list of Wikipedia page titles to include")
    p.add_argument("--out", default="web/data/articles.geojson", help="output geojson file")
    p.add_argument("--limit", type=int, default=5, help="items per feed")
    p.add_argument("--max-places", type=int, default=200, help="maximum unique place candidates to geocode (top frequent)")
    args = p.parse_args()

    feeds = read_lines(Path(args.feeds))
    wiki = read_lines(Path(args.wikipedia))

    print(f"Feeds: {len(feeds)} wiki topics: {len(wiki)}")

    rss_items = fetch_rss_items(feeds, limit_per_feed=args.limit)
    wiki_items = fetch_wikipedia_summaries(wiki)

    all_items = rss_items + wiki_items

    # enhance content
    enhanced = []
    for it in all_items:
        text = article_text_from_summary(it.get("summary", ""), it.get("link", ""))
        it["text"] = text
        it["places"] = extract_place_names(text)
        enhanced.append(it)

    # collect unique places
    # count frequencies and select top candidates to avoid excessive geocoding
    counter = Counter()
    for it in enhanced:
        for p in it["places"]:
            counter[p] += 1
    uniques = [p for p, _ in counter.most_common(args.max_places)]

    print(f"Selected {len(uniques)} unique place candidates (top {args.max_places})")
    coords = geocode_places(uniques)

    features = []
    for it in enhanced:
        for p in it["places"]:
            if p in coords:
                lat, lon = coords[p]
                features.append({
                    "type": "Feature",
                    "properties": {
                        "title": it.get("title"),
                        "source": it.get("source"),
                        "link": it.get("link"),
                        "place": p,
                        "summary": (it.get("summary") or "")[:400],
                    },
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    geo = to_geojson(features)
    out_path.write_text(json.dumps(geo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(features)} features to {out_path}")


if __name__ == "__main__":
    main()
