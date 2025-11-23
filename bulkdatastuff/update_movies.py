import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List

from db_maker import BASE_DIR, process_folder

MOVIES_JSON = Path(__file__).parent / "movies.json"


def load_movies() -> List[dict]:
    """Load existing movies.json if present."""
    if not MOVIES_JSON.exists():
        return []
    try:
        return json.loads(MOVIES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logging.error("Could not parse %s: %s", MOVIES_JSON, exc)
        raise


def write_movies(movies: List[dict]) -> None:
    """Write movies.json with pretty formatting."""
    MOVIES_JSON.write_text(json.dumps(movies, indent=2, ensure_ascii=False), encoding="utf-8")


def count_screenshots(folder: Path) -> int:
    """Count screenshot JPGs in a movie folder."""
    if not folder.exists():
        return 0
    return sum(
        1
        for item in folder.iterdir()
        if item.is_file() and item.name.lower().startswith("screenshot") and item.suffix.lower() == ".jpg"
    )


def sort_movies(movies: List[dict]) -> List[dict]:
    """Sort movies by tmdb_id numerically when possible."""
    def _key(movie: dict):
        try:
            return int(str(movie.get("tmdb_id", "0")))
        except ValueError:
            return movie.get("tmdb_id", "")

    return sorted(movies, key=_key)


def scan_movie_folders(base_dir: Path) -> List[str]:
    """Return list of folder names (tmdb_ids)."""
    return [item.name for item in base_dir.iterdir() if item.is_dir()]


def update_existing_flags(movies_by_id: Dict[str, dict], base_dir: Path) -> int:
    """Refresh poster/screenshot flags (and counts) for movies we already know about."""
    updated = 0
    for tmdb_id, movie in movies_by_id.items():
        folder = base_dir / tmdb_id
        poster_exists = (folder / "poster.jpg").exists()
        screenshot_count = count_screenshots(folder)
        screenshots_exist = screenshot_count > 0

        changed = False
        if movie.get("poster") != poster_exists:
            movie["poster"] = poster_exists
            changed = True
        if movie.get("screenshots") != screenshots_exist:
            movie["screenshots"] = screenshots_exist
            changed = True

        movie["screenshot_count"] = screenshot_count
        if changed:
            updated += 1
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update or report movie metadata.")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Report-only mode: do not write movies.json (still fetches metadata for new folders).",
    )
    parser.add_argument(
        "--list-new",
        action="store_true",
        help="Print tmdb_ids that are new relative to movies.json.",
    )
    parser.add_argument(
        "--list-missing-screens",
        action="store_true",
        help="Print tmdb_ids that currently have no screenshots in their folder.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    base_dir = BASE_DIR
    if not base_dir.exists():
        raise SystemExit(f"Movie images directory not found: {base_dir}")

    existing_movies = load_movies()
    movies_by_id: Dict[str, dict] = {movie.get("tmdb_id"): movie for movie in existing_movies if movie.get("tmdb_id")}

    folder_ids = scan_movie_folders(base_dir)
    new_ids = [tmdb_id for tmdb_id in folder_ids if tmdb_id not in movies_by_id]

    logging.info("Found %s movie folders, %s existing entries, %s new.", len(folder_ids), len(movies_by_id), len(new_ids))

    added = 0
    new_movies: List[dict] = []
    for tmdb_id in new_ids:
        movie = process_folder(base_dir / tmdb_id)
        if movie:
            movies_by_id[tmdb_id] = movie
            new_movies.append(movie)
            added += 1
        else:
            logging.warning("Skipped tmdb_id %s due to fetch/parse error.", tmdb_id)

    refreshed = update_existing_flags(movies_by_id, base_dir)

    all_movies = sort_movies(list(movies_by_id.values()))

    missing_screens = [m.get("tmdb_id") for m in all_movies if m.get("screenshot_count", 0) == 0]

    print(f"Scanned {len(folder_ids)} folders under {base_dir}")
    print(f"Added {added} new movies")
    print(f"Updated poster/screenshot flags for {refreshed} existing entries")
    print(f"Total movies (post-merge, not necessarily written): {len(all_movies)}")

    if args.list_new and new_ids:
        print("\nNew tmdb_ids:")
        for tmdb_id in new_ids:
            print(tmdb_id)

    if args.list_missing_screens and missing_screens:
        print("\nMovies missing screenshots:")
        for tmdb_id in missing_screens:
            print(tmdb_id)

    if not args.report:
        write_movies(all_movies)
        print(f"\nWrote {MOVIES_JSON}")
    else:
        print("\nReport-only mode: movies.json not written.")


if __name__ == "__main__":
    main()
