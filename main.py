import requests
import os
import time
import chess.pgn
import chess.engine

# Ton pseudo Chess.com
username = 'bwbdjdj28288'
webhook_url = os.getenv('WEBHOOK_URL')
stockfish_path = "path_to_your_stockfish_executable"  # Remplace ça

# Récupère l’URL de la dernière archive
def get_latest_game_url():
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    response = requests.get(archives_url)
    if response.status_code == 200:
        last_url = response.json()["archives"][-1]
        return last_url
    return None

# Récupère la dernière partie jouée (terminée)
def get_last_finished_game():
    url = get_latest_game_url()
    if not url:
        return None
    response = requests.get(url)
    if response.status_code == 200:
        games = response.json()["games"]
        for game in reversed(games):
            if game["status"] == "mate" or game["status"] == "resigned" or game["status"] == "timeout":
                return game
    return None

# Analyse les coups avec Stockfish
def analyze_game(pgn_text):
    game = chess.pgn.read_game(pgn_text)
    board = game.board()

    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        for move in game.mainline_moves():
            info = engine.analyse(board, chess.engine.Limit(time=0.5))
            best_move = info["pv"][0]
            if move != best_move:
                msg = f"Erreur détectée : joué {move}, meilleur coup était {best_move}"
                send_discord_notification(msg)
            board.push(move)

# Envoie un message sur Discord
def send_discord_notification(message):
    data = {"content": message}
    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        print("Message envoyé")
    else:
        print(f"Erreur Discord: {response.status_code}")

# Fonction principale
def main():
    game = get_last_finished_game()
    if game:
        pgn_url = game.get("pgn")
        if pgn_url:
            pgn_text = requests.get(pgn_url).text
            from io import StringIO
            analyze_game(StringIO(pgn_text))
    else:
        print("Aucune partie terminée trouvée.")

# Lancer
main()