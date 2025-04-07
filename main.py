import requests
import os
import time
from dotenv import load_dotenv
import chess
import chess.engine


#Charger les variables d'environnement depuis un fichier .env
load_dotenv()

# Ton pseudo Chess.com
username = "oleac123"

# Récupérer le token Discord et le webhook URL depuis les variables d'environnement
webhook_url = os.getenv('WEBHOOK_URL')

# URL de l'API pour récupérer les archives de tes parties
url = f"https://api.chess.com/pub/player/{username}/games/archives"

# Fonction pour récupérer les parties en cours
def get_active_game():
    response = requests.get(url)
    if response.status_code == 200:
        archives = response.json()['archives']
        if archives:
            latest_archive_url = archives[-1]  # Prendre la dernière archive
            print(f"Récupération de l'archive à l'URL : {latest_archive_url}")
            games_data = requests.get(latest_archive_url).json()
            for game in games_data['games']:
                if game['status'] == 'in_progress':  # Partie en cours
                    print(f"Partie active trouvée : {game['id']}")
                    return game
    return None

# Fonction pour récupérer l'état de la partie à partir de l'ID
def get_game_state(game_id):
    url = f"https://api.chess.com/pub/game/{game_id}"
    response = requests.get(url)
    return response.json()

# Fonction pour analyser la position avec Stockfish
def analyze_position(board_fen, time_limit=2.0):
    stockfish_path = "path_to_your_stockfish_executable"  # Remplace par le chemin vers ton fichier Stockfish

    # Lancer Stockfish
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        board = chess.Board(board_fen)  # Charger la position FEN de la partie
        result = engine.play(board, chess.engine.Limit(time=time_limit))  # Analyser pendant `time_limit` secondes
        return result.move

# Fonction pour envoyer une notification via Discord
def send_discord_notification(message):
    print(f"Envoi du message: {message}")  # Pour vérifier dans la console
    data = {
        "content": message
    }
    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        print("Notification envoyée avec succès")
    else:
        print(f"Erreur lors de l'envoi de la notification : {response.status_code}")

# Fonction principale pour surveiller les parties actives
def monitor_game():
    previous_game_id = None
    start_time = time.time()  # Temps de début du script
    while True:
        active_game = get_active_game()
        if active_game:
            active_game_id = active_game['id']
            if active_game_id != previous_game_id:
                print(f"Nouvelle partie trouvée : {active_game_id}")
                previous_game_id = active_game_id
            game_state = get_game_state(active_game_id)
            board_fen = game_state['board']['fen']
            white_time = game_state['white']['time_left']
            black_time = game_state['black']['time_left']
            turn = game_state['turn']  # C'est ton tour si 'w' et celui de l'adversaire si 'b'

            print(f"Temps restant pour les blancs: {white_time} secondes")
            print(f"Temps restant pour les noirs: {black_time} secondes")

            # Calculer la quantité de temps restant
            time_limit = 5.0  # Par défaut, on donne 5 secondes pour analyser le coup

            if turn == 'w':  # C'est à ton tour de jouer
                if white_time < 30:  # Si tu as moins de 30 secondes, jouer plus vite
                    time_limit = 1.0
                    print("Tu as moins de 30 secondes, le bot va jouer plus vite.")
                best_move = analyze_position(board_fen, time_limit)
                message = f"Le meilleur coup à jouer est : {best_move}"
                send_discord_notification(message)

            elif turn == 'b':  # C'est l'adversaire qui joue
                if black_time < 30:  # Si l'adversaire a moins de 30 secondes, il peut faire des erreurs
                    time_limit = 1.0  # Plus de temps pour analyser, car on veut capitaliser sur ses erreurs
                    print("L'adversaire a moins de 30 secondes, le bot joue plus vite.")
                best_move = analyze_position(board_fen, time_limit)
                message = f"L'adversaire joue le coup : {best_move}"
                send_discord_notification(message)

        # Vérifie toutes les 5 secondes
        time.sleep(5)

        # Vérifier si la partie a duré plus de 10 minutes (600 secondes)
        elapsed_time = time.time() - start_time
        if elapsed_time > 600:
            print("Le temps de la partie est écoulé.")
            break  # La partie est terminée, on arrête le bot

# Test d'envoi d'une notification pour s'assurer que le webhook Discord fonctionne
print("Test d'envoi d'une notification...")
send_discord_notification("Test de notification du bot Chess.com")

# Lancer la surveillance du jeu
keep_alive()
monitor_game()
