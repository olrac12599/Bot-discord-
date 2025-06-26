import discord
from discord.ext import commands, tasks
import requests
import os
# La ligne "from dotenv import load_dotenv" a été SUPPRIMÉE.

# --- CONFIGURATION INITIALE ---
# La ligne "load_dotenv()" a été SUPPRIMÉE.

# On lit directement les variables d'environnement qui sont fournies par Railway.
# C'est exactement ce que "getenv" (get environment variable) veut dire.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")

# --- VÉRIFICATION DES VARIABLES (TRÈS IMPORTANT) ---
# On vérifie que les variables ont bien été trouvées dans l'environnement de Railway.
if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN]):
    # Si une des variables manque, le bot ne peut pas démarrer.
    # On lève une erreur pour que les logs de Railway montrent clairement le problème.
    raise ValueError("Une ou plusieurs variables d'environnement sont manquantes (DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN).")


# Configuration des "Intents" pour le bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# (Le reste du code est absolument identique à la version précédente)

# --- STOCKAGE DES ALERTES ---
alerts = []
streamer_id_cache = {}

# --- FONCTIONS UTILITAIRES TWITCH ---
async def get_streamer_id(streamer_name):
    if streamer_name in streamer_id_cache:
        return streamer_id_cache[streamer_name]

    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"login": streamer_name.lower()}
    response = requests.get("https://api.twitch.tv/helix/users", headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["data"]:
            user_id = data["data"][0]["id"]
            streamer_id_cache[streamer_name] = user_id
            return user_id
    # Gestion de l'expiration du token
    elif response.status_code == 401:
        print("ERREUR: Le token Twitch a probablement expiré. Veuillez en générer un nouveau.")
    return None

async def get_stream_status(streamer_id):
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"user_id": streamer_id}
    response = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["data"]:
            return data["data"][0]
    return None

# --- COMMANDES DU BOT ---
@bot.command(name="ping")
async def ping(ctx, category: str, streamer: str):
    streamer_name_lower = streamer.lower()
    category_name_lower = category.lower()

    for alert in alerts:
        if alert['streamer'] == streamer_name_lower and \
           alert['category'] == category_name_lower and \
           alert['author_id'] == ctx.author.id:
            await ctx.send(f"Vous avez déjà une alerte active pour **{streamer}** dans la catégorie **{category}**.")
            return

    new_alert = {
        "streamer": streamer_name_lower,
        "category": category_name_lower,
        "channel_id": ctx.channel.id,
        "author_id": ctx.author.id,
        "last_status": False
    }
    alerts.append(new_alert)
    await ctx.send(f"✅ Alerte créée ! Je vous préviendrai si **{streamer}** lance un live sur **{category}**.")

# --- TÂCHE DE FOND ---
@tasks.loop(minutes=1)
async def check_streams():
    print(f"Vérification des streams en cours... {len(alerts)} alerte(s) active(s).")
    
    for alert in alerts:
        streamer_id = await get_streamer_id(alert['streamer'])
        if not streamer_id:
            continue 

        stream_info = await get_stream_status(streamer_id)
        
        is_live_in_category = False
        if stream_info:
            current_category = stream_info.get("game_name", "").lower()
            if alert['category'] in current_category:
                is_live_in_category = True
        
        if is_live_in_category and not alert['last_status']:
            channel = bot.get_channel(alert['channel_id'])
            if channel:
                user = await bot.fetch_user(alert['author_id'])
                message = (
                    f"🔔 **ALERTE** 🔔\n"
                    f"{user.mention}, le streamer **{alert['streamer'].capitalize()}** vient de lancer un live dans la catégorie **{stream_info['game_name']}** !\n"
                    f"Titre : {stream_info['title']}\n"
                    f"https://www.twitch.tv/{alert['streamer']}"
                )
                await channel.send(message)
        
        alert['last_status'] = is_live_in_category

# --- DÉMARRAGE DU BOT ---
@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name}')
    check_streams.start()

bot.run(DISCORD_TOKEN)
