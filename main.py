import discord
from discord.ext import commands
import os
import asyncio
import io
from pathlib import Path
from scraping import get_pgn_from_chess_com, ScrapingError

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo

last_video_paths = {}
active_tasks = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def chess(ctx, url: str):
    if ctx.channel.id in active_tasks:
        return await ctx.send("⚠️ Une analyse est déjà en cours ici. Tape `!stop` pour l'arrêter.")
    
    async def run():
        msg = await ctx.send("🕵️ Lancement de l'analyse + enregistrement vidéo...")
        try:
            pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD, ctx.channel)
            if video_path:
                last_video_paths[ctx.channel.id] = video_path
            pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
            await msg.edit(content=f"✅ **PGN récupéré :**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo.*")
        except ScrapingError as e:
            await msg.edit(content="❌ Erreur pendant le scraping.")
            if e.video_path:
                last_video_paths[ctx.channel.id] = e.video_path
                await ctx.send("🎥 Vidéo disponible :", file=discord.File(e.video_path, "debug_video.webm"))
            else:
                await ctx.send("❌ Aucune vidéo enregistrée.")
        finally:
            active_tasks.pop(ctx.channel.id, None)

    task = asyncio.create_task(run())
    active_tasks[ctx.channel.id] = task

@bot.command(name="cam")
async def cam(ctx):
    video_path = last_video_paths.get(ctx.channel.id)
    if not video_path or not Path(video_path).exists():
        return await ctx.send("❌ Aucune vidéo trouvée.")
    file = Path(video_path)
    if file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo :", file=discord.File(str(file), "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({file.stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="stop")
async def stop(ctx):
    task = active_tasks.get(ctx.channel.id)
    if not task:
        return await ctx.send("❌ Aucun scraping en cours.")
    task.cancel()
    await ctx.send("🛑 Scraping interrompu. Envoi de la vidéo...")
    video_path = last_video_paths.get(ctx.channel.id)
    if video_path and Path(video_path).exists():
        await ctx.send("📹 Vidéo sauvegardée :", file=discord.File(video_path, "debug_video.webm"))
    else:
        await ctx.send("❌ Aucune vidéo disponible.")
    active_tasks.pop(ctx.channel.id, None)

@bot.command(name="aide")
async def aide(ctx):
    await ctx.send("""📖 **Commandes disponibles :**
`!chess <url>` – Analyse en direct d’une partie Chess.com
`!cam` – Envoie la vidéo de la dernière session
`!stop` – Stoppe l’analyse en cours et envoie la vidéo
`!ping` – Latence du bot
`!aide` – Affiche cette aide
""")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)} ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot arrêté.")