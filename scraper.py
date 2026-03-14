import os
import time
import json
import requests
from datetime import datetime, date

# ─── Configuration ─────────────────────────────────────────────────────────────
THEATER_ID = "P0187"
BASE_URL = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi"

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TRAKT_CLIENT_ID = os.environ["TRAKT_CLIENT_ID"]
TRAKT_ACCESS_TOKEN = os.environ["TRAKT_ACCESS_TOKEN"]
TRAKT_USERNAME = os.environ["TRAKT_USERNAME"]
TRAKT_LIST_SLUG = os.environ.get("TRAKT_LIST_SLUG", "diagonal-montpellier")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DiagonalScraper/1.0)"})


# ─── 1. Récupérer les IDs des films actuellement à l'affiche ───────────────────

def get_now_playing_ids() -> list[str]:
    """
    Appelle /scheduledMovies et retourne les IDs des films
    qui ont au moins une séance aujourd'hui ou cette semaine.
    """
    url = f"{BASE_URL}/scheduledMovies"
    params = {"theaterId": THEATER_ID}
    resp = SESSION.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    today = date.today().isoformat()  # ex: "2026-03-20"
    scheduled_days = data.get("scheduledDays", {})

    now_playing = []
    for movie_id, days in scheduled_days.items():
        if today in days:
            now_playing.append(movie_id)

    print(f"[*] {len(now_playing)} film(s) à l'affiche aujourd'hui ({today})")
    return now_playing


# ─── 2. Récupérer les titres via /movies?ids= ──────────────────────────────────

def fetch_movie_details(movie_ids: list[str]) -> list[dict]:
    """
    Appelle /movies avec les IDs en paramètres multiples.
    Retourne une liste de dicts avec title, originalTitle, year.
    """
    if not movie_ids:
        return []

    url = f"{BASE_URL}/movies"

    # Les IDs commençant par "c" (ex: "c1488") sont des contenus spéciaux,
    # pas des films → on les filtre car TMDb ne les connaîtra pas
    clean_ids = [mid for mid in movie_ids if not mid.startswith("c")]

    # Construction des paramètres avec ids répétés (comme dans ton URL)
    params = [("basic", "false"), ("castingLimit", "3")]
    for mid in clean_ids:
        params.append(("ids", mid))

    resp = SESSION.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    films = []
    # La réponse est soit une liste, soit un dict {id: {...}}
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = list(data.values())
    else:
        items = []

    for item in items:
        title = (
            item.get("title")
            or item.get("localTitle")
            or item.get("originalTitle")
            or ""
        ).strip()
        original_title = (item.get("originalTitle") or title).strip()

        # Extraire l'année depuis releaseDate (ex: "2026-01-15") ou releaseYear
        year = ""
        release_date = item.get("releaseDate") or item.get("releaseYear") or ""
        if release_date:
            year = str(release_date)[:4]

        if title:
            films.append({
                "id": item.get("id", ""),
                "title": title,
                "original_title": original_title,
                "year": year,
            })
            print(f"  [{item.get('id', '?')}] {title} ({year or '?'})")

    print(f"[*] {len(films)} film(s) avec titre récupérés")
    return films


# ─── 3. Recherche sur TMDb ─────────────────────────────────────────────────────

def search_tmdb(title: str, year: str = "", original_title: str = "") -> dict | None:
    """Recherche un film sur TMDb, retourne son tmdb_id."""
    url = "https://api.themoviedb.org/3/search/movie"

    def _search(query, yr=""):
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "fr-FR"}
        if yr:
            params["primary_release_year"] = yr
        r = SESSION.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("results", [])

    # Tentatives dans l'ordre : titre FR avec année, titre FR sans année,
    # titre original avec année, titre original sans année
    for query, yr in [
        (title, year),
        (title, ""),
        (original_title, year) if original_title != title else (None, None),
        (original_title, "") if original_title != title else (None, None),
    ]:
        if not query:
            continue
        results = _search(query, yr)
        if results:
            best = results[0]
            print(f"    TMDb → '{best['title']}' ({best.get('release_date','')[:4]}) id={best['id']}")
            return {"tmdb_id": best["id"], "title": best["title"]}

    print(f"    [WARN] Non trouvé sur TMDb : '{title}'")
    return None


# ─── 4. Conversion TMDb ID → objet film Trakt ──────────────────────────────────

def tmdb_to_trakt(tmdb_id: int) -> dict | None:
    """Convertit un TMDb ID en objet film Trakt."""
    url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
    }
    params = {"type": "movie"}
    resp = SESSION.get(url, headers=headers, params=params, timeout=10)
    if resp.status_code == 200 and resp.json():
        movie = resp.json()[0]["movie"]
        print(f"    Trakt → '{movie['title']}' (slug: {movie['ids']['slug']})")
        return movie
    print(f"    [WARN] Non trouvé sur Trakt (TMDb id={tmdb_id})")
    return None


# ─── 5. Gestion de la liste Trakt ──────────────────────────────────────────────

def trakt_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
        "Authorization": f"Bearer {TRAKT_ACCESS_TOKEN}",
    }


def ensure_list_exists():
    """Crée la liste Trakt si elle n'existe pas encore."""
    url = f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists"
    resp = SESSION.get(url, headers=trakt_headers(), timeout=10)
    resp.raise_for_status()
    existing_slugs = [lst["ids"]["slug"] for lst in resp.json()]

    if TRAKT_LIST_SLUG not in existing_slugs:
        payload = {
            "name": "Diagonal Montpellier — À l'affiche",
            "description": "Films à l'affiche au cinéma Diagonal de Montpellier. Mis à jour automatiquement chaque jeudi.",
            "privacy": "public",
            "allow_comments": True,
            "display_numbers": False,
        }
        r = SESSION.post(url, headers=trakt_headers(), json=payload, timeout=10)
        r.raise_for_status()
        print(f"[OK] Liste Trakt créée.")
    else:
        print(f"[*] Liste Trakt existante.")


def get_list_movie_slugs() -> list[str]:
    """Retourne les slugs des films déjà dans la liste."""
    url = f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists/{TRAKT_LIST_SLUG}/items/movies"
    resp = SESSION.get(url, headers=trakt_headers(), timeout=10)
    if resp.status_code == 200:
        return [item["movie"]["ids"]["slug"] for item in resp.json()]
    return []


def clear_list(slugs: list[str]):
    """Vide la liste de ses films actuels."""
    if not slugs:
        return
    url = f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists/{TRAKT_LIST_SLUG}/items/remove"
    payload = {"movies": [{"ids": {"slug": s}} for s in slugs]}
    resp = SESSION.post(url, headers=trakt_headers(), json=payload, timeout=10)
    print(f"[*] Liste vidée ({len(slugs)} films supprimés, HTTP {resp.status_code})")


def add_to_list(trakt_movies: list[dict]):
    """Ajoute les films à la liste Trakt."""
    if not trakt_movies:
        print("[!] Aucun film à ajouter.")
        return
    url = f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists/{TRAKT_LIST_SLUG}/items"
    payload = {"movies": [{"ids": m["ids"]} for m in trakt_movies]}
    resp = SESSION.post(url, headers=trakt_headers(), json=payload, timeout=10)
    resp.raise_for_status()
    added = resp.json().get("added", {}).get("movies", 0)
    not_found = resp.json().get("not_found", {}).get("movies", [])
    print(f"[OK] {added} film(s) ajouté(s) à la liste Trakt.")
    if not_found:
        print(f"[!] Non trouvés sur Trakt : {not_found}")


# ─── 6. Pipeline principal ─────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Diagonal Montpellier → Trakt  |", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 55)

    # Étape 1 : IDs des films à l'affiche aujourd'hui
    movie_ids = get_now_playing_ids()
    if not movie_ids:
        print("[!] Aucun film à l'affiche. Fin du script.")
        return

    # Étape 2 : Titres des films
    print("\n[→] Récupération des titres...")
    cinema_films = fetch_movie_details(movie_ids)

    # Étape 3 : Recherche TMDb + Trakt pour chaque film
    trakt_movies = []
    print("\n[→] Recherche TMDb / Trakt...")
    for film in cinema_films:
        print(f"\n  Film : {film['title']} ({film['year'] or '?'})")
        tmdb = search_tmdb(film["title"], film["year"], film["original_title"])
        if tmdb:
            trakt_movie = tmdb_to_trakt(tmdb["tmdb_id"])
            if trakt_movie:
                trakt_movies.append(trakt_movie)
        time.sleep(0.3)  # Respecter les rate limits

    # Étape 4 : Mise à jour de la liste Trakt
    print(f"\n[→] Mise à jour de la liste Trakt ({len(trakt_movies)} films)...")
    ensure_list_exists()
    old_slugs = get_list_movie_slugs()
    clear_list(old_slugs)
    add_to_list(trakt_movies)

    print(f"\n{'=' * 55}")
    print(f"  ✓ Terminé : {len(trakt_movies)}/{len(cinema_films)} films ajoutés")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
```

---

### `requirements.txt`
```
requests==2.32.3
