# CineGuess Public Scripts

These scripts are safe to publish. They assume your private assets live outside the repo, for example:

```
/mnt/user/CineGuess/private_data/
  movie_data/          # per-movie folders containing *_metadata.txt, poster.jpg, screenshot_*.jpg
  databases/           # optional: generated movies.json, etc.
```

Environment variables (override defaults):
- `MOVIE_DATA_ROOT` (default `/mnt/user/CineGuess/private_data/movie_data`) — where movie folders live.
- `TMDB_API_KEY` — required for fetching posters/screenshots from TMDB.
- `TMDB_DELAY_SECONDS` — delay between TMDB calls (default 1.0s) to avoid rate limits.

Scripts:
- `report_assets.py` — scan movie folders and report which have metadata, posters, and screenshots.
- `fetch_tmdb_assets.py` — fetch poster and screenshots for movies with metadata but missing assets (uses TMDB).

Usage examples:
```
# Report with first 20 missing items per category
python report_assets.py --limit 20

# Fetch poster + up to 6 screenshots for entries missing assets
python fetch_tmdb_assets.py --mode missing --limit 6 --delay 1.0
```

Notes:
- The scripts never write inside the repo; they operate on `MOVIE_DATA_ROOT`.
- Adjust paths to match your Unraid/Dockge volumes (e.g., bind `/mnt/user/CineGuess/private_data` into the container).
