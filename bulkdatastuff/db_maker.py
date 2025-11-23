import os
import json
import time
import requests
from pathlib import Path
import logging
import re

# Setup logging
logging.basicConfig(filename='script.log', level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
# Allow overriding the movie image root (e.g., a mounted network share like \\pluto_gang\...)
MOVIE_IMAGES_ROOT = os.getenv("MOVIE_IMAGES_ROOT")
BASE_DIR = Path(MOVIE_IMAGES_ROOT) if MOVIE_IMAGES_ROOT else Path(__file__).parent / "movie_images"

# Prefer an environment override for the TMDB key to avoid baking secrets in
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "9b5c0efe2a66eb92081b7fb9735ee650")
TMDB_URL = "https://api.themoviedb.org/3/movie/{}?api_key={}&append_to_response=credits"
OUTPUT_FILE = "movies.json"

def get_decade(release_date):
    """Convert release_date (e.g., '1985-07-03') to decade (e.g., '1980s')."""
    try:
        year = int(release_date.split('-')[0])
        decade = (year // 10) * 10
        return f"{decade}s"
    except (ValueError, AttributeError):
        return ""

def format_revenue(revenue):
    """Format revenue as a USD string (e.g., 654264015 -> '$654,264,015')."""
    try:
        return "${:,}".format(int(revenue))
    except (ValueError, TypeError):
        return "$0"

def clean_text(text, names_to_remove):
    """Remove cast, director, and title names from text."""
    if not text or not names_to_remove:
        return text
    pattern = '|'.join(map(re.escape, names_to_remove))
    return re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

def get_movie_initials(title):
    """Convert movie title to initials (e.g., 'Pirates of the Caribbean: Dead Man's Chest' -> 'PotC:DMC')."""
    if not title:
        return ""
    # Split on spaces and certain punctuation, filter out empty strings
    words = [word for word in re.split(r'[ -]', title) if word]
    # Take first letter of each word, handle subtitles with ':'
    initials = ''.join(word[0].upper() for word in words if word[0].isalpha())
    # Reinsert ':' if it was in the original title
    if ':' in title:
        parts = title.split(':')
        return ':'.join(get_movie_initials(part.strip()) for part in parts)
    return initials

def fetch_movie_data(tmdb_id):
    """Fetch movie details from TMDB API."""
    url = TMDB_URL.format(tmdb_id, TMDB_API_KEY)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Get top 6 cast members, sorted by billing order
        cast_list = sorted(data.get("credits", {}).get("cast", []), key=lambda x: x.get("order", float('inf')))
        cast_names = [member["name"] for member in cast_list[:6]]
        
        # Get top director
        crew = data.get("credits", {}).get("crew", [])
        director = next((person["name"] for person in crew if person["job"] == "Director"), "")
        
        # Get top 2 production companies
        prod_companies = [comp["name"] for comp in data.get("production_companies", [])[:2]]

        # Get title
        title = data.get("title", "")

        # Names to remove from tagline and plot
        names_to_remove = cast_names + [director, title]

        # Build movie data
        movie_data = {
            "cast": cast_names,
            "decade": get_decade(data.get("release_date", "")),
            "director": director,
            "genres": [genre["name"] for genre in data.get("genres", [])],
            "original_language": data.get("original_language", ""),
            "plot": clean_text(data.get("overview", ""), names_to_remove),
            "popularity": data.get("popularity", 0.0),
            "production_companies": prod_companies,
            "release_date": data.get("release_date", ""),
            "revenue": format_revenue(data.get("revenue", 0)),
            "tagline": clean_text(data.get("tagline", ""), names_to_remove),
            "title": title,
            "tmdb_id": str(data.get("id", tmdb_id)),
            "vote_average": data.get("vote_average", 0.0),
            "vote_count": data.get("vote_count", 0),
            "movie_initials": get_movie_initials(title),
        }
        return movie_data
    except requests.RequestException as e:
        print(f"Error fetching TMDB data for {tmdb_id}: {e}")
        logging.error(f"TMDB API error for {tmdb_id}: {e}")
        return None

def process_folder(folder_path):
    """Process a single movie folder and return its data."""
    tmdb_id = folder_path.name
    logging.info(f"Processing folder: {tmdb_id}")

    # Check for files
    poster_exists = (folder_path / "poster.jpg").exists()
    screenshots_exist = any(f.startswith("screenshot") and f.endswith(".jpg") 
                           for f in os.listdir(folder_path))
    
    # Delete metadata.txt if it exists
    metadata_file = folder_path / "metadata.txt"
    if metadata_file.exists():
        try:
            metadata_file.unlink()
            logging.info(f"Deleted metadata.txt from {tmdb_id}")
        except OSError as e:
            print(f"Error deleting metadata.txt from {tmdb_id}: {e}")
            logging.error(f"Delete error for {tmdb_id}: {e}")

    # Fetch TMDB data
    movie_data = fetch_movie_data(tmdb_id)
    if not movie_data:
        return None

    # Add local file flags and challenge_id
    movie_data.update({
        "challenge_id": "",
        "poster": poster_exists,
        "screenshots": screenshots_exist
    })
    return movie_data

def main():
    """Main function to process all folders and save to JSON."""
    movies = []
    folder_count = 0

    # Process each subfolder in /movie_images
    for folder in BASE_DIR.iterdir():
        if folder.is_dir():
            movie_data = process_folder(folder)
            if movie_data:
                movies.append(movie_data)
            folder_count += 1
            time.sleep(0.3)  # Rate limit delay

    # Save to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(movies, f, indent=2, ensure_ascii=False)
    
    print(f"Processed {folder_count} folders. Saved {len(movies)} movies to {OUTPUT_FILE}")
    logging.info(f"Completed: Processed {folder_count} folders, saved {len(movies)} movies")

if __name__ == "__main__":
    main()
