# tempo-service - Project Memory

## Project Overview

A small HTTP service that turns artist + title into a BPM: iTunes Search API,
30 second preview, Essentia, SQLite cache. It runs on the Mosher Labs k3s
homelab (`homelab-gitops/apps/tempo-service`) as a ClusterIP Service with no
tunnel, because it has no auth. It is meant to back `spotify-mcp` when
ReccoBeats has no tempo for a track.

The code started as an artifact in a claude.ai chat. The flat layout
(`app.py`, `analyzer.py`, `fill_tempos.py`) is kept so changes can move
between that chat and this repo without restructuring.

**Key Details:**

- **Language:** Python 3.12, FastAPI, managed with `uv`
- **Essentia:** pinned to `2.1b6.dev1389`, the newest build with cp312
  wheels. Later builds ship cp314 wheels only
- **Image:** `ghcr.io/mosher-labs/tempo-service:<short sha>`, built by
  `.github/workflows/image.yml` on push to `main`
- **Data:** `TEMPO_DB` (default `/data/tempo.db`) on a ReadWriteOnce volume

## Working on This Repo

1. Branch from `main`: `git checkout -b feat/description`
1. Run the tests: `uv sync && uv run pytest`
1. Run pre-commit before committing: `pre-commit run --all-files`
1. Commit with Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`)
1. Open a PR. Merging to `main` builds a new image; update the digest in
   `homelab-gitops/apps/tempo-service/application.yaml`

## Constraints

- One replica only: the iTunes rate limiter is in-process.
- `RhythmExtractor2013` snaps BPM to 5168 / n. Don't tighten test tolerances
  below that.
- YAML lines stay under 80 characters (yamllint), outside
  `.github/workflows`.

## References

- @README.md
- Shared workflows: <https://github.com/Mosher-Labs/.github>
