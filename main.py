# --- IMPORTS ---
import discord
from discord.ext import commands, tasks
from twitchio.ext import commands as twitch_commands
import requests
import os
import asyncio
import chess
import chess.pgn
import io
from enum import Enum, auto
import re

# --- NOUVEAUX IMPORTS POUR LA CAPTURE VIDÉO ---
import cv2 # Pour la manipulation vidéo (opencv-python)
import numpy as np # Requis par OpenCV
import mss # Pour la capture d'écran rapide
import threading # Pour exécuter l'enregistrement en arrière-plan
import time # Pour contrôler le framerate
import subprocess # Pour lancer ffmpeg

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- STOCKAGE ---
tracked_games = {}  # pour analyse échecs (par salon)
streamer_id_cache = {}
tracked_recordings = {} # NOUVEAU: pour l'enregistrement de l'écran (par salon)

# --- FONCTIONS UTILES ---

def get_live_game_moves(game_id):
    url = f"https://www.chess.com/game/live/{game_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code != 200:
        raise RuntimeError(f"Erreur HTTP {r.status_code} lors de la récupération.")
    text = r.text
    match = re.search(r'"moves":"([^"]+)"', text)
    if not match:
        raise RuntimeError("Impossible de trouver les coups dans la page.")
    moves_str = match.group(1)
    moves = moves_str.split()
    return moves

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

# --- CLASSE BOT TWITCH ---

class WatcherMode(Enum):
    IDLE = auto()
    KEYWORD = auto()
    MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    def __init__(self, discord_bot_instance):
        super().__init__(token=TTV_BOT_TOKEN, prefix='!', initial_channels=[])
        self.discord_bot = discord_bot_instance
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def event_ready(self):
        print(f"Bot Twitch '{TTV_BOT_NICKNAME}' prêt.")

    async def stop_task(self):
        if self.current_channel_name:
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def start_keyword_watch(self, twitch_channel, keyword, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])

    async def start_mirror(self, twitch_channel, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return

        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(
                    title="🚨 Mot-Clé Twitch détecté !",
                    description=message.content,
                    color=discord.Color.orange()
                )
                embed.set_footer(text=f"Chaîne : {message.channel.name} | Auteur : {message.author.name}")
                await self.target_discord_channel.send(embed=embed)

        elif self.mode == WatcherMode.MIRROR:
            msg = f"**{message.author.name}**: {message.content}"
            await self.target_discord_channel.send(msg[:2000])

# --- COMMANDES DISCORD ---

@bot.command(name="chess") # MODIFIÉ
async def start_chess_analysis(ctx, game_id: str):
    channel_id = ctx.channel.id
    if channel_id in tracked_games:
        await ctx.send("⏳ Une analyse est déjà en cours dans ce salon. Utilisez `!stopchess` pour l'arrêter.")
        return

    try:
        get_live_game_moves(game_id)
    except Exception as e:
        await ctx.send(f"❌ Erreur récupération partie : {e}")
        return

    # --- DÉBUT SECTION ENREGISTREMENT VIDÉO ---
    if channel_id in tracked_recordings:
        old_rec = tracked_recordings.pop(channel_id)
        old_rec['stop_event'].set()
        
    raw_video_path = f"raw_{channel_id}.mp4"
    stop_event = threading.Event()
    
    def video_recorder(path, stop_flag):
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Moniteur principal
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(path, fourcc, 2.0, (monitor["width"], monitor["height"])) # 2 FPS
            
            while not stop_flag.is_set():
                img = sct.grab(monitor)
                frame = np.array(img)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                out.write(frame_bgr)
                time.sleep(0.4) # Contrôle la boucle pour ne pas surcharger le CPU
            
            out.release()
            print(f"Enregistrement brut '{path}' terminé.")

    recorder_thread = threading.Thread(target=video_recorder, args=(raw_video_path, stop_event))
    recorder_thread.start()
    
    tracked_recordings[channel_id] = {
        "thread": recorder_thread,
        "stop_event": stop_event,
        "raw_path": raw_video_path
    }
    # --- FIN SECTION ENREGISTREMENT VIDÉO ---

    tracked_games[channel_id] = {"game_id": game_id, "last_ply": 0}
    game_analysis_loop.start(ctx)
    await ctx.send(f"✅ Analyse démarrée pour la partie live `{game_id}`.\n🎥 Enregistrement de l'activité du bot démarré. Utilisez `!cam` pour obtenir la vidéo.")

@bot.command(name="stopchess") # MODIFIÉ
async def stop_chess_analysis(ctx):
    channel_id = ctx.channel.id
    
    if channel_id in tracked_games:
        game_analysis_loop.cancel()
        del tracked_games[channel_id]
        await ctx.send("⏹️ Analyse d'échecs arrêtée.")
    else:
        await ctx.send("Aucune analyse d'échecs active dans ce salon.")

    if channel_id in tracked_recordings:
        rec_data = tracked_recordings.pop(channel_id)
        rec_data['stop_event'].set()
        await asyncio.to_thread(rec_data['thread'].join)
        
        if os.path.exists(rec_data['raw_path']):
            await asyncio.to_thread(os.remove, rec_data['raw_path'])
        
        print(f"Enregistrement arrêté et fichier nettoyé pour le salon {channel_id}.")

# NOUVELLE COMMANDE !cam
@bot.command(name="cam")
async def send_capture(ctx):
    channel_id = ctx.channel.id
    if channel_id not in tracked_recordings:
        await ctx.send("❌ Aucun enregistrement en cours. Lancez une analyse avec `!chess` d'abord.")
        return

    await ctx.send("⏳ Arrêt de l'enregistrement et compression de la vidéo... Ceci peut prendre un moment.")

    rec_data = tracked_recordings[channel_id]
    stop_event, raw_path, thread = rec_data['stop_event'], rec_data['raw_path'], rec_data['thread']
    
    stop_event.set()
    await asyncio.to_thread(thread.join)

    compressed_path = f"compressed_{channel_id}.mp4"

    def compress_video():
        try:
            command = [
                'ffmpeg', '-i', raw_path, '-c:v', 'libx264', 
                '-preset', 'veryfast', '-crf', '30', '-y', compressed_path
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True, None
        except FileNotFoundError:
            return False, "Erreur critique : `ffmpeg` n'est pas installé ou accessible."
        except subprocess.CalledProcessError as e:
            return False, f"Erreur de ffmpeg : `{e.stderr}`"

    success, error = await asyncio.to_thread(compress_video)

    if not success:
        await ctx.send(f"❌ La compression a échoué. {error}")
    else:
        file_size = os.path.getsize(compressed_path)
        if file_size > 8 * 1024 * 1024:
            await ctx.send(f"😥 La vidéo compressée fait **{file_size / 1024 / 1024:.2f} Mo**, dépassant la limite de 8 Mo de Discord.")
        else:
            await ctx.send("✅ Voici la capture vidéo de l'activité du bot :", file=discord.File(compressed_path))
    
    if os.path.exists(raw_path): os.remove(raw_path)
    if os.path.exists(compressed_path): os.remove(compressed_path)
    
    del tracked_recordings[channel_id]


@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
        await ctx.send(f"🔍 Mot-clé **{keyword}** sur **{streamer}** surveillé.")

@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_mirror(streamer, ctx.channel)
        await ctx.send(f"🪞 Miroir du chat de **{streamer}** activé.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_twitch_watch(ctx):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.stop_task()
        await ctx.send("🛑 Surveillance Twitch arrêtée.")

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
        moves = get_live_game_moves(game_id)
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
                    ply_num = i+1
                    await ctx.send(f"**{(ply_num+1)//2}. {move_san}** – {quality} (Eval: {eval_before/100:.2f} ➜ {eval_after/100:.2f})")

        tracked_games[cid]["last_ply"] = current_ply

    except RuntimeError as e:
        await ctx.send(f"⚠️ {e} Analyse arrêtée.")
        tracked_games.pop(cid, None)
        game_analysis_loop.cancel()
    except Exception as e:
        await ctx.send(f"⚠️ Erreur durant l'analyse : {e}")
        tracked_games.pop(cid, None)
        game_analysis_loop.cancel()

# --- ÉVÉNEMENTS ---

@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} !")

# --- LANCEMENT ---

async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())
