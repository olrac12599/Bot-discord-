
import subprocess

path = subprocess.getoutput('which stockfish')
print(f"Stockfish path: {path}")
