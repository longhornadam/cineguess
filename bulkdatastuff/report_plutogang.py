r"""
Generate a presence report for movies on the PLUTOGANG share.

For each movie folder under \\PLUTOGANG\data\media\movies (override with PLUTOGANG_MOVIES_ROOT),
check whether we have:
- metadata file (any *_metadata.txt)
- poster.jpg under the images root (override with MOVIE_IMAGES_ROOT, default ./movie_images/{tmdb_id})
- screenshot*.jpg under that images folder

Outputs a summary plus the first N missing items per category.
"""

import argparse
import os
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_SHARE_ROOT = Path(os.getenv("PLUTOGANG_MOVIES_ROOT", r"\\PLUTOGANG\data\media\movies"))
IMAGES_ROOT = Path(os.getenv("MOVIE_IMAGES_ROOT", Path(__file__).parent / "movie_images"))


def parse_tmdb_id(meta_path: Path) -> Optional[str]:
    """Try to extract tmdb_id from the metadata file content; fall back to filename."""
    tmdb_id = None
    try:
        with meta_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.lower().startswith("id:"):
                    maybe = line.split(":", 1)[1].strip()
                    if maybe:
                        tmdb_id = maybe
                        break
    except OSError:
        tmdb_id = None

    if not tmdb_id:
        stem = meta_path.stem
        # filename like "33_metadata" -> take leading digits
        digits = "".join(ch for ch in stem if ch.isdigit())
        tmdb_id = digits or None
    return tmdb_id


def find_metadata_file(folder: Path) -> Optional[Path]:
    metas = sorted(folder.glob("*_metadata.txt"))
    return metas[0] if metas else None


def scan_share(share_root: Path) -> List[Dict[str, str]]:
    rows = []
    for entry in sorted(share_root.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = find_metadata_file(entry)
        has_meta = meta_path is not None
        tmdb_id = parse_tmdb_id(meta_path) if meta_path else None

        poster = False
        screenshot_count = 0
        if tmdb_id:
            image_folder = IMAGES_ROOT / tmdb_id
            poster = (image_folder / "poster.jpg").exists()
            screenshot_count = len(list(image_folder.glob("screenshot*.jpg")))

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
    parser = argparse.ArgumentParser(description="Report asset presence for PLUTOGANG movies.")
    parser.add_argument("--limit", type=int, default=25, help="Limit for listing missing items.")
    args = parser.parse_args()

    share_root = DEFAULT_SHARE_ROOT
    if not share_root.exists():
        raise SystemExit(f"Share root not found: {share_root}")

    rows = scan_share(share_root)
    total = len(rows)
    with_meta = sum(1 for r in rows if r["has_metadata"])
    with_poster = sum(1 for r in rows if r["has_poster"])
    with_screens = sum(1 for r in rows if r["screenshot_count"] > 0)

    missing_meta = [r for r in rows if not r["has_metadata"]]
    missing_poster = [r for r in rows if not r["has_poster"]]
    missing_screens = [r for r in rows if r["screenshot_count"] == 0]

    print(f"Share root: {share_root}")
    print(f"Images root: {IMAGES_ROOT}")
    print(f"Total movie folders: {total}")
    print(f"Metadata present: {with_meta} / {total}")
    print(f"Poster present: {with_poster} / {total}")
    print(f"Screenshots present: {with_screens} / {total}")

    def _print_sample(title: str, items: List[Dict[str, str]]):
        if not items:
            print(f"\n{title}: none 🎉")
            return
        print(f"\n{title} (showing up to {args.limit}): {len(items)} missing")
        for r in items[: args.limit]:
            print(f"- {r['folder']} (id: {r['tmdb_id'] or 'unknown'})")

    _print_sample("Missing metadata", missing_meta)
    _print_sample("Missing poster", missing_poster)
    _print_sample("Missing screenshots", missing_screens)


if __name__ == "__main__":
    main()
