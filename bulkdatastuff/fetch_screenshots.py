import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

import requests

from db_maker import BASE_DIR, TMDB_API_KEY

IMAGE_BASE = os.getenv("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p/original")
MOVIES_JSON = Path(__file__).parent / "movies.json"


def load_missing_ids() -> List[str]:
    """Load movies.json and return tmdb_ids that have zero screenshots recorded."""
    if not MOVIES_JSON.exists():
        raise SystemExit(f"movies.json not found at {MOVIES_JSON}")

    data = MOVIES_JSON.read_text(encoding="utf-8")
    try:
        movies = json.loads(data)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Could not parse {MOVIES_JSON}: {exc}") from exc

    return [movie.get("tmdb_id") for movie in movies if movie.get("screenshot_count", 0) == 0 and movie.get("tmdb_id")]


def fetch_backdrops(tmdb_id: str, limit: int) -> List[str]:
    """Return a list of backdrop file paths from TMDB."""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/images"
    params = {"api_key": TMDB_API_KEY}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    images = resp.json().get("backdrops", []) or []
    # Sort by vote_average descending, fallback length
    images.sort(key=lambda i: i.get("vote_average", 0), reverse=True)
    paths = [img["file_path"] for img in images if img.get("file_path")]
    return paths[:limit]


def download_image(file_path: str, dest: Path) -> None:
    url = f"{IMAGE_BASE}{file_path}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def ensure_folder(tmdb_id: str) -> Path:
    folder = BASE_DIR / tmdb_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def fetch_for_ids(tmdb_ids: List[str], limit: int, overwrite: bool, delay: float) -> None:
    for tmdb_id in tmdb_ids:
        try:
            folder = ensure_folder(tmdb_id)
            existing = list(folder.glob("screenshot*.jpg"))
            if existing and not overwrite:
                logging.info("Skipping %s (screenshots already present)", tmdb_id)
                continue

            backdrops = fetch_backdrops(tmdb_id, limit)
            if not backdrops:
                logging.warning("No backdrops returned for %s", tmdb_id)
                continue

            for idx, path in enumerate(backdrops, start=1):
                dest = folder / f"screenshot_{idx}.jpg"
                download_image(path, dest)
            logging.info("Saved %s screenshots for %s", len(backdrops), tmdb_id)
            time.sleep(delay)
        except requests.HTTPError as exc:
            logging.error("HTTP error for %s: %s", tmdb_id, exc)
        except Exception as exc:  # noqa: BLE001
            logging.error("Failed %s: %s", tmdb_id, exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch screenshots/backdrops from TMDB for missing movies.")
    parser.add_argument("--ids", nargs="*", help="Explicit tmdb_ids to fetch.")
    parser.add_argument(
        "--missing",
        action="store_true",
        help="Fetch for movies that have zero screenshots according to movies.json.",
    )
    parser.add_argument("--limit", type=int, default=6, help="Number of screenshots to fetch (default 6).")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing screenshot files if present.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between TMDB calls to avoid rate limits (seconds).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    args = parse_args()

    if not TMDB_API_KEY:
        raise SystemExit("TMDB_API_KEY is required (env var).")

    tmdb_ids: List[str] = []
    if args.ids:
        tmdb_ids.extend(args.ids)
    if args.missing:
        tmdb_ids.extend(load_missing_ids())

    if not tmdb_ids:
        raise SystemExit("No tmdb_ids provided. Use --ids or --missing.")

    # De-duplicate while preserving order
    seen = set()
    tmdb_ids_unique = []
    for tmdb_id in tmdb_ids:
        if tmdb_id not in seen:
            seen.add(tmdb_id)
            tmdb_ids_unique.append(tmdb_id)

    fetch_for_ids(tmdb_ids_unique, limit=args.limit, overwrite=args.overwrite, delay=args.delay)


if __name__ == "__main__":
    main()
