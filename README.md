# tempo-service

![GitHub branch status](https://img.shields.io/github/checks-status/mosher-labs/tempo-service/main)
![GitHub Issues](https://img.shields.io/github/issues/mosher-labs/tempo-service)
![GitHub last commit](https://img.shields.io/github/last-commit/mosher-labs/tempo-service)
![GitHub License](https://img.shields.io/github/license/mosher-labs/tempo-service)

## Introduction

tempo-service looks up a song's BPM from its artist and title, with no paid
API. It searches the iTunes Search API (free, no key), downloads the 30 second
preview, runs Essentia beat detection on it, and caches the result in SQLite.

It exists to fill the gap in `spotify-mcp`'s tempo lookups. spotify-mcp asks
ReccoBeats first, and tracks ReccoBeats doesn't know need a BPM from
somewhere else. The plan is for spotify-mcp to call this service inside the
cluster on a ReccoBeats miss. That isn't wired up yet.

It runs on the Mosher Labs k3s cluster from
`homelab-gitops/apps/tempo-service`, with a ClusterIP Service and no tunnel.
It has no auth, so it is not exposed outside the cluster.

## Usage

### Run locally

```bash
uv sync
TEMPO_DB=./tempo.db uv run uvicorn app:app --port 8000
```

ffmpeg must be on `PATH`.

### Reach the cluster copy

```bash
kubectl -n tempo-service port-forward svc/tempo-service 8000:8000
```

### Query it

```bash
curl 'http://localhost:8000/bpm?artist=Survivor&title=Eye%20of%20the%20Tiger'
curl 'http://localhost:8000/fits?bpm=75&cadence=150'   # fits at half time
./fill_tempos.py tracks.json http://localhost:8000 > tempos.json
```

`tracks.json` is `[{"id": "<spotify track id>", "artist": "...", "title": "..."}]`.
Hand the output to Claude, which saves each tempo with spotify-mcp's
`set_track_tempo`. Confirm entries marked `trust: check` by ear first.

### Reading the result

- `bpm` is Essentia's `RhythmExtractor2013` (multifeature) estimate.
  `percival_bpm` is an independent second estimate.
- `readings` lists half, normal, and double time. Hip-hop often reads at half
  time, so a 75 BPM reading fits a 150 steps/min cadence. Use `/fits` to
  check.
- `trust: high` means confidence is 3 or more and the two estimators agree,
  allowing for half or double time. `trust: check` means confirm by ear.

### What testing has shown

Tested 2026-11-16 against live iTunes from a Mac:

| Track | bpm | percival_bpm | trust | Published tempo |
| --- | --- | --- | --- | --- |
| Survivor, Eye of the Tiger | 108.9 | 108.8 | high | about 109 |
| Daft Punk, Harder Better Faster Stronger | 123.5 | 123.8 | high | about 123.7 |
| Eminem, Lose Yourself | 172.3 | 86.1 | check | about 86 (171 double) |
| Wiz Khalifa, Camo Shorts | 404 | | | not in the iTunes catalog |

- `RhythmExtractor2013` reports beat periods in whole onset frames (512
  samples at 44.1 kHz), so `bpm` can only be 5168 / n. A 128 BPM click track
  reads as 129.2, and 170 reads as 172.3. Near 128 the steps are about 3 BPM
  apart. `percival_bpm` is not snapped this way. Cadence matching allows 4%,
  so this has not mattered yet.
- The publicly listed tempos above are from memory, not checked against a
  source.

### Limits

- It only analyzes the 30 second preview, so it misses tempo changes later in
  a song.
- iTunes rate-limits hard. The service waits about 3.5 seconds between calls
  (`ITUNES_MIN_GAP_SECONDS`) and caches every result, so a cold lookup takes
  about 7 seconds.
- Songs with no iTunes preview, or whose title doesn't match well enough,
  return 404.
- Run one replica. The rate limiter lives in the process.

## 🔰 Contributing

Upon first clone, install the pre-commit hooks.

```bash
pre-commit install
```

To run pre-commit hooks locally, without a git commit.

```bash
pre-commit run -a --all-files
```

Run the tests with `uv run pytest`. Merging to `main` builds
`ghcr.io/mosher-labs/tempo-service:<short sha>`; update the digest in
`homelab-gitops/apps/tempo-service/application.yaml` to deploy it.
