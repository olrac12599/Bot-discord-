import discord
import os
import requests
import asyncio
import time
from flask import Flask
from colorama import init, Fore  # Importer colorama pour les erreurs en rouge dans la console
import threading

# Initialisation de colorama
init(autoreset=True)
id_discord = os.environ['id_discord']
DISCORD_TOKEN = os.environ['caca']  # Remplacer 'caca' par 'DISCORD_TOKEN'
CLIENT_ID = os.environ['CLIENT_ID']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']

STREAMERS_CIBLES = ["tobias", "blazx", "lamatrak", "fugu_fps", "anyme023"]
LOG_CHANNEL_ID = 1356775675297533965  # ID du salon de logs
USER_ID_DISCORD = (id_discord)  # Ton ID Discord

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
bot = discord.Client(intents=intents)

# Fonction pour afficher les erreurs en rouge dans la console
def log_error(error_message):
    """Affiche les erreurs en rouge dans la console."""
    print(Fore.RED + f"❌ Erreur: {error_message}")

# Récupérer l'ID de l'utilisateur Twitch
def get_user_id():
    try:
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {ACCESS_TOKEN}'
        }
        response = requests.get("https://api.twitch.tv/helix/users", headers=headers)

        if response.status_code == 200:
            return response.json()["data"][0]["id"]
        else:
            log_error("Impossible de récupérer l'ID utilisateur Twitch.")
            return None
    except Exception as e:
        log_error(f"Erreur lors de la récupération de l'ID utilisateur Twitch: {str(e)}")
        return None

# Récupérer les streams en direct
def get_live_streams(user_id):
    try:
        url = f"https://api.twitch.tv/helix/streams/followed?user_id={user_id}"
        headers = {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {ACCESS_TOKEN}"
        }
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            log_error("Erreur API Twitch lors de la récupération des streams.")
            return []
    except Exception as e:
        log_error(f"Erreur lors de la récupération des streams: {str(e)}")
        return []

# Envoyer ou mettre à jour un DM
async def send_or_update_dm(user, embed, message_id=None):
    try:
        if message_id:
            msg = await user.fetch_message(message_id)
            await msg.edit(embed=embed)
        else:
            msg = await user.send(embed=embed)
            return msg.id
    except discord.Forbidden:
        log_error(f"Impossible d'envoyer un message à {user.name}.")
    except discord.NotFound:
        log_error("Le message n'a pas été trouvé.")
    return message_id

# Enregistrer les actions dans le canal de logs
async def log_action(content):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(content)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    await log_action("✅ Bot démarré et prêt à fonctionner !")
    bot.loop.create_task(update_stream_notifications())

# Fonction principale de mise à jour des notifications de streamers
async def update_stream_notifications():
    await bot.wait_until_ready()
    user_id = get_user_id()
    if not user_id:
        log_error("Impossible de récupérer l'ID utilisateur Twitch.")
        return

    notified_streamers = {}

    while not bot.is_closed():
        live_streams = get_live_streams(user_id)
        live_info = {s["user_login"].lower(): s for s in live_streams}

        embed = discord.Embed(title="🎥 **Streamers en Live**", color=0x9146FF)
        updated = False

        for streamer in STREAMERS_CIBLES:
            if streamer in live_info:
                info = live_info[streamer]

                # 🔄 Ajoute un timestamp unique pour forcer la mise à jour de l'image
                timestamp = int(time.time())
                preview_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{streamer}-600x340.jpg?rand={timestamp}"

                embed.add_field(
                    name=f"🔴 {info['user_name']}",
                    value=f"🎮 **{info['game_name']}**\n"
                          f"📖 {info['title']}\n"
                          f"👥 {info['viewer_count']} spectateurs\n"
                          f"[▶️ Regarder](https://twitch.tv/{streamer})",
                    inline=False
                )

                # Met à jour l'image de l'embed
                embed.set_image(url=preview_url)

                if streamer not in notified_streamers:
                    notified_streamers[streamer] = None
                    updated = True

        if updated or len(embed.fields) != len(notified_streamers):
            user = await bot.fetch_user(USER_ID_DISCORD)
            notified_streamers[streamer] = await send_or_update_dm(user, embed, notified_streamers.get(streamer))
            await log_action(f"🔔 **Mise à jour des streamers en live.**")

        await asyncio.sleep(30)  # Mise à jour toutes les 30 secondes (plus raisonnable)

# Flask : Serveur simple pour vérifier que le bot est en ligne
app = Flask(__name__)

@app.route('/')
def home():
    return "Le bot est en ligne !"

# Fonction pour démarrer Flask dans un thread séparé
def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=False)  # Désactivation du reloader

# Démarrer le serveur Flask dans un thread séparé
threading.Thread(target=run_flask).start()

# Lancement du bot Discord
bot.run(DISCORD_TOKEN)