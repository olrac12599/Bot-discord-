from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from datetime import datetime
import discord
from discord.ext import commands
import os

TOKEN_DISCORD= os.dotenv('TOKEN_DISCORD')

# Fonction pour convertir une chaîne de date en datetime
def to_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d")

# Récupère les vidéos de la chaîne
def get_videos_from_channel(channel_url):
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'force_generic_extractor': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        return info.get('entries', [])

# Cherche la phrase dans les sous-titres
def search_in_subtitles(video_id, phrase):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['fr', 'en'])
        results = []
        for entry in transcript:
            if phrase.lower() in entry['text'].lower():
                results.append({
                    'start': entry['start'],
                    'text': entry['text']
                })
        return results
    except (TranscriptsDisabled, NoTranscriptFound):
        return []

# === MAIN ===
bot = commands.Bot(command_prefix="!")

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

@bot.command()
async def cherche(ctx, url, *, phrase):
    await ctx.send("Recherche en cours...")

    # Dates à utiliser pour la recherche
    start_date = to_date("2024-12-11")
    end_date = to_date("2025-04-09")

    videos = get_videos_from_channel(url)

    count = 0
    for video in videos:
        video_date = datetime.strptime(video['upload_date'], "%Y%m%d")
        if start_date <= video_date <= end_date:
            video_id = video['url'].split('v=')[-1]
            results = search_in_subtitles(video_id, phrase)
            if results:
                count += 1
                await ctx.send(f"\n**{video['title']}**\nhttps://www.youtube.com/watch?v={video_id}")
                for res in results:
                    time = int(res['start'])
                    await ctx.send(f"> À {time//60}:{time%60:02d} — {res['text']}")

    if count == 0:
        await ctx.send("Aucun résultat trouvé.")

# Lance le bot
bot.run("TON_TOKEN_ICI")