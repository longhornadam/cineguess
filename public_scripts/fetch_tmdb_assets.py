"""
Fetch posters and screenshots from TMDB for movies stored under MOVIE_DATA_ROOT.

Defaults assume Unraid layout:
  MOVIE_DATA_ROOT=/mnt/user/CineGuess/private_data/movie_data

Environment variables:
- MOVIE_DATA_ROOT: root containing per-movie folders.
- TMDB_API_KEY: required.
- TMDB_IMAGE_BASE: default https://image.tmdb.org/t/p/original
- TMDB_DELAY_SECONDS: default 1.0 (delay between TMDB calls).

Example (fill missing assets):
  python fetch_tmdb_assets.py --mode missing --limit 6 --delay 1.0
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

MOVIE_DATA_ROOT = Path(os.getenv("MOVIE_DATA_ROOT", "/mnt/user/CineGuess/private_data/movie_data"))
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
IMAGE_BASE = os.getenv("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p/original")
DEFAULT_DELAY = float(os.getenv("TMDB_DELAY_SECONDS", "1.0"))


def find_metadata_file(folder: Path) -> Optional[Path]:
    metas = sorted(folder.glob("*_metadata.txt"))
    return metas[0] if metas else None


def parse_tmdb_id(meta_path: Path) -> Optional[str]:
    tmdb_id = None
    try:
        with meta_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.lower().startswith("id:"):
                    maybe = line.split(":", 1)[1].strip()
                    if maybe:
                        tmdb_id = maybe
                        break
    except OSError:
        tmdb_id = None
    if not tmdb_id:
        stem = meta_path.stem
        digits = "".join(ch for ch in stem if ch.isdigit())
        tmdb_id = digits or None
    return tmdb_id


def scan(root: Path) -> List[Dict[str, object]]:
    rows = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = find_metadata_file(entry)
        tmdb_id = parse_tmdb_id(meta_path) if meta_path else None
        rows.append(
            {
                "folder": entry,
                "name": entry.name,
                "tmdb_id": tmdb_id,
                "has_meta": meta_path is not None,
                "has_poster": (entry / "poster.jpg").exists(),
                "screenshot_count": len(list(entry.glob("screenshot*.jpg"))),
            }
        )
    return rows


def tmdb_images(tmdb_id: str) -> Dict[str, List[str]]:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/images"
    params = {"api_key": TMDB_API_KEY}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    posters = [p["file_path"] for p in data.get("posters", []) if p.get("file_path")]
    backdrops = [b["file_path"] for b in data.get("backdrops", []) if b.get("file_path")]
    return {"posters": posters, "backdrops": backdrops}


def download_image(file_path: str, dest: Path) -> None:
    url = f"{IMAGE_BASE}{file_path}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def process_movie(row: Dict[str, object], limit: int, overwrite: bool, posters_only: bool, screens_only: bool) -> Dict[str, object]:
    folder: Path = row["folder"]  # type: ignore[assignment]
    tmdb_id: Optional[str] = row["tmdb_id"]  # type: ignore[assignment]
    if not tmdb_id:
        return {"status": "skip", "reason": "no_tmdb_id", "name": row["name"]}

    try:
        assets = tmdb_images(tmdb_id)
    except requests.HTTPError as exc:
        return {"status": "error", "reason": f"http {exc}", "name": row["name"], "tmdb_id": tmdb_id}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": str(exc), "name": row["name"], "tmdb_id": tmdb_id}

    # Posters
    poster_written = False
    if not screens_only:
        poster_exists = (folder / "poster.jpg").exists()
        if overwrite or not poster_exists:
            if assets["posters"]:
                try:
                    download_image(assets["posters"][0], folder / "poster.jpg")
                    poster_written = True
                except Exception as exc:  # noqa: BLE001
                    return {"status": "error", "reason": f"poster_dl {exc}", "name": row["name"], "tmdb_id": tmdb_id}
        else:
            poster_written = False

    # Screenshots
    screenshots_written = 0
    if not posters_only:
        existing = list(folder.glob("screenshot*.jpg"))
        if overwrite or not existing:
            backdrops = assets["backdrops"][:limit]
            for idx, path in enumerate(backdrops, start=1):
                try:
                    download_image(path, folder / f"screenshot_{idx}.jpg")
                    screenshots_written += 1
                except Exception as exc:  # noqa: BLE001
                    return {"status": "error", "reason": f"screen_dl {exc}", "name": row["name"], "tmdb_id": tmdb_id}

    return {
        "status": "ok",
        "name": row["name"],
        "tmdb_id": tmdb_id,
        "poster_written": poster_written,
        "screenshots_written": screenshots_written,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch posters/screenshots from TMDB for local movie folders.")
    parser.add_argument(
        "--mode",
        choices=["missing", "ids"],
        default="missing",
        help="missing = auto-detect missing assets; ids = process explicit tmdb_ids.",
    )
    parser.add_argument("--ids", nargs="*", help="Explicit tmdb_ids to process when --mode ids.")
    parser.add_argument("--limit", type=int, default=6, help="Number of screenshots/backdrops to fetch.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between TMDB requests (seconds).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing poster/screenshots.")
    parser.add_argument("--posters-only", action="store_true", help="Only fetch poster.jpg (skip screenshots).")
    parser.add_argument("--screenshots-only", action="store_true", help="Only fetch screenshots (skip poster).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not TMDB_API_KEY:
        raise SystemExit("TMDB_API_KEY is required.")

    root = MOVIE_DATA_ROOT
    if not root.exists():
        raise SystemExit(f"MOVIE_DATA_ROOT not found: {root}")

    rows = scan(root)
    targets: List[Dict[str, object]] = []
    if args.mode == "missing":
        for row in rows:
            if not row["tmdb_id"]:
                continue
            needs_poster = not row["has_poster"] and not args.screenshots_only
            needs_screens = row["screenshot_count"] == 0 and not args.posters_only
            if needs_poster or needs_screens:
                targets.append(row)
    else:
        ids_set = set(args.ids or [])
        for row in rows:
            if row["tmdb_id"] and row["tmdb_id"] in ids_set:
                targets.append(row)

    print(f"Movie data root: {root}")
    print(f"Targets to process: {len(targets)}")
    if not targets:
        return

    success = 0
    errors = []
    for idx, row in enumerate(targets, start=1):
        result = process_movie(row, limit=args.limit, overwrite=args.overwrite, posters_only=args.posters_only, screens_only=args.screenshots_only)
        if result.get("status") == "ok":
            success += 1
            poster_note = "poster" if result.get("poster_written") else ""
            scr_note = f"{result.get('screenshots_written', 0)} screenshots" if not args.posters_only else ""
            notes = ", ".join([n for n in [poster_note, scr_note] if n])
            print(f"[{idx}/{len(targets)}] {row['name']} ({row['tmdb_id']}): ok {notes}")
        else:
            errors.append(result)
            print(f"[{idx}/{len(targets)}] {row['name']} ({row.get('tmdb_id','?')}): {result.get('reason')}")
        time.sleep(args.delay)

    print(f"\nCompleted. Success: {success} / {len(targets)}. Errors: {len(errors)}")
    if errors:
        print(json.dumps(errors, indent=2))


if __name__ == "__main__":
    main()
