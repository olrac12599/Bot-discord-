import discord
from discord.ext import commands
import os
import asyncio
import io
from pathlib import Path
from scraping import get_pgn_from_chess_com, ScrapingError

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo

videos_dir = Path("videos")
last_video_paths = {}
active_tasks = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if ctx.channel.id in active_tasks:
        return await ctx.send("⚠️ Une analyse est déjà en cours dans ce salon. Utilisez `!stop` pour l'arrêter.")

    async def run_chess():
        msg = await ctx.send("🕵️ Connexion à Chess.com... Enregistrement vidéo + analyse en direct en cours.")
        try:
            pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD, ctx.channel)
            if video_path:
                last_video_paths[ctx.channel.id] = video_path
            pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
            await msg.edit(content=f"✅ **PGN récupéré :**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo.*")
        except ScrapingError as e:
            await msg.edit(content="❌ Erreur lors du scraping.")
            if e.video_path:
                last_video_paths[ctx.channel.id] = e.video_path
                await ctx.send("🎥 Voici la vidéo de la session échouée :", file=discord.File(e.video_path, "debug_video.webm"))
            else:
                await ctx.send("❌ Aucun enregistrement vidéo disponible.")
        finally:
            active_tasks.pop(ctx.channel.id, None)

    task = asyncio.create_task(run_chess())
    active_tasks[ctx.channel.id] = task

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path_str = last_video_paths.get(ctx.channel.id)
    if not video_path_str:
        return await ctx.send("❌ Aucune vidéo récente trouvée.")
    video_file = Path(video_path_str)
    if not video_file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la dernière opération :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="stop")
async def stop_scraping(ctx):
    task = active_tasks.get(ctx.channel.id)
    if not task:
        return await ctx.send("❌ Aucun scraping en cours dans ce salon.")
    task.cancel()
    await ctx.send("🛑 Scraping interrompu. Tentative d'envoi de la vidéo...")
    video_path_str = last_video_paths.get(ctx.channel.id)
    if not video_path_str:
        return await ctx.send("❌ Aucune vidéo récente trouvée.")
    video_file = Path(video_path_str)
    if not video_file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la session interrompue :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")
    active_tasks.pop(ctx.channel.id, None)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}.")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot arrêté.")