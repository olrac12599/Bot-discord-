import os
import discord
from discord.ext import commands, tasks
import requests
from PIL import Image
import io
import time

# --- Configuration --- #
# Il est recommandé de stocker ces informations dans des variables d'environnement
TOKEN_DISCORD = os.environ['TOKEN_DISCORD']
CLIENT_ID = os.environ['CLIENT_ID']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']

# ID du salon où envoyer les notifications de live
TEXT_NOTIFY_CHANNEL_ID = 1357601068921651203 

# Liste statique des streamers à suivre. Peut être modifiée par les commandes !a et !r
STREAMERS_CIBLES = {"didiiana_","jolavanille","fugu_fps", "tobias", "blazx", "lamatrak", "Aneyaris_", "anyme023"}

# --- Initialisation du bot Discord --- #
intents = discord.Intents.default()
intents.message_content = True  # Nécessaire pour lire le contenu des messages pour les commandes
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Variables globales pour le suivi d'état --- #
streamers_dynamique = set()
notified_message_id = None
empty_message_id = None

# --- Fonctions pour l'API Twitch --- #
def get_user_id():
    """Récupère l'ID de l'utilisateur Twitch associé au token d'accès."""
    headers = {'Client-ID': CLIENT_ID, 'Authorization': f'Bearer {ACCESS_TOKEN}'}
    try:
        response = requests.get("https://api.twitch.tv/helix/users", headers=headers)
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP
        return response.json()["data"][0]["id"]
    except requests.RequestException as e:
        print(f"Erreur lors de la récupération de l'user ID Twitch : {e}")
        return None

def get_live_streams(user_id):
    """Récupère les streams en live parmi les chaînes suivies par l'utilisateur."""
    url = f"https://api.twitch.tv/helix/streams/followed?user_id={user_id}"
    headers = {"Client-ID": CLIENT_ID, "Authorization": f'Bearer {ACCESS_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.RequestException as e:
        print(f"Erreur lors de la récupération des streams live : {e}")
        return []

# --- Tâche de fond pour vérifier les lives --- #
@tasks.loop(seconds=10)
async def update_stream_notifications():
    global notified_message_id, empty_message_id
    
    user_id = get_user_id()
    if not user_id:
        print("Vérification annulée : Impossible de récupérer l'ID utilisateur Twitch.")
        return

    live_streams = get_live_streams(user_id)
    live_info = {stream["user_login"].lower(): stream for stream in live_streams}
    
    # Combine la liste statique et la liste dynamique ajoutée par les commandes
    streamers_a_surveiller = STREAMERS_CIBLES.union(streamers_dynamique)
    live_now = streamers_a_surveiller.intersection(live_info.keys())
    
    text_channel = bot.get_channel(TEXT_NOTIFY_CHANNEL_ID)
    if not text_channel:
        print(f"Erreur : le salon avec l'ID {TEXT_NOTIFY_CHANNEL_ID} est introuvable.")
        return

    # Logique pour afficher/mettre à jour l'embed des streamers en live
    if live_now:
        if empty_message_id:
            try:
                empty_msg = await text_channel.fetch_message(empty_message_id)
                await empty_msg.delete()
                empty_message_id = None
            except discord.NotFound:
                empty_message_id = None

        embed = discord.Embed(
            title="🎥 Streamers en Live",
            color=0x9146FF, # Couleur violette de Twitch
            description="🔥 Voici les streamers actuellement en live !"
        )
        
        for streamer_login in live_now:
            info = live_info[streamer_login]
            embed.add_field(
                name=f"🔴 {info['user_name']}",
                value=(
                    f"🎮 **Jeu :** {info['game_name']}\n"
                    f"📖 **Titre :** {info['title']}\n"
                    f"👥 {info['viewer_count']} spectateurs\n"
                    f"[▶️ **Regarder**](https://twitch.tv/{streamer_login})"
                ),
                inline=True
            )
        
        embed.set_footer(text=f"Mis à jour le {time.strftime('%d/%m/%Y à %H:%M:%S')}")
        
        if notified_message_id:
            try:
                msg = await text_channel.fetch_message(notified_message_id)
                await msg.edit(embed=embed)
            except discord.NotFound:
                msg = await text_channel.send(embed=embed)
                notified_message_id = msg.id
        else:
            msg = await text_channel.send(embed=embed)
            notified_message_id = msg.id

    # Logique pour afficher qu'aucun streamer n'est en live
    else:
        if notified_message_id:
            try:
                msg = await text_channel.fetch_message(notified_message_id)
                await msg.delete()
                notified_message_id = None
            except discord.NotFound:
                notified_message_id = None

        if not empty_message_id:
            try:
                empty_msg = await text_channel.send("❌ **Personne n'est en live actuellement.**")
                empty_message_id = empty_msg.id
            except discord.HTTPException as e:
                print(f"Impossible d'envoyer le message 'personne en live': {e}")


# --- Événements et Commandes Discord --- #
@bot.event
async def on_ready():
    """S'exécute une fois que le bot est connecté et prêt."""
    print(f'Connecté en tant que {bot.user}')
    if not update_stream_notifications.is_running():
        update_stream_notifications.start()

@bot.command(name='a')
async def add_streamer(ctx, streamer: str):
    """Ajoute un streamer à la liste de surveillance dynamique."""
    streamers_dynamique.add(streamer.lower())
    await ctx.message.delete()
    await ctx.send(f"✅ **{streamer}** a été ajouté à la liste des notifications.", delete_after=5)

@bot.command(name='r')
async def remove_streamer(ctx, streamer: str):
    """Retire un streamer de la liste de surveillance dynamique."""
    streamers_dynamique.discard(streamer.lower())
    await ctx.message.delete()
    await ctx.send(f"❌ **{streamer}** a été retiré de la liste des notifications.", delete_after=5)

@bot.command(name='all')
async def purge_channel(ctx):
    """Nettoie le salon (supprime tous les messages)."""
    await ctx.channel.purge()
    await ctx.send("🧹 **Le salon a été nettoyé !**", delete_after=3)

# --- Lancement du bot --- #
bot.run(TOKEN_DISCORD)
