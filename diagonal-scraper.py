import os
import json
import re
import requests
from playwright.sync_api import sync_playwright

TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID')
TRAKT_ACCESS_TOKEN = os.environ.get('TRAKT_ACCESS_TOKEN')
LIST_ID = 'diagonal-montpellier'
USER_ID = 'me'

TRAKT_HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_CLIENT_ID,
    'Authorization': f'Bearer {TRAKT_ACCESS_TOKEN}'
}

def get_diagonal_movies():
    print("🔍 Ouverture du navigateur headless...")
    movies = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Intercepter les réponses réseau pour capturer l'appel GraphQL
        graphql_titles = []

        def handle_response(response):
            if "graphql" in response.url and response.status == 200:
                try:
                    body = response.json()
                    raw = json.dumps(body)
                    # Chercher tous les titres dans la réponse GraphQL
                    found = re.findall(r'"title"\s*:\s*"([^"]{2,80})"', raw)
                    graphql_titles.extend(found)
                except Exception:
                    pass

        page.on("response", handle_response)

        print("🌐 Chargement de https://www.cinediagonal.com/a-laffiche/ ...")
        page.goto("https://www.cinediagonal.com/a-laffiche/", wait_until="networkidle", timeout=30000)

        # Attendre que les films soient rendus
        try:
            page.wait_for_selector('[class*="movie"], [class*="film"], article', timeout=10000)
        except Exception:
            pass

        # Méthode 1 : titres capturés via GraphQL intercepté
        if graphql_titles:
            ui_noise = ['affiche', 'Diagonal', 'Accueil', 'cinéma', 'label',
                        'error', 'button', '{', 'loyalty', 'séance', 'Évènement']
            movies = list(set(
                t for t in graphql_titles
                if not any(n.lower() in t.lower() for n in ui_noise) and len(t) > 3
            ))
            print(f"✅ {len(movies)} films via GraphQL intercepté")

        # Méthode 2 : scraping DOM si GraphQL n'a rien donné
        if not movies:
            print("🔍 Fallback : scraping du DOM...")
            selectors = [
                '[class*="movieTitle"]', '[class*="movie-title"]',
                '[class*="MovieTitle"]', '.movie-title',
                'h2', 'h3'
            ]
            for sel in selectors:
                elements = page.query_selector_all(sel)
                titles = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
                if titles:
                    print(f"   Sélecteur '{sel}' → {titles[:5]}")
                    movies = list(set(t for t in titles if len(t) > 3))
                    break

        browser.close()

    if not movies:
        print("❌ Aucun film trouvé. Le site a peut-être changé de structure.")
    else:
        print(f"🎬 Films : {movies}")

    return movies


def search_trakt_id(title):
    url = "https://api.trakt.tv/search/movie"
    try:
        res = requests.get(url, headers=TRAKT_HEADERS, params={'query': title}, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            found = data[0]['movie']['title']
            print(f"   🎬 '{title}' → '{found}'")
            return data[0]['movie']['ids']
    except Exception as e:
        print(f"⚠️ Trakt : '{title}' introuvable ({e})")
    return None


def get_current_list():
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items/movies"
    try:
        res = requests.get(url, headers=TRAKT_HEADERS, timeout=10)
        res.raise_for_status()
        ids = {item['movie']['ids']['trakt'] for item in res.json()}
        print(f"📋 {len(ids)} films déjà dans la liste")
        return ids
    except Exception as e:
        print(f"⚠️ Impossible de lire la liste : {e}")
        return set()


def update_trakt_list():
    print("🚀 Démarrage...\n")

    titles = get_diagonal_movies()
    if not titles:
        return

    existing = get_current_list()

    to_add = []
    for t in titles:
        ids = search_trakt_id(t)
        if ids and ids.get('trakt') not in existing:
            to_add.append({"ids": ids})

    if not to_add:
        print("\n✅ Liste déjà à jour !")
        return

    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items"
    res = requests.post(url, headers=TRAKT_HEADERS, json={"movies": to_add}, timeout=10)
    res.raise_for_status()
    r = res.json()
    print(f"\n✨ Ajoutés : {r.get('added', {}).get('movies', 0)}")


if __name__ == "__main__":
    update_trakt_list()
```

**requirements.txt**
```
requests
playwright
