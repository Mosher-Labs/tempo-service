#!/usr/bin/env python3
"""Look up tempos for a list of tracks via the service and write results.

Input JSON: [{"id": "<spotify id>", "artist": "...", "title": "..."}, ...]
Usage:  python fill_tempos.py tracks.json http://tempo.local:8000 > tempos.json

Output has one entry per track with bpm, readings (half/normal/double) and
"trust" (high/check). Hand the output back to Claude, which saves each tempo to
the Spotify connector with set_track_tempo. Entries with trust=check should be
confirmed by ear before saving.
"""
import json
import sys

import requests


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    tracks = json.load(open(sys.argv[1]))
    base = sys.argv[2].rstrip('/')
    out = []
    # small chunks so a slow iTunes response does not time out one huge request
    for i in range(0, len(tracks), 5):
        r = requests.post(f"{base}/batch", json=tracks[i:i + 5], timeout=600)
        r.raise_for_status()
        out.extend(r.json())
        print(f"{min(i + 5, len(tracks))}/{len(tracks)}", file=sys.stderr)
    json.dump(out, sys.stdout, indent=2)


if __name__ == '__main__':
    main()
