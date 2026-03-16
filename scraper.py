import os
import time
import requests
from datetime import date

# ─── Configuration ─────────────────────────────────────────────────────────────
THEATER_ID    = "P0187"
BASE_URL      = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi"
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_LIST_ID  = os.environ["TMDB_LIST_ID"]   # ex: "8523061"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DiagonalScraper/1.0)"})


# ─── 1. IDs des films à l'affiche aujourd'hui ──────────────────────────────────

def get_now_playing_ids() -> list[str]:
    today = date.today().isoformat()
    resp = SESSION.get(f"{BASE_URL}/scheduledMovies", params={"theaterId": THEATER_ID}, timeout=15)
    resp.raise_for_status()
    scheduled = resp.json().get("scheduledDays", {})
    ids = [mid for mid, days in scheduled.items()
           if today in days and not mid.startswith("c")]
    print(f"[*] {len(ids)} film(s) à l'affiche le {today}")
    return ids


# ─── 2. Détails des films ──────────────────────────────────────────────────────

def fetch_movie_details(movie_ids: list[str]) -> list[dict]:
    params = [("basic", "false"), ("castingLimit", "3")]
    for mid in movie_ids:
        params.append(("ids", mid))
    resp = SESSION.get(f"{BASE_URL}/movies", params=params, timeout=15)
    resp.raise_for_status()

    films = []
    for item in resp.json():
        title          = item.get("title", "").strip()
        original_title = item.get("originalTitle", title).strip()
        release        = item.get("release", "")
        year           = release[:4] if release else ""
        allocine_id    = (item.get("altId") or [None])[0]
        if title:
            films.append({
                "title": title, "original_title": original_title,
                "year": year,   "allocine_id": allocine_id,
            })
            print(f"  {title} ({year}) — Allociné: {allocine_id}")
    return films


# ─── 3. Recherche TMDb ─────────────────────────────────────────────────────────

def search_tmdb(film: dict) -> int | None:
    """Retourne le TMDb ID du film, en priorité via l'ID Allocine."""

    # Étape 1 : lookup direct par ID Allocine
    if film["allocine_id"]:
        r = SESSION.get(
            f"https://api.themoviedb.org/3/find/{film['allocine_id']}",
            params={"api_key": TMDB_API_KEY, "external_source": "allocine_id"},
            timeout=10,
        )
        results = r.json().get("movie_results", [])
        if results:
            print(f"    TMDb (Allocine✓) → '{results[0]['title']}' id={results[0]['id']}")
            return results[0]["id"]

    # Étape 2 : recherche texte
    for query, yr in [(film["title"], film["year"]), (film["title"], ""),
                      (film["original_title"], film["year"]), (film["original_title"], "")]:
        if not query:
            continue
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "fr-FR"}
        if yr:
            params["primary_release_year"] = yr
        results = SESSION.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params, timeout=10
        ).json().get("results", [])
        if results:
            print(f"    TMDb (titre) → '{results[0]['title']}' id={results[0]['id']}")
            return results[0]["id"]

    print(f"    [WARN] Non trouvé : '{film['title']}'")
    return None


# ─── 4. Gestion de la liste TMDb ───────────────────────────────────────────────

def get_tmdb_session_token() -> str:
    """Authentification TMDb en 3 étapes (token de session v3)."""
    api = "https://api.themoviedb.org/3"
    key = f"?api_key={TMDB_API_KEY}"

    # 1. Request token
    token = SESSION.get(f"{api}/authentication/token/new{key}").json()["request_token"]

    # 2. Valider avec login/password
    SESSION.post(f"{api}/authentication/token/validate_with_login{key}", json={
        "username": os.environ["TMDB_USERNAME"],
        "password": os.environ["TMDB_PASSWORD"],
        "request_token": token,
    }).raise_for_status()

    # 3. Créer session
    session_id = SESSION.post(
        f"{api}/authentication/session/new{key}",
        json={"request_token": token}
    ).json()["session_id"]

    return session_id


def clear_tmdb_list(session_id: str):
    """Vide la liste TMDb."""
    r = SESSION.post(
        f"https://api.themoviedb.org/3/list/{TMDB_LIST_ID}/clear",
        params={"api_key": TMDB_API_KEY, "session_id": session_id, "confirm": True},
        timeout=10,
    )
    print(f"[*] Liste TMDb vidée (HTTP {r.status_code})")


def add_to_tmdb_list(session_id: str, tmdb_ids: list[int]):
    """Ajoute les films à la liste TMDb."""
    url = f"https://api.themoviedb.org/3/list/{TMDB_LIST_ID}/add_item"
    params = {"api_key": TMDB_API_KEY, "session_id": session_id}
    added = 0
    for tmdb_id in tmdb_ids:
        r = SESSION.post(url, params=params, json={"media_id": tmdb_id}, timeout=10)
        if r.status_code in (200, 201):
            added += 1
        time.sleep(0.2)
    print(f"[OK] {added}/{len(tmdb_ids)} films ajoutés à la liste TMDb.")


# ─── 5. Pipeline principal ─────────────────────────────────────────────────────

def main():
    from datetime import datetime
    print("=" * 55)
    print(f"  Diagonal → TMDb  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # Étape 1 : films à l'affiche
    movie_ids = get_now_playing_ids()
    if not movie_ids:
        print("[!] Aucun film. Fin.")
        return

    # Étape 2 : titres
    print("\n[→] Récupération des titres...")
    films = fetch_movie_details(movie_ids)

    # Étape 3 : résolution TMDb
    tmdb_ids = []
    print("\n[→] Recherche TMDb...")
    for film in films:
        print(f"\n  · {film['title']} ({film['year'] or '?'})")
        tmdb_id = search_tmdb(film)
        if tmdb_id:
            tmdb_ids.append(tmdb_id)
        time.sleep(0.25)

    # Étape 4 : mise à jour liste TMDb
    print(f"\n[→] Mise à jour liste TMDb ({len(tmdb_ids)} films)...")
    session_id = get_tmdb_session_token()
    clear_tmdb_list(session_id)
    add_to_tmdb_list(session_id, tmdb_ids)

    print(f"\n{'=' * 55}")
    print(f"  ✓ {len(tmdb_ids)}/{len(films)} films ajoutés")
    print("=" * 55)


if __name__ == "__main__":
    main()
