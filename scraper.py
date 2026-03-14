import os
import time
import requests
from datetime import date

# ─── Configuration ─────────────────────────────────────────────────────────────
THEATER_ID   = "P0187"
BASE_URL     = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi"

TMDB_API_KEY      = os.environ["TMDB_API_KEY"]
TRAKT_CLIENT_ID   = os.environ["TRAKT_CLIENT_ID"]
TRAKT_ACCESS_TOKEN = os.environ["TRAKT_ACCESS_TOKEN"]
TRAKT_USERNAME    = os.environ["TRAKT_USERNAME"]
TRAKT_LIST_SLUG   = os.environ.get("TRAKT_LIST_SLUG", "diagonal-montpellier")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DiagonalScraper/1.0)"})


# ─── 1. IDs des films à l'affiche aujourd'hui ──────────────────────────────────

def get_now_playing_ids() -> list[str]:
    today = date.today().isoformat()
    resp = SESSION.get(f"{BASE_URL}/scheduledMovies", params={"theaterId": THEATER_ID}, timeout=15)
    resp.raise_for_status()
    scheduled = resp.json().get("scheduledDays", {})

    ids = [mid for mid, days in scheduled.items() if today in days
           and not mid.startswith("c")]  # Exclure les IDs "c1488" (contenus spéciaux)
    print(f"[*] {len(ids)} film(s) à l'affiche le {today}")
    return ids


# ─── 2. Détails des films (titre + altId Allocine) ─────────────────────────────

def fetch_movie_details(movie_ids: list[str]) -> list[dict]:
    params = [("basic", "false"), ("castingLimit", "3")]
    for mid in movie_ids:
        params.append(("ids", mid))

    resp = SESSION.get(f"{BASE_URL}/movies", params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json()  # C'est bien une liste []

    films = []
    for item in items:
        title          = item.get("title", "").strip()
        original_title = item.get("originalTitle", title).strip()
        release        = item.get("release", "")          # "2026-03-11T00:00:00.000Z"
        year           = release[:4] if release else ""
        allocine_id    = item.get("altId", [None])[0]     # ex: "366149"

        if title:
            films.append({
                "id":             item.get("id"),
                "title":          title,
                "original_title": original_title,
                "year":           year,
                "allocine_id":    allocine_id,
            })
            print(f"  [{item.get('id')}] {title} ({year}) — Allociné: {allocine_id}")

    print(f"[*] {len(films)} films récupérés")
    return films


# ─── 3. Recherche TMDb ─────────────────────────────────────────────────────────

def search_tmdb(film: dict) -> dict | None:
    # Étape 1 : via ID Allocine (external_source correct pour TMDb = "allocine_id" ne marche pas)
    # On utilise plutôt la recherche titre + année stricte
    search_url = "https://api.themoviedb.org/3/search/movie"

    def _search(query: str, yr: str = "") -> list:
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "fr-FR"}
        if yr:
            params["primary_release_year"] = yr
        r = SESSION.get(search_url, params=params, timeout=10)
        return r.json().get("results", [])

    def _best_match(results: list, expected_year: str) -> dict | None:
        """Retourne le premier résultat dont l'année correspond, sinon None."""
        for r in results:
            result_year = r.get("release_date", "")[:4]
            if not expected_year or result_year == expected_year:
                return r
        return None

    # Tentatives dans l'ordre, avec vérification d'année stricte
    for query, yr in [
        (film["title"],          film["year"]),
        (film["original_title"], film["year"]),
        (film["title"],          ""),           # fallback sans année
        (film["original_title"], ""),
    ]:
        if not query:
            continue
        results = _search(query, yr)
        match = _best_match(results, film["year"])
        if match:
            print(f"    TMDb → '{match['title']}' ({match.get('release_date','')[:4]}) id={match['id']}")
            return {"tmdb_id": match["id"], "title": match["title"]}

    print(f"    [WARN] Non trouvé sur TMDb : '{film['title']}'")
    return None

# ─── 4. TMDb ID → objet Trakt ──────────────────────────────────────────────────

def tmdb_to_trakt(tmdb_id: int) -> dict | None:
    resp = SESSION.get(
        f"https://api.trakt.tv/search/tmdb/{tmdb_id}",
        headers={
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": TRAKT_CLIENT_ID,
        },
        params={"type": "movie"},
        timeout=10,
    )
    if resp.status_code == 200 and resp.json():
        movie = resp.json()[0]["movie"]
        print(f"    Trakt → '{movie['title']}' slug={movie['ids']['slug']}")
        return movie
    print(f"    [WARN] Non trouvé sur Trakt (tmdb_id={tmdb_id})")
    return None


# ─── 5. Gestion liste Trakt ────────────────────────────────────────────────────

def _th() -> dict:
    """Headers Trakt authentifiés."""
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
        "Authorization": f"Bearer {TRAKT_ACCESS_TOKEN}",
    }

def _list_url(path="") -> str:
    return f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists/{TRAKT_LIST_SLUG}{path}"


def ensure_list_exists():
    r = SESSION.get(f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists", headers=_th(), timeout=10)
    r.raise_for_status()
    if TRAKT_LIST_SLUG not in [l["ids"]["slug"] for l in r.json()]:
        SESSION.post(
            f"https://api.trakt.tv/users/{TRAKT_USERNAME}/lists",
            headers=_th(),
            json={
                "name": "Diagonal Montpellier — À l'affiche",
                "description": "Films à l'affiche au cinéma Diagonal de Montpellier. Mis à jour automatiquement chaque jeudi.",
                "privacy": "public",
            },
            timeout=10,
        ).raise_for_status()
        print("[OK] Liste Trakt créée.")
    else:
        print("[*] Liste Trakt existante.")


def clear_list():
    r = SESSION.get(_list_url("/items/movies"), headers=_th(), timeout=10)
    if r.status_code != 200 or not r.json():
        return
    slugs = [item["movie"]["ids"]["slug"] for item in r.json()]
    SESSION.post(
        _list_url("/items/remove"),
        headers=_th(),
        json={"movies": [{"ids": {"slug": s}} for s in slugs]},
        timeout=10,
    )
    print(f"[*] {len(slugs)} film(s) supprimés de la liste.")


def add_to_list(trakt_movies: list[dict]):
    if not trakt_movies:
        print("[!] Aucun film à ajouter.")
        return
    r = SESSION.post(
        _list_url("/items"),
        headers=_th(),
        json={"movies": [{"ids": m["ids"]} for m in trakt_movies]},
        timeout=10,
    )
    r.raise_for_status()
    added = r.json().get("added", {}).get("movies", 0)
    print(f"[OK] {added} film(s) ajouté(s) à la liste Trakt.")


# ─── 6. Pipeline ───────────────────────────────────────────────────────────────

def main():
    from datetime import datetime
    print("=" * 55)
    print(f"  Diagonal → Trakt  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # Étape 1 : IDs des films à l'affiche
    movie_ids = get_now_playing_ids()
    if not movie_ids:
        print("[!] Aucun film à l'affiche. Fin.")
        return

    # Étape 2 : Titres + Allocine IDs
    print("\n[→] Récupération des titres...")
    films = fetch_movie_details(movie_ids)

    # Étape 3 : Résolution TMDb + Trakt
    trakt_movies = []
    print("\n[→] Recherche TMDb / Trakt...")
    for film in films:
        print(f"\n  · {film['title']} ({film['year'] or '?'})")
        tmdb = search_tmdb(film)
        if tmdb:
            trakt = tmdb_to_trakt(tmdb["tmdb_id"])
            if trakt:
                trakt_movies.append(trakt)
        time.sleep(0.3)

    # Étape 4 : Mise à jour liste Trakt
    print(f"\n[→] Mise à jour liste Trakt ({len(trakt_movies)} films)...")
    ensure_list_exists()
    clear_list()
    add_to_list(trakt_movies)

    print(f"\n{'=' * 55}")
    print(f"  ✓ {len(trakt_movies)}/{len(films)} films ajoutés")
    print("=" * 55)


if __name__ == "__main__":
    main()
