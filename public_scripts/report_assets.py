"""
Scan movie folders and report presence of metadata, poster, and screenshots.

Defaults assume Unraid layout:
  MOVIE_DATA_ROOT=/mnt/user/CineGuess/private_data/movie_data

Environment variables:
- MOVIE_DATA_ROOT: root containing per-movie folders.

Example:
  python report_assets.py --limit 20
"""

import argparse
import os
from pathlib import Path
from typing import Dict, List, Optional

MOVIE_DATA_ROOT = Path(os.getenv("MOVIE_DATA_ROOT", "/mnt/user/CineGuess/private_data/movie_data"))


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


def scan(root: Path) -> List[Dict[str, str]]:
    rows = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = find_metadata_file(entry)
        has_meta = meta_path is not None
        tmdb_id = parse_tmdb_id(meta_path) if meta_path else None

        poster = (entry / "poster.jpg").exists()
        screenshot_count = len(list(entry.glob("screenshot*.jpg")))

        rows.append(
            {
                "folder": entry.name,
                "tmdb_id": tmdb_id or "",
                "has_metadata": has_meta,
                "has_poster": poster,
                "screenshot_count": screenshot_count,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Report asset presence in movie_data root.")
    parser.add_argument("--limit", type=int, default=25, help="How many missing items to list.")
    args = parser.parse_args()

    root = MOVIE_DATA_ROOT
    if not root.exists():
        raise SystemExit(f"MOVIE_DATA_ROOT not found: {root}")

    rows = scan(root)
    total = len(rows)
    with_meta = sum(1 for r in rows if r["has_metadata"])
    with_poster = sum(1 for r in rows if r["has_poster"])
    with_screens = sum(1 for r in rows if r["screenshot_count"] > 0)

    missing_meta = [r for r in rows if not r["has_metadata"]]
    missing_poster = [r for r in rows if not r["has_poster"]]
    missing_screens = [r for r in rows if r["screenshot_count"] == 0]

    print(f"Movie data root: {root}")
    print(f"Total movie folders: {total}")
    print(f"Metadata present: {with_meta} / {total}")
    print(f"Poster present: {with_poster} / {total}")
    print(f"Screenshots present: {with_screens} / {total}")

    def _sample(title: str, items: List[Dict[str, str]]):
        if not items:
            print(f"\n{title}: none 🎉")
            return
        print(f"\n{title} (showing up to {args.limit}): {len(items)} missing")
        for r in items[: args.limit]:
            print(f"- {r['folder']} (id: {r['tmdb_id'] or 'unknown'})")

    _sample("Missing metadata", missing_meta)
    _sample("Missing poster", missing_poster)
    _sample("Missing screenshots", missing_screens)


if __name__ == "__main__":
    main()
