import os
import discord
from discord.ext import commands, tasks
import googleapiclient.discovery

API_YT = os.getenv('API_YT')

# Configuration du bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Clé API YouTube (remplace par la tienne)
API_KEY = 'API_YT'
CHANNEL_ID = 'UCqHw1XAOi4QZQ4M7n6jFdHg'  # ID de la chaîne YouTube de Blazx
TEXT_CHANNEL_ID = 1357601068921651203  # ID du salon Discord où la vidéo sera envoyée

# Fonction pour récupérer la dernière vidéo de la chaîne via l'API YouTube
def get_last_video():
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=API_KEY)
    
    # Récupérer les 1 dernières vidéos de la chaîne
    request = youtube.search().list(
        part="snippet",
        channelId=CHANNEL_ID,
        order="date",  # Trie par date
        maxResults=1
    )
    response = request.execute()
    
    # Si on a trouvé une vidéo, renvoie l'URL et le titre
    if response["items"]:
        video = response["items"][0]
        video_url = f"https://www.youtube.com/watch?v={video['id']['videoId']}"
        video_title = video['snippet']['title']
        return video_url, video_title
    else:
        return None, None

# Fonction asynchrone qui envoie la vidéo dans un salon Discord
@tasks.loop(seconds=10)  # Cette tâche sera exécutée toutes les 10 secondes
async def send_last_video():
    video_url, video_title = get_last_video()
    
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