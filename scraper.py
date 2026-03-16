import os
import time
import requests
from datetime import date, datetime

# ─── Configuration ─────────────────────────────────────────────────────────────
THEATER_ID    = "P0187"
BASE_URL      = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi"
TMDB_API_KEY  = os.environ["TMDB_API_KEY"]
TMDB_LIST_ID  = os.environ["TMDB_LIST_ID"]
TMDB_USERNAME = os.environ["TMDB_USERNAME"]
TMDB_PASSWORD = os.environ["TMDB_PASSWORD"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DiagonalScraper/1.0)"})


# ─── 1. IDs des films à l'affiche aujourd'hui ──────────────────────────────────

def get_now_playing_ids() -> list[str]:
    today = date.today().isoformat()
    resp = SESSION.get(
        f"{BASE_URL}/scheduledMovies",
        params={"theaterId": THEATER_ID},
        timeout=15,
    )
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
                "title":          title,
                "original_title": original_title,
                "year":           year,
                "allocine_id":    allocine_id,
            })
            print(f"  {title} ({year}) — Allociné: {allocine_id}")
    print(f"[*] {len(films)} films récupérés")
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
    for query, yr in [
        (film["title"],          film["year"]),
        (film["title"],          ""),
        (film["original_title"], film["year"]),
        (film["original_title"], ""),
    ]:
        if not query:
            continue
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "fr-FR"}
        if yr:
            params["primary_release_year"] = yr
        results = SESSION.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params,
            timeout=10,
        ).json().get("results", [])
        if results:
            print(f"    TMDb (titre) → '{results[0]['title']}' id={results[0]['id']}")
            return results[0]["id"]

    print(f"    [WARN] Non trouvé : '{film['title']}'")
    return None


# ─── 4. Authentification TMDb ──────────────────────────────────────────────────

def get_tmdb_session_token() -> str:
    """Authentification TMDb v3 en 3 étapes."""
    api = "https://api.themoviedb.org/3"
    key = f"?api_key={TMDB_API_KEY}"

    # 1. Request token
    token = SESSION.get(f"{api}/authentication/token/new{key}").json()["request_token"]

    # 2. Valider avec login/password
    SESSION.post(
        f"{api}/authentication/token/validate_with_login{key}",
        json={
            "username": TMDB_USERNAME,
            "password": TMDB_PASSWORD,
            "request_token": token,
        },
    ).raise_for_status()

    # 3. Créer session
    session_id = SESSION.post(
        f"{api}/authentication/session/new{key}",
        json={"request_token": token},
    ).json()["session_id"]

    return session_id


# ─── 5. Gestion de la liste TMDb ───────────────────────────────────────────────

def get_tmdb_list_ids(session_id: str) -> set[int]:
    """Retourne les TMDb IDs déjà dans la liste (toutes pages)."""
    ids = set()
    page = 1
    while True:
        r = SESSION.get(
            f"https://api.themoviedb.org/3/list/{TMDB_LIST_ID}",
            params={"api_key": TMDB_API_KEY, "page": page},
            timeout=10,
        )
        data = r.json()
        for item in data.get("items", []):
            ids.add(item["id"])
        if page >= data.get("total_pages", 1):
            break
        page += 1
    print(f"    [*] {len(ids)} films détectés dans la liste (sur {page} page(s))")
    return ids


def add_to_tmdb_list(session_id: str, tmdb_ids: list[int]):
    """Ajoute uniquement les films pas encore dans la liste."""
    already_in_list = get_tmdb_list_ids(session_id)
    to_add = [tid for tid in tmdb_ids if tid not in already_in_list]

    print(f"[*] {len(already_in_list)} film(s) déjà dans la liste, {len(to_add)} nouveau(x) à ajouter.")

    if not to_add:
        print("[OK] Aucun nouveau film cette semaine.")
        return

    url = f"https://api.themoviedb.org/3/list/{TMDB_LIST_ID}/add_item"
    params = {"api_key": TMDB_API_KEY, "session_id": session_id}
    added = 0
    for tmdb_id in to_add:
        r = SESSION.post(url, params=params, json={"media_id": tmdb_id}, timeout=10)
        print(f"    [{tmdb_id}] HTTP {r.status_code} — {r.json()}")  # ← log détaillé
        if r.status_code in (200, 201):
            added += 1
        time.sleep(0.2)
    print(f"[OK] {added} nouveau(x) film(s) ajouté(s).")


# ─── 6. Pipeline principal ─────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"  Diagonal → TMDb  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # Étape 1 : films à l'affiche aujourd'hui
    movie_ids = get_now_playing_ids()
    if not movie_ids:
        print("[!] Aucun film. Fin.")
        return

    # Étape 2 : titres + IDs Allocine
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

    # Étape 4 : mise à jour liste TMDb (sans doublons)
    print(f"\n[→] Mise à jour liste TMDb ({len(tmdb_ids)} films résolus)...")
    session_id = get_tmdb_session_token()
    add_to_tmdb_list(session_id, tmdb_ids)

    print(f"\n{'=' * 55}")
    print(f"  ✓ Terminé — {len(tmdb_ids)}/{len(films)} films résolus sur TMDb")
    print("=" * 55)


if __name__ == "__main__":
    main()
