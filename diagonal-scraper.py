import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json

# --- CONFIGURATION ---
TRAKT_CLIENT_ID = 'VOTRE_CLIENT_ID'
TRAKT_ACCESS_TOKEN = 'VOTRE_ACCESS_TOKEN'
LIST_ID = 'diagonal-montpellier'  # Le slug de votre liste Trakt
USER_ID = 'me'

HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_CLIENT_ID,
    'Authorization': f'Bearer {TRAKT_ACCESS_TOKEN}'
}

def get_diagonal_movies():
    url = "https://www.cinediagonal.com/seances/"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    # Extraction des titres (sélecteur à ajuster selon le code source exact)
    titles = [tag.get_text(strip=True) for tag in soup.select('h2 a')]
    return list(set(titles))

def search_trakt_id(title):
    url = f"https://api.trakt.tv/search/movie?query={title}"
    res = requests.get(url, headers=HEADERS)
    data = res.json()
    if data:
        return data[0]['movie']['ids']
    return None

def update_trakt_list():
    # 1. Récupérer les films actuels du Diagonal
    new_movies = get_diagonal_movies()
    movie_ids_to_add = []
    
    for title in new_movies:
        ids = search_trakt_id(title)
        if ids:
            movie_ids_to_add.append({"ids": ids, "added_at": datetime.now().isoformat()})

    # 2. Gérer l'historique (Nettoyage > 3 mois)
    # Note : Trakt ne stocke pas nativement la date d'ajout personnalisée dans les listes simples 
    # pour le filtrage, on peut donc gérer un petit fichier local 'history.json' ou 
    # simplement laisser la liste s'accumuler (Trakt gère les doublons automatiquement).
    
    # Ajout à la liste Trakt
    payload = {"movies": [m for m in movie_ids_to_add]}
    requests.post(f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items", 
                  headers=HEADERS, json=payload)
    print(f"Ajout de {len(movie_ids_to_add)} films terminé.")

if __name__ == "__main__":
    update_trakt_list()
