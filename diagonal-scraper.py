import requests
import os
import json
import re

# --- CONFIGURATION ---
TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID', 'VOTRE_CLIENT_ID_LOCAL')
TRAKT_ACCESS_TOKEN = os.environ.get('TRAKT_ACCESS_TOKEN', 'VOTRE_ACCESS_TOKEN_LOCAL')
LIST_ID = 'diagonal-montpellier'
USER_ID = 'me'

TRAKT_HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_CLIENT_ID,
    'Authorization': f'Bearer {TRAKT_ACCESS_TOKEN}'
}

# websiteId extrait du page-data.json
WEBSITE_ID = "V2Vic2l0ZU1hbmFnZXJXZWJzaXRlOmZkOTI0YjY3LTBlNzctNDMwYS1iYzBiLTkyYTliYmU2YTA0Zg=="

def get_diagonal_movies():
    """
    Approche 1 : API GraphQL du CMS Webedia (ciné-manager)
    Visible dans les DevTools > Réseau quand on charge la page d'accueil.
    """
    api_url = "https://www.cinediagonal.com/api/graphql"
    
    # Requête GraphQL pour récupérer les films à l'affiche
    query = """
    query GetMoviesWithShowtimes($websiteId: ID!) {
      moviesWithShowtimes(
        websiteId: $websiteId
        period: CURRENT_PLAYWEEK
      ) {
        movies {
          title
          originalTitle
          releaseDate
        }
      }
    }
    """
    
    # Fallback : requête plus générique
    query_fallback = """
    query {
      movies(websiteId: "%s", dataset: MOVIES_WITH_SHOWTIMES) {
        title
        originalTitle
      }
    }
    """ % WEBSITE_ID
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://www.cinediagonal.com',
        'Referer': 'https://www.cinediagonal.com/a-laffiche/',
    }
    
    try:
        print("🔍 Tentative via API GraphQL...")
        res = requests.post(
            api_url,
            json={"query": query, "variables": {"websiteId": WEBSITE_ID}},
            headers=headers,
            timeout=15
        )
        
        if res.status_code == 200:
            data = res.json()
            print(f"DEBUG GraphQL response: {json.dumps(data)[:500]}")
            
            # Parser la réponse selon la structure reçue
            movies = []
            result = data.get('data', {})
            
            # Chercher les titres dans n'importe quelle clé
            def extract_titles(obj, depth=0):
                if depth > 5:
                    return
                if isinstance(obj, dict):
                    if 'title' in obj and isinstance(obj['title'], str) and len(obj['title']) > 2:
                        movies.append(obj['title'])
                    for v in obj.values():
                        extract_titles(v, depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_titles(item, depth + 1)
            
            extract_titles(result)
            
            if movies:
                print(f"✅ {len(movies)} films via GraphQL")
                return list(set(movies))
        
        print(f"⚠️ GraphQL status: {res.status_code}, fallback sur scraping HTML...")
        
    except Exception as e:
        print(f"⚠️ GraphQL échoué: {e}, passage au fallback...")
    
    # --- FALLBACK : Scraping HTML avec BeautifulSoup ---
    return get_diagonal_movies_html()


def get_diagonal_movies_html():
    """
    Approche 2 (fallback) : Scraping HTML direct de la page.
    Cherche les balises de titres de films dans le HTML rendu côté serveur.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("❌ BeautifulSoup non installé. Lancez : pip install beautifulsoup4")
        return get_diagonal_movies_sitemap()
    
    url = "https://www.cinediagonal.com/a-laffiche/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        print("🔍 Tentative scraping HTML...")
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        titles = []
        
        # Sélecteurs CSS courants pour les titres de films sur ce type de CMS
        selectors = [
            'h2.movie-title', 'h3.movie-title', '.movie-title',
            '[class*="movieTitle"]', '[class*="movie-title"]',
            '[class*="MovieTitle"]', 'h2[itemprop="name"]',
            '.film-title', '[data-testid="movie-title"]',
            'article h2', 'article h3',
        ]
        
        for selector in selectors:
            found = soup.select(selector)
            if found:
                print(f"✅ Sélecteur '{selector}' : {len(found)} titres")
                titles.extend([el.get_text(strip=True) for el in found])
                break
        
        # Si rien trouvé, chercher dans les scripts JSON embarqués
        if not titles:
            print("🔍 Recherche dans les scripts JSON embarqués...")
            for script in soup.find_all('script', type='application/json'):
                try:
                    data = json.loads(script.string)
                    raw = json.dumps(data)
                    # Chercher des patterns de titre de film (pas les labels UI)
                    found = re.findall(r'"title"\s*:\s*"([^"]{4,80})"', raw)
                    # Filtrer les strings qui ressemblent à des labels UI
                    ui_patterns = ['l\'affiche', 'Diagonal', 'Accueil', 'cinéma',
                                   'error', 'label', 'button', 'message', '{', 'loyalty']
                    film_titles = [t for t in found
                                   if not any(p.lower() in t.lower() for p in ui_patterns)]
                    titles.extend(film_titles)
                except Exception:
                    continue
        
        clean = list(set(t for t in titles if t and len(t) > 2))
        if clean:
            print(f"✅ {len(clean)} films via HTML : {', '.join(clean[:5])}...")
            return clean
            
        print("⚠️ HTML scraping n'a rien trouvé non plus, passage au sitemap...")
        return get_diagonal_movies_sitemap()
        
    except Exception as e:
        print(f"❌ Erreur HTML scraping: {e}")
        return get_diagonal_movies_sitemap()


def get_diagonal_movies_sitemap():
    """
    Approche 3 (dernier recours) : Parser le sitemap XML du site.
    Les sites Gatsby publient souvent un sitemap avec toutes les URLs de films.
    """
    urls_to_try = [
        "https://www.cinediagonal.com/sitemap/sitemap-0.xml",
        "https://www.cinediagonal.com/sitemap.xml",
        "https://www.cinediagonal.com/sitemap-index.xml",
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for sitemap_url in urls_to_try:
        try:
            print(f"🔍 Tentative sitemap: {sitemap_url}")
            res = requests.get(sitemap_url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
            
            # Extraire les URLs de films (pattern /films/titre-du-film/)
            film_urls = re.findall(r'<loc>(https://www\.cinediagonal\.com/films/[^<]+)</loc>', res.text)
            
            if not film_urls:
                # Essayer un pattern plus large
                film_urls = re.findall(r'<loc>(https://www\.cinediagonal\.com/film[^<]+)</loc>', res.text)
            
            if film_urls:
                print(f"✅ {len(film_urls)} URLs de films dans le sitemap")
                # Convertir les slugs d'URL en titres lisibles
                titles = []
                for url in film_urls:
                    slug = url.rstrip('/').split('/')[-1]
                    title = slug.replace('-', ' ').title()
                    titles.append(title)
                    print(f"   📽️ {title} (slug: {slug})")
                return titles
                
        except Exception as e:
            print(f"⚠️ {sitemap_url}: {e}")
            continue
    
    print("❌ Aucune méthode n'a fonctionné.")
    print("\n💡 AIDE : Ouvre les DevTools du navigateur (F12) > Onglet Réseau > Filtre 'graphql'")
    print("   Recharge https://www.cinediagonal.com/a-laffiche/ et note l'URL et le body de la requête GraphQL.")
    return []


def search_trakt_id(title):
    """Cherche l'ID Trakt pour un titre de film."""
    url = "https://api.trakt.tv/search/movie"
    params = {'query': title}
    try:
        res = requests.get(url, headers=TRAKT_HEADERS, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            found_title = data[0]['movie']['title']
            score = data[0].get('score', 0)
            print(f"   🎬 '{title}' → '{found_title}' (score: {score})")
            return data[0]['movie']['ids']
    except Exception as e:
        print(f"⚠️ Trakt n'a pas trouvé '{title}': {e}")
    return None


def get_current_list_items():
    """Récupère les IDs des films déjà dans la liste Trakt."""
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items/movies"
    try:
        res = requests.get(url, headers=TRAKT_HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        existing_ids = set()
        for item in data:
            movie = item.get('movie', {})
            ids = movie.get('ids', {})
            if ids.get('trakt'):
                existing_ids.add(ids['trakt'])
        print(f"📋 {len(existing_ids)} films déjà dans la liste Trakt")
        return existing_ids
    except Exception as e:
        print(f"⚠️ Impossible de lire la liste Trakt: {e}")
        return set()


def update_trakt_list():
    print("🎬 Démarrage de la mise à jour...\n")
    
    titles = get_diagonal_movies()
    if not titles:
        print("❌ Aucun film trouvé sur le site. Voir les messages d'aide ci-dessus.")
        return
    
    print(f"\n📽️ Films trouvés sur Diagonal : {titles}\n")
    
    # Récupérer les films déjà dans la liste pour un vrai diff
    existing_trakt_ids = get_current_list_items()
    
    movie_ids_to_add = []
    already_present = 0
    not_found = []
    
    for t in titles:
        ids = search_trakt_id(t)
        if ids:
            trakt_id = ids.get('trakt')
            if trakt_id and trakt_id in existing_trakt_ids:
                already_present += 1
                print(f"   ✓ Déjà présent : {t}")
            else:
                movie_ids_to_add.append({"ids": ids})
        else:
            not_found.append(t)
    
    print(f"\n📊 Résumé :")
    print(f"   - Films trouvés sur le site : {len(titles)}")
    print(f"   - Déjà dans la liste : {already_present}")
    print(f"   - À ajouter : {len(movie_ids_to_add)}")
    print(f"   - Non trouvés sur Trakt : {len(not_found)}")
    if not_found:
        print(f"   - Titres non reconnus : {not_found}")
    
    if not movie_ids_to_add:
        print("\n✅ La liste est déjà à jour !")
        return
    
    # Envoi à Trakt
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items"
    try:
        res = requests.post(url, headers=TRAKT_HEADERS, json={"movies": movie_ids_to_add}, timeout=10)
        res.raise_for_status()
        r = res.json()
        print(f"\n✨ TERMINÉ !")
        print(f"   Nouveaux films ajoutés : {r.get('added', {}).get('movies', 0)}")
        print(f"   Films déjà présents (côté Trakt) : {r.get('existing', {}).get('movies', 0)}")
    except Exception as e:
        print(f"❌ Erreur Trakt : {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Réponse: {e.response.text}")

if __name__ == "__main__":
    update_trakt_list()
