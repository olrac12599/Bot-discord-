import discord
from discord.ext import commands
import os
import asyncio

from pathlib import Path
from your_scraping_module import get_pgn_from_chess_com, ScrapingError  # adapte selon ton fichier
import io

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo

videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)
last_video_paths = {}

# --- INIT BOT ---
intents = discord.Intents.default()
intents.message_content = True  # ⚠️ Nécessaire pour que le bot lise les messages

bot = commands.Bot(command_prefix="!", intents=intents)

# --- COMMANDES ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    msg = await ctx.send("🕵️ **Lancement du scraping en mode furtif...** Connexion à Chess.com.")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        if video_path:
            last_video_paths[ctx.channel.id] = video_path
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré !**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo de l'opération.*")
    except ScrapingError as e:
        await msg.edit(content=f"❌ **Erreur de scraping.**")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
        files = [discord.File(io.BytesIO(e.screenshot_bytes), "debug.png")] if e.screenshot_bytes else []
        await ctx.send(f"**Erreur :** {e}", files=files)
        if e.video_path:
            await ctx.send(f"Utilisez `!cam` pour voir la vidéo de la session qui a échoué.")
    except Exception as e:
        await msg.edit(content=f"❌ Erreur système: {e}")

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path_str = last_video_paths.get(ctx.channel.id)
    if not video_path_str:
        return await ctx.send("❌ Aucune vidéo récente trouvée.")
    video_file = Path(video_path_str)
    if not video_file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la dernière opération `!chess` :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📹 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}.")

# --- DÉMARRAGE ---
async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot.")