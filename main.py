import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup

# Configuration du bot
TOKEN_DISCORD = os.getenv('TOKEN_DISCORD')  # Récupère le token depuis les variables d'environnement
intents = discord.Intents.default()
intents.message_content = True  # Assure-toi que l'intent pour le contenu des messages est activé

bot = commands.Bot(command_prefix="!", intents=intents)

# Liste des chaînes YouTube à surveiller
STREAMERS_YT = {
    "Blazx": "@blazxoff",
}

# Fonction pour récupérer la dernière vidéo d'une chaîne YouTube via son handle
def get_last_video(channel_display_name):
    handle = STREAMERS_YT[channel_display_name]
    url = f"https://www.youtube.com/{handle}/videos"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Erreur lors de la récupération de la page pour {channel_display_name}: {response.status_code}")
        return None, None

    soup = BeautifulSoup(response.text, 'html.parser')
    video_tag = soup.find('a', id='video-title')
    
    if video_tag:
        video_url = "https://www.youtube.com" + video_tag['href']
        video_title = video_tag.get('title')
        return video_url, video_title
    else:
        print(f"Aucune vidéo trouvée pour {channel_display_name}")
        return None, None

# Commande Discord pour envoyer la dernière vidéo de @blazxoff
@bot.command()
async def last_video(ctx):
    video_url, video_title = get_last_video("Blazx")
    if video_url:
        await ctx.send(f"📺 Dernière vidéo de Blazx : {video_title}\n[Regarder ici]({video_url})")
    else:
        await ctx.send("❌ Impossible de récupérer la dernière vidéo de Blazx.")

# Lancer le bot
bot.run(TOKEN_DISCORD)