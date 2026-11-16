"""Self-hosted tempo lookup: artist + title -> BPM.

Flow: iTunes Search API (free, no key) -> 30 s preview -> Essentia -> SQLite cache.
"""
import difflib
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import analyzer

DB_PATH = os.environ.get('TEMPO_DB', '/data/tempo.db')
MIN_GAP = float(os.environ.get('ITUNES_MIN_GAP_SECONDS', '3.5'))  # iTunes rate-limits hard
ITUNES = 'https://itunes.apple.com/search'

app = FastAPI(title='tempo-service')
_lock = threading.Lock()
_last_call = 0.0


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tempo (
             key TEXT PRIMARY KEY, artist TEXT, title TEXT, matched TEXT,
             bpm REAL, percival_bpm REAL, confidence REAL, ts INTEGER)""")
    return conn


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r'\(.*?\)|\[.*?\]', ' ', s)      # drop (feat. x), [explicit]
    s = re.sub(r'\b(feat|ft|featuring)\b.*', ' ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def throttle():
    global _last_call
    with _lock:
        wait = MIN_GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def itunes_get(url, **kw):
    for attempt in range(4):
        throttle()
        r = requests.get(url, timeout=20, **kw)
        if r.status_code in (403, 429):
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r
    raise HTTPException(503, 'iTunes is rate-limiting; retry later')


def find_preview(artist: str, title: str):
    r = itunes_get(ITUNES, params={'term': f"{artist} {title}", 'media': 'music',
                                   'entity': 'song', 'limit': 10})
    want_t, want_a = norm(title), norm(artist.split(',')[0])
    best, best_score = None, 0.0
    for hit in r.json().get('results', []):
        if not hit.get('previewUrl'):
            continue
        t = difflib.SequenceMatcher(None, want_t, norm(hit['trackName'])).ratio()
        a = difflib.SequenceMatcher(None, want_a, norm(hit['artistName'])).ratio()
        score = 0.7 * t + 0.3 * a
        if score > best_score:
            best, best_score = hit, score
    if not best or best_score < 0.75:
        return None
    return best


def compute(artist: str, title: str) -> dict:
    hit = find_preview(artist, title)
    if not hit:
        raise HTTPException(404, 'no iTunes preview found for that track')
    audio = itunes_get(hit['previewUrl']).content
    with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as f:
        f.write(audio)
        src = f.name
    wav = None
    try:
        wav = analyzer.to_wav(src)
        res = analyzer.analyze_wav(wav)
    except subprocess.CalledProcessError:
        raise HTTPException(422, 'ffmpeg could not decode the iTunes preview')
    finally:
        os.remove(src)
        if wav:
            os.remove(wav)
    res['matched'] = f'{hit["artistName"]} - {hit["trackName"]}'
    return res


class Track(BaseModel):
    artist: str
    title: str
    id: Optional[str] = None   # your Spotify track id, echoed back


def lookup(t: Track, refresh=False) -> dict:
    key = f"{norm(t.artist.split(',')[0])}|{norm(t.title)}"
    if not refresh:
        with closing(db()) as conn:
            row = conn.execute('SELECT matched,bpm,percival_bpm,confidence FROM tempo WHERE key=?',
                               (key,)).fetchone()
        if row:
            return shape(t, *row, cached=True)
    # computed outside the connection: a lookup can take ~10 s of iTunes waits
    res = compute(t.artist, t.title)
    with closing(db()) as conn:
        conn.execute('INSERT OR REPLACE INTO tempo VALUES (?,?,?,?,?,?,?,?)',
                     (key, t.artist, t.title, res['matched'], res['bpm'],
                      res['percival_bpm'], res['confidence'], int(time.time())))
        conn.commit()
    return shape(t, res['matched'], res['bpm'], res['percival_bpm'], res['confidence'], False)


def shape(t, matched, bpm, percival, conf, cached):
    agree = abs(bpm - percival) <= bpm * 0.04 or \
        any(abs(c - percival) <= percival * 0.04 for c in analyzer.candidates(bpm))
    return {'id': t.id, 'artist': t.artist, 'title': t.title, 'matched': matched,
            'bpm': bpm, 'percival_bpm': percival, 'confidence': conf,
            'readings': analyzer.candidates(bpm),
            'trust': 'high' if (conf >= 3 and agree) else 'check',
            'cached': cached}


@app.get('/healthz')
def healthz():
    return {'ok': True}


@app.get('/bpm')
def bpm(artist: str, title: str, refresh: bool = False):
    return lookup(Track(artist=artist, title=title), refresh)


@app.post('/batch')
def batch(tracks: List[Track]):
    out = []
    for t in tracks:
        try:
            out.append(lookup(t))
        except HTTPException as e:
            out.append({'id': t.id, 'artist': t.artist, 'title': t.title, 'error': e.detail})
        except requests.RequestException as e:
            # one network failure should not throw away the rest of the batch
            out.append({'id': t.id, 'artist': t.artist, 'title': t.title,
                        'error': f"iTunes request failed: {type(e).__name__}"})
    return out


@app.get('/fits')
def fits(bpm: float, cadence: float, tol: float = 0.04):
    """Does a song at `bpm` fit a running cadence (steps/min), allowing half/double time?"""
    return {'fits': analyzer.fits_cadence(bpm, cadence, tol), 'readings': analyzer.candidates(bpm)}
