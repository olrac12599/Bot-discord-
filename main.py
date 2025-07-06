import subprocess

# Vérifier où Stockfish est installé
stockfish_path = subprocess.getoutput('which stockfish')
if stockfish_path:
    print(f"Stockfish est installé dans : {stockfish_path}")
else:
    print("Stockfish n'est pas installé ou introuvable dans le PATH.")