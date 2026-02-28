import requests
from bs4 import BeautifulSoup
import os

# --- CONFIGURATION SECRÈTE ---
# On utilise os.environ pour que GitHub Actions injecte tes clés secrètes sans les afficher dans le code
TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID', 'VOTRE_CLIENT_ID_LOCAL')
TRAKT_ACCESS_TOKEN = os.environ.get('TRAKT_ACCESS_TOKEN', 'VOTRE_ACCESS_TOKEN_LOCAL')
LIST_ID = 'diagonal-montpellier'  # Le slug de votre liste Trakt
USER_ID = 'me'

HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_CLIENT_ID,
    'Authorization': f'Bearer {TRAKT_ACCESS_TOKEN}'
}

def get_diagonal_movies():
    # L'URL secrète que tu as trouvée !
    api_url = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi/movies?basic=false&castingLimit=3&ids=1000001960&ids=1000004467&ids=1000006454&ids=1000007317&ids=1000012006&ids=1000012017&ids=1000014092&ids=1000015619&ids=1000017997&ids=1000019745&ids=1000019912&ids=1000020088&ids=1000020167&ids=1000023006&ids=1000028071&ids=1000030340&ids=1000031821&ids=11674&ids=297924&ids=298832&ids=314229&ids=321789&ids=323925&ids=325655"
    
    web_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0'
    }
    
    try:
        print("🕵️‍♂️ Connexion à l'API secrète du Diagonal...")
        res = requests.get(api_url, headers=web_headers, timeout=10)
        res.raise_for_status()
        
        # La magie de l'API : on transforme directement le résultat en dictionnaire Python
        movies_data = res.json()
        
        titles = []
        for movie in movies_data:
            # Dans cette API, le titre du film se trouve sous l'étiquette 'title'
            titre = movie.get('title')
            if titre:
                titles.append(titre)
        
        return list(set(titles))
        
    except Exception as e:
        print(f"❌ Erreur API: {e}")
        return []
def search_trakt_id(title):
    url = "https://api.trakt.tv/search/movie"
    # L'utilisation de 'params' gère automatiquement les espaces et caractères spéciaux
    params = {'query': title} 
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            return data[0]['movie']['ids'] # On prend le premier résultat
    except Exception as e:
        print(f"Erreur API Trakt pour '{title}': {e}")
    return None

def update_trakt_list():
    print("🎬 Démarrage de la récupération des films du Diagonal...")
    new_movies = get_diagonal_movies()
    print(f"🍿 {len(new_movies)} films trouvés sur le site.")
    
    movie_ids_to_add = []
    
    for title in new_movies:
        ids = search_trakt_id(title)
        if ids:
            movie_ids_to_add.append({"ids": ids})
        else:
            print(f"⚠️ Film non trouvé sur Trakt : {title}")

    if not movie_ids_to_add:
        print("Aucun film à traiter.")
        return

    # Ajout à la liste Trakt (Trakt ignore automatiquement les doublons, donc on garde tout l'historique sans soucis)
    payload = {"movies": movie_ids_to_add}
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items"
    
    try:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        res.raise_for_status()
        result = res.json()
        
        added = result.get('added', {}).get('movies', 0)
        existing = result.get('existing', {}).get('movies', 0)
        print(f"✅ Succès ! {added} nouveaux films ajoutés à la liste, {existing} étaient déjà présents.")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'ajout à la liste Trakt: {e}")

if __name__ == "__main__":
    update_trakt_list()
