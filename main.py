import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
import os

# Configuration du bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# URL de la chaîne YouTube de Blazx
CHANNEL_URL = "https://m.youtube.com/@blazxoff"
TEXT_CHANNEL_ID = 1357601068921651203  # ID du salon où la vidéo sera envoyée

# Fonction pour récupérer la dernière vidéo de la chaîne
def get_last_video(channel_url):
    # Faire une requête pour récupérer le HTML de la page de la chaîne
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    response = requests.get(channel_url, headers=headers)

    # Vérifier que la requête a fonctionné
    if response.status_code != 200:
        print(f"Erreur lors de la récupération de la page : {response.status_code}")
        return None, None

    # Analyser le HTML avec BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')

    # Trouver la vidéo la plus récente (on va chercher un tag <a> avec un certain ID)
    video_tag = soup.find('a', {'id': 'video-title'})
    
    if video_tag:
        video_url = "https://www.youtube.com" + video_tag['href']
        video_title = video_tag.get('title')
        return video_url, video_title
    else:
        print("Aucune vidéo trouvée.")
        return None, None

# Fonction asynchrone qui envoie la vidéo dans un salon Discord
@tasks.loop(seconds=10)  # Cette tâche sera exécutée toutes les 10 secondes
async def send_last_video():
    # Récupérer la dernière vidéo
    video_url, video_title = get_last_video(CHANNEL_URL)
    
    if video_url:
        # Obtenir le salon où envoyer la vidéo
        channel = bot.get_channel(TEXT_CHANNEL_ID)
        if channel:
            await channel.send(f"📺 Dernière vidéo de Blazx : {video_title}\n[Regarder ici]({video_url})")
        else:
            print("Le salon spécifié n'a pas été trouvé.")
    else:
        print("Aucune vidéo trouvée.")

# Commande de démarrage pour le bot
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    send_last_video.start()  # Lancer la tâche pour envoyer la vidéo

# Lancer le bot Discord
bot.run(os.getenv('TOKEN_DISCORD'))