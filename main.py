# --- IMPORTS ---
import discord
from discord.ext import commands, tasks
import requests
import os
import asyncio
import chess
import chess.pgn
import io
import re
import time

# --- IMPORTS POUR SELENIUM ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR CRITIQUE: DISCORD_TOKEN, CHESS_USERNAME, ou CHESS_PASSWORD est manquant.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- STOCKAGE ---
tracked_games = {}

# --- FONCTION D'ANALYSE AVEC SELENIUM ---
def get_live_game_moves(game_id):
    """
    Utilise Selenium pour se connecter à chess.com, accepter les cookies,
    et récupérer les coups d'une partie. (Version améliorée)
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)
    # On augmente un peu le temps d'attente maximum à 20 secondes
    wait = WebDriverWait(driver, 20)

    try:
        print("Selenium: Démarrage et navigation vers chess.com...")
        driver.get("https://www.chess.com/login_and_go")

        # Accepter les cookies (méthode plus robuste)
        try:
            print("Selenium: Recherche du bouton de cookies...")
            # On attend juste que le bouton soit cliquable
            cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='onetrust-accept-btn-handler'] | //button[contains(., 'Accept All')]")))
            
            # On utilise un clic JavaScript, plus fiable pour les overlays
            driver.execute_script("arguments[0].click();", cookie_button)
            print("Selenium: Clic JavaScript effectué sur le bouton de cookies.")
            time.sleep(1) # Petite pause pour que l'overlay disparaisse
        except TimeoutException:
            print("Selenium: Pas de pop-up de cookies trouvé ou déjà accepté.")

        # Connexion
        print("Selenium: Entrée des identifiants...")
        # MODIFICATION : On attend que le champ soit VISIBLE avant d'interagir
        username_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
        username_field.send_keys(CHESS_USERNAME)

        password_field = wait.until(EC.visibility_of_element_located((By.ID, "password")))
        password_field.send_keys(CHESS_PASSWORD)
        
        wait.until(EC.element_to_be_clickable((By.ID, "login"))).click()
        print("Selenium: Connexion effectuée.")

        # On attend la confirmation de connexion en cherchant un élément de la page principale
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".home-user-info, .nav-menu-area")))
        print("Selenium: Page principale après connexion détectée.")

        # Navigation vers la partie
        game_url = f"https://www.chess.com/game/live/{game_id}"
        print(f"Selenium: Navigation vers la partie : {game_url}")
        driver.get(game_url)
        time.sleep(5)

        # Récupération des coups
        print("Selenium: Récupération du code source de la page...")
        page_source = driver.page_source
        match = re.search(r'"moves":"([^"]+)"', page_source)
        
        if not match:
            return None, page_source

        moves_str = match.group(1)
        moves = moves_str.split()
        return moves, None

    finally:
        print("Selenium: Fermeture du navigateur.")
        driver.quit()


def get_lichess_evaluation(fen):
    url = f"https://lichess.org/api/cloud-eval?fen={fen}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        if 'pvs' in data and data['pvs']:
            pvs0 = data['pvs'][0]
            if 'cp' in pvs0:
                return pvs0['cp']
            elif 'mate' in pvs0:
                return 10000 if pvs0['mate'] > 0 else -10000
        return None
    except Exception:
        return None

def classify_move(eval_before, eval_after, turn):
    if turn == chess.BLACK:
        eval_before = -eval_before
        eval_after = -eval_after
    loss = eval_before - eval_after
    if loss >= 300: return "🤯 Gaffe monumentale"
    if loss >= 150: return "⁉️ Gaffe"
    if loss >= 70: return "❓ Erreur"
    if loss >= 30: return "🤔 Imprécision"
    return None

# --- COMMANDES DISCORD ---

@bot.command(name="chess")
async def start_chess_analysis(ctx, game_id: str):
    if ctx.channel.id in tracked_games:
        await ctx.send("⏳ Une analyse est déjà en cours dans ce salon. Utilisez `!stopchess` pour l'arrêter.")
        return

    await ctx.send(f"🕵️‍♂️ Lancement de l'analyse avec Selenium pour la partie `{game_id}`... (Ceci peut prendre 30-60 secondes)")
    
    try:
        # On exécute la fonction Selenium (qui est bloquante) dans un thread séparé
        moves, debug_html = await asyncio.to_thread(get_live_game_moves, game_id)

        if moves is None:
            await ctx.send(f"❌ Erreur : Impossible de trouver les coups dans la page après connexion.")
            if debug_html:
                await ctx.send(" Mise en ligne de la page de débogage...")
                try:
                    payload = {'content': debug_html}
                    post_response = requests.post("https://dpaste.com/api/", data=payload, timeout=10)
                    post_response.raise_for_status()
                    paste_url = post_response.text
                    await ctx.send(f"🔗 **Voici un lien vers la page que j'ai vue :**\n{paste_url}")
                except Exception as e:
                    await ctx.send(f"😥 Je n'ai pas réussi à mettre la page en ligne. Erreur : {e}")
            return

        tracked_games[ctx.channel.id] = {"game_id": game_id, "last_ply": 0}
        game_analysis_loop.start(ctx)
        await ctx.send("✅ Analyse Selenium démarrée avec succès !")

    except Exception as e:
        await ctx.send(f"❌ Une erreur critique est survenue avec Selenium : **{e}**")


@bot.command(name="stopchess")
async def stop_chess_analysis(ctx):
    if ctx.channel.id in tracked_games:
        game_analysis_loop.cancel()
        del tracked_games[ctx.channel.id]
        await ctx.send("⏹️ Analyse arrêtée.")
    else:
        await ctx.send("Aucune analyse active dans ce salon.")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

# --- TÂCHE D'ANALYSE ÉCHECS ---

@tasks.loop(seconds=15)
async def game_analysis_loop(ctx):
    cid = ctx.channel.id
    if cid not in tracked_games:
        game_analysis_loop.cancel()
        return
    
    game_id = tracked_games[cid]["game_id"]
    try:
        moves, _ = await asyncio.to_thread(get_live_game_moves, game_id)
        if moves is None:
            await ctx.send(f"⚠️ La partie `{game_id}` n'est plus accessible (session peut-être expirée). Analyse arrêtée.")
            if cid in tracked_games:
                del tracked_games[cid]
            game_analysis_loop.cancel()
            return
            
        board = chess.Board()
        last_ply = tracked_games[cid]["last_ply"]
        current_ply = len(moves)

        for i in range(last_ply, current_ply):
            move_san = moves[i]
            try:
                move = board.parse_san(move_san)
            except Exception:
                break
            fen_before = board.fen()
            turn = board.turn
            board.push(move)
            eval_before = get_lichess_evaluation(fen_before)
            eval_after = get_lichess_evaluation(board.fen())

            if eval_before is not None and eval_after is not None:
                quality = classify_move(eval_before, eval_after, turn)
                if quality:
                    await ctx.send(f"**{(i+1+1)//2}. {move_san}** – {quality} (Eval: {eval_before/100:.2f} ➜ {eval_after/100:.2f})")
        
        tracked_games[cid]["last_ply"] = current_ply
    except Exception as e:
        await ctx.send(f"⚠️ Erreur durant l'analyse : {e}")
        if cid in tracked_games:
            del tracked_games[cid]
        game_analysis_loop.cancel()

# --- ÉVÉNEMENTS ---
@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} !")

# --- LANCEMENT ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

