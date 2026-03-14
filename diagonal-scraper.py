import requests
import os
import re

# --- CONFIGURATION SECRÈTE ---
TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID', 'VOTRE_CLIENT_ID_LOCAL')
TRAKT_ACCESS_TOKEN = os.environ.get('TRAKT_ACCESS_TOKEN', 'VOTRE_ACCESS_TOKEN_LOCAL')
LIST_ID = 'diagonal-montpellier'
USER_ID = 'me'

HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_CLIENT_ID,
    'Authorization': f'Bearer {TRAKT_ACCESS_TOKEN}'
}

def get_diagonal_movies():
    """Récupère dynamiquement les IDs et les titres des films de la semaine"""
    # 1. On va chercher le "cerveau" de la page pour trouver les IDs actuels
    data_url = "https://www.cinediagonal.com/page-data/a-laffiche/page-data.json"
    web_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    
    try:
        print("🔍 Recherche des IDs de films sur le site...")
        res_data = requests.get(data_url, headers=web_headers, timeout=10)
        res_data.raise_for_status()
        
        # On extrait tous les IDs (nombres de 4 à 10 chiffres)
        ids_uniques = list(set(re.findall(r'(\d{4,10})', res_data.text)))
        
        if not ids_uniques:
            print("⚠️ Aucun ID trouvé dynamiquement.")
            return []

        # 2. On construit l'URL de l'API avec ces nouveaux IDs
        api_url = f"https://www.cinediagonal.com/api/gatsby-source-boxofficeapi/movies?basic=false&castingLimit=3&ids={'&ids='.join(ids_uniques)}"
            
        print("🕵️‍♂️ Récupération des titres via l'API...")
        res_api = requests.get(api_url, headers=web_headers, timeout=10)
        res_api.raise_for_status()
        movies_data = res_api.json()
        
        titles = [movie.get('title') for movie in movies_data if movie.get('title')]
        print(f"✅ {len(titles)} films trouvés sur le site.")
        return list(set(titles))
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping : {e}")
        return []

def search_trakt_id(title):
    """Cherche l'ID Trakt d'un film en nettoyant le titre pour plus de précision"""
    url = "https://api.trakt.tv/search/movie"
    # On nettoie le titre (minuscules et sans espaces inutiles)
    clean_title = title.lower().strip()
    params = {'query': clean_title} 
    
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            # On cherche une correspondance exacte dans les résultats pour éviter les erreurs
            for result in data:
                if result['movie']['title'].lower() == clean_title:
                    return result['movie']['ids']
            # Si pas de correspondance exacte, on prend le premier résultat
            return data[0]['movie']['ids']
    except Exception as e:
        print(f"⚠️ Erreur API Trakt pour '{title}': {e}")
    return None

def update_trakt_list():
    print("🎬 Démarrage de la mise à jour Diagonal -> Trakt...")
    
    # Récupération des films sur le site
    new_movies_titles = get_diagonal_movies()
    
    if not new_movies_titles:
        print("Fin du script : Aucun film trouvé.")
        return

    # Conversion des titres en IDs Trakt
    movie_ids_to_add = []
    for title in new_movies_titles:
        ids = search_trakt_id(title)
        if ids:
            movie_ids_to_add.append({"ids": ids})
        else:
            print(f"❌ Film non trouvé sur Trakt : {title}")

    if not movie_ids_to_add:
        print("Aucun ID de film n'a pu être récupéré.")
        return

    # Envoi massif à Trakt
    payload = {"movies": movie_ids_to_add}
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items"
    
    try:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        res.raise_for_status()
        result = res.json()
        
        added = result.get('added', {}).get('movies', 0)
        existing = result.get('existing', {}).get('movies', 0)
        not_found = result.get('not_found', {}).get('movies', [])
        
        print(f"--- RÉSULTAT ---")
        print(f"✨ Nouveaux films ajoutés : {added}")
        print(f"🔄 Films déjà présents : {existing}")
        if not_found:
             print(f"❓ Films non reconnus par Trakt : {len(not_found)}")
        print(f"----------------")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'ajout à la liste Trakt : {e}")

if __name__ == "__main__":
    update_trakt_list()
