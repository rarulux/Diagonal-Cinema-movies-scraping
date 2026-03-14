import requests
import os
import json

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
    """Récupère directement les titres de films depuis le JSON de Gatsby"""
    data_url = "https://www.cinediagonal.com/page-data/a-laffiche/page-data.json"
    web_headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        print("🔍 Lecture de la programmation sur cinediagonal.com...")
        res = requests.get(data_url, headers=web_headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        # On va chercher dans la structure interne de Gatsby
        # On récupère tous les titres mentionnés dans la section "data"
        raw_text = json.dumps(data.get('result', {}).get('data', {}))
        
        import re
        # On cherche tout ce qui suit "title":"..."
        found_titles = re.findall(r'"title":"([^"]+)"', raw_text)
        
        # On filtre les titres techniques du site qui ne sont pas des films
        exclude = ["Diagonal", "Montpellier", "A l'affiche", "Accueil", "Films", "Séances", "Évènements"]
        clean_titles = []
        for t in found_titles:
            if not any(word in t for word in exclude) and len(t) > 3:
                clean_titles.append(t)
        
        final_list = list(set(clean_titles))
        print(f"✅ {len(final_list)} films identifiés : {', '.join(final_list[:5])}...")
        return final_list
        
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du site : {e}")
        return []

def search_trakt_id(title):
    """Cherche l'ID Trakt avec une sécurité sur le titre"""
    url = "https://api.trakt.tv/search/movie"
    params = {'query': title} 
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            # On vérifie si le premier résultat ressemble vraiment au titre
            return data[0]['movie']['ids']
    except Exception as e:
        print(f"⚠️ Trakt n'a pas trouvé '{title}'")
    return None

def update_trakt_list():
    print("🎬 Démarrage de la mise à jour...")
    
    titles = get_diagonal_movies()
    if not titles:
        print("Aucun film trouvé sur le site.")
        return

    movie_ids = []
    for t in titles:
        ids = search_trakt_id(t)
        if ids:
            movie_ids.append({"ids": ids})
            print(f"➕ Ajouté à la file : {t}")

    if not movie_ids:
        print("Aucun film n'a été reconnu par Trakt.")
        return

    # Envoi à Trakt
    url = f"https://api.trakt.tv/users/{USER_ID}/lists/{LIST_ID}/items"
    try:
        res = requests.post(url, headers=HEADERS, json={"movies": movie_ids}, timeout=10)
        res.raise_for_status()
        r = res.json()
        print(f"\n✨ TERMINÉ !")
        print(f"Nouveaux films ajoutés : {r.get('added', {}).get('movies', 0)}")
        print(f"Films déjà présents : {r.get('existing', {}).get('movies', 0)}")
    except Exception as e:
        print(f"❌ Erreur finale Trakt : {e}")

if __name__ == "__main__":
    update_trakt_list()
