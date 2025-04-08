import discord
import os
import requests
import asyncio
import time
from discord.ext import commands
from PIL import Image
import io
from bs4 import BeautifulSoup  # Assure-toi d'avoir bs4 installé !

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Liste des chaînes YouTube à surveiller
STREAMERS_YT = [
    "SQUEEZIE GAMING", "Unchained_off", "Aywen", "SQUEEZIE", "Tobias", "BLAZX EN MIEUX",
    "FUGU", "RaGe", "[Unchained]", "MichouOff", "Michou", "TobiasEnVrai", "Fiouze",
    "Anyme TV", "BouziTV", "Lamatrak", "Tobias TV", "Qin Hui", "Jolavanille", "Inoxtag2.0", "Louisbaldiviensdansmonlit"
]
last_video = {channel: "" for channel in STREAMERS_YT}

# Fonction pour récupérer la dernière vidéo d'une chaîne YouTube
def get_last_video(channel_name):
    url = f"https://www.youtube.com/c/{channel_name}/videos"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    video_tag = soup.find('a', {'id': 'video-title'})
    if video_tag:
        video_url = "https://www.youtube.com" + video_tag['href']
        video_title = video_tag.get('title')
        return video_url, video_title
    return None, None

# Fonction pour envoyer la dernière vidéo de chaque chaîne dans un salon spécifique au démarrage
async def send_latest_youtube_videos():
    await bot.wait_until_ready()
    text_channel = bot.get_channel(1357601068921651203)

    if not text_channel:
        print("Salon de notification YouTube introuvable.")
        return

    embed = discord.Embed(
        title="📺 Dernières vidéos YouTube",
        description="Voici les vidéos les plus récentes des chaînes suivies :",
        color=0xff0000
    )

    for streamer in STREAMERS_YT:
        video_url, video_title = get_last_video(streamer)
        if video_url:
            embed.add_field(
                name=streamer,
                value=f"[{video_title}]({video_url})",
                inline=False
            )
        else:
            embed.add_field(
                name=streamer,
                value="❌ Aucune vidéo trouvée",
                inline=False
            )

    await text_channel.send(embed=embed)

# Fonction pour créer ou récupérer un salon
async def get_or_create_channel(channel_name, guild):
    existing = discord.utils.get(guild.text_channels, name=channel_name.lower())
    if existing:
        return existing

    category = discord.utils.get(guild.categories, id=1357601068921651201)  # ID de la catégorie à utiliser
    if not category:
        print("Catégorie introuvable.")
        return None

    new_channel = await guild.create_text_channel(channel_name.lower(), category=category)
    return new_channel

# Fonction pour vérifier les vidéos toutes les 10 secondes
async def check_new_videos():
    await bot.wait_until_ready()
    guild = bot.guilds[0]
    while True:
        for streamer in STREAMERS_YT:
            video_url, video_title = get_last_video(streamer)
            if video_url and video_url != last_video[streamer]:
                last_video[streamer] = video_url
                channel = await get_or_create_channel(streamer, guild)
                if channel:
                    embed = discord.Embed(
                        title=f"📢 Nouvelle vidéo de {streamer}",
                        description=f"**{video_title}**\n[Regarder ici]({video_url})",
                        color=0xff0000
                    )
                    await channel.send(content="@everyone", embed=embed)
        await asyncio.sleep(10)

# Paramètres de Twitch
TOKEN_DISCORD = os.environ['TOKEN_DISCORD']
CLIENT_ID = os.environ['CLIENT_ID']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']
TEXT_NOTIFY_CHANNEL_ID = 1357601068921651203

STREAMERS_CIBLES = {"fugu_fps", "tobias", "blazx", "lamatrak", "Aneyaris_", "anyme023"}
streamers_dynamique = set()
notified_message_id = None
empty_message_id = None

# Fonction pour récupérer l'ID utilisateur
def get_user_id():
    headers = {'Client-ID': CLIENT_ID, 'Authorization': f'Bearer {ACCESS_TOKEN}'}
    response = requests.get("https://api.twitch.tv/helix/users", headers=headers)
    if response.status_code == 200:
        return response.json()["data"][0]["id"]
    return None

# Fonction pour récupérer les streams en direct
def get_live_streams(user_id):
    url = f"https://api.twitch.tv/helix/streams/followed?user_id={user_id}"
    headers = {"Client-ID": CLIENT_ID, "Authorization": f'Bearer {ACCESS_TOKEN}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("data", [])
    return []

# Événement de démarrage du bot
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    await send_latest_youtube_videos()  # Résumé des dernières vidéos
    bot.loop.create_task(check_new_videos())
    bot.loop.create_task(update_stream_notifications())

# Fonction pour notifier les streams en direct
async def update_stream_notifications():
    await bot.wait_until_ready()
    user_id = get_user_id()
    if not user_id:
        print("Impossible de récupérer l'ID utilisateur Twitch.")
        return

    global notified_message_id, empty_message_id
    already_live = set()

    while True:
        live_streams = get_live_streams(user_id)
        live_info = {s["user_login"].lower(): s for s in live_streams}
        live_now = STREAMERS_CIBLES.union(streamers_dynamique).intersection(live_info.keys())
        text_channel = bot.get_channel(TEXT_NOTIFY_CHANNEL_ID)

        # Notif @everyone pour nouveaux streamers en live
        new_live = live_now - already_live
        for new_streamer in new_live:
            msg = await text_channel.send(f"🚨 **{new_streamer} est en live !** @everyone\nhttps://twitch.tv/{new_streamer}")
            await msg.delete(delay=5)

        already_live = live_now

        if live_now:
            embed = discord.Embed(
                title="🎥 **Streamers en Live**",
                color=0x9146FF,
                description="🔥 Voici les streamers actuellement en live !"
            )
            files = []

            for i, streamer in enumerate(live_now):
                info = live_info[streamer]
                timestamp = int(time.time())
                preview_url = info["thumbnail_url"].replace("{width}", "160").replace("{height}", "90")
                preview_url += f"?t={timestamp}"

                response = requests.get(preview_url)
                image = Image.open(io.BytesIO(response.content))
                image = image.resize((160, 90))
                image_bytes = io.BytesIO()
                image.save(image_bytes, format="PNG")
                image_bytes.seek(0)

                filename = f"preview_{i}.png"
                file = discord.File(image_bytes, filename=filename)
                files.append(file)

                embed.add_field(
                    name=f"🔴 **{info['user_name']}**",
                    value=(
                        f"🎮 **{info['game_name']}**\n"
                        f"📖 {info['title']}\n"
                        f"👥 {info['viewer_count']} spectateurs\n"
                        f"[▶️ **Regarder**](https://twitch.tv/{streamer})"
                    ),
                    inline=True
                )

                embed.set_thumbnail(url=f"attachment://{filename}")

            embed.set_footer(text="📢 Mis à jour automatiquement toutes les 10 secondes")

            if notified_message_id:
                try:
                    msg = await text_channel.fetch_message(notified_message_id)
                    await msg.edit(embed=embed, attachments=files)
                except (discord.NotFound, discord.HTTPException):
                    msg = await text_channel.send(embed=embed, files=files)
                    notified_message_id = msg.id
            else:
                msg = await text_channel.send(embed=embed, files=files)
                notified_message_id = msg.id

            if empty_message_id:
                try:
                    empty_msg = await text_channel.fetch_message(empty_message_id)
                    await empty_msg.delete()
                    empty_message_id = None
                except discord.NotFound:
                    pass
        else:
            if notified_message_id:
                try:
                    msg = await text_channel.fetch_message(notified_message_id)
                    await msg.delete()
                    notified_message_id = None
                except discord.NotFound:
                    pass

            if not empty_message_id:
                empty_msg = await text_channel.send("❌ **Personne n'est en live actuellement.**")
                empty_message_id = empty_msg.id

        await asyncio.sleep(10)

# Commandes du bot
@bot.command()
async def a(ctx, streamer: str):
    streamers_dynamique.add(streamer.lower())
    await ctx.message.delete()
    await ctx.send(f"✅ **{streamer}** a été ajouté à la liste des notifications.", delete_after=3)

@bot.command()
async def r(ctx, streamer: str):
    streamers_dynamique.discard(streamer.lower())
    await ctx.message.delete()
    await ctx.send(f"❌ **{streamer}** a été retiré de la liste des notifications.", delete_after=3)

@bot.command()
async def all(ctx):
    await ctx.channel.purge()
    await ctx.send("🧹 **Le salon a été nettoyé !**", delete_after=3)

# Démarre le bot
bot.run(TOKEN_DISCORD)