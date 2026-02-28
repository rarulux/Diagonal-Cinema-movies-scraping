import requests
import os
import re

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
    # 1. On va d'abord sur la page d'accueil pour espionner les IDs de la semaine
    base_url = "https://www.cinediagonal.com/a-laffiche/"
    web_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0'
    }
    
    try:
        print("🔍 Recherche des films de la semaine sur le site...")
        res_html = requests.get(base_url, headers=web_headers, timeout=10)
        res_html.raise_for_status()
        
        # Le scanner magique : il trouve tous les "ids=123456" dans le code caché
        ids_trouves = re.findall(r'ids=(\d+)', res_html.text)
        
        # On enlève les doublons au cas où un film apparaîtrait deux fois
        ids_uniques = list(set(ids_trouves))
        
        if not ids_uniques:
            print("⚠️ Aucun ID trouvé cette semaine.")
            return []
            
        print(f"✅ {len(ids_uniques)} IDs trouvés ! Construction de l'URL secrète...")
        
        # 2. On fabrique notre lien API sur-mesure pour cette semaine
        api_url = "https://www.cinediagonal.com/api/gatsby-source-boxofficeapi/movies?basic=false&castingLimit=3"
        for movie_id in ids_uniques:
            api_url += f"&ids={movie_id}"
            
        # 3. On interroge enfin l'API avec notre beau lien tout neuf !
        print("🕵️‍♂️ Récupération des vrais titres via l'API...")
        res_api = requests.get(api_url, headers=web_headers, timeout=10)
        res_api.raise_for_status()
        movies_data = res_api.json()
        
        titles = []
        for movie in movies_data:
            titre = movie.get('title')
            if titre:
                titles.append(titre)
        
        return list(set(titles))
        
    except Exception as e:
        print(f"❌ Erreur globale: {e}")
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
