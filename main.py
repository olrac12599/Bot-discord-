import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
import os
import asyncio

# --- NOUVEAU : Import pour le bot Twitch ---
from twitchio.ext import commands as twitch_commands


# --- 1. CONFIGURATION ---
# --- Configuration pour le bot Discord (EXISTANT) ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN") # Token pour l'API (alertes de live)

# --- NOUVEAU : Configuration pour le bot Twitch (Chat) ---
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN") # Token OAuth pour le chat
TTV_CHANNEL_TO_MONITOR = os.getenv("TTV_CHANNEL_TO_MONITOR")
TTV_KEYWORD = os.getenv("TTV_KEYWORD")

# --- Vérification de la configuration ---
if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN, TTV_CHANNEL_TO_MONITOR]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes pour Discord ou Twitch.")

# --- Configuration du bot Discord ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- NOUVEAU : BOT DE SURVEILLANCE DU CHAT TWITCH ---
# Cette classe est entièrement nouvelle et gère la connexion au chat Twitch.
class WatcherBot(twitch_commands.Bot):
    def __init__(self, discord_bot_instance):
        super().__init__(token=TTV_BOT_TOKEN, prefix='!', initial_channels=[TTV_CHANNEL_TO_MONITOR])
        self.discord_bot = discord_bot_instance # Garde une référence au bot discord pour envoyer des notifs
        
    async def event_ready(self):
        print("-------------------------------------------------")
        print(f"Bot de surveillance Twitch '{TTV_BOT_NICKNAME}' connecté.")
        print(f"Surveillance du salon : #{TTV_CHANNEL_TO_MONITOR}")
        print(f"Recherche du mot-clé : '{TTV_KEYWORD}'")
        print("-------------------------------------------------")

    # --- VERSION MODIFIÉE DE LA FONCTION ---
    async def event_message(self, message):
        if message.echo:
            return

        # La condition reste la même
        if TTV_KEYWORD.lower() in message.content.lower():
            # On garde le message dans la console, c'est utile
            print(f"[TWITCH] Mot-clé trouvé dans le chat de {message.channel.name} par {message.author.name}: {message.content}")

            # --- DÉBUT DU CODE AJOUTÉ POUR LA NOTIFICATION DISCORD ---
            
            # 1. On définit l'ID de votre salon Discord
            channel_id = 1388952464782524548

            # 2. On récupère l'objet "salon" via le bot Discord
            channel_to_notify = self.discord_bot.get_channel(channel_id)

            # 3. On vérifie que le salon existe et que le bot y a accès
            if channel_to_notify:
                try:
                    # 4. On prépare un message clair et esthétique (Embed)
                    embed = discord.Embed(
                        title="🚨 Alerte Mot-Clé sur Twitch !",
                        description=f"Le mot-clé **'{TTV_KEYWORD}'** a été détecté dans le chat.",
                        color=discord.Color.from_rgb(145, 70, 255) # Couleur violette de Twitch
                    )
                    embed.add_field(name="Chaîne Twitch", value=f"[{message.channel.name}](https://twitch.tv/{message.channel.name})", inline=True)
                    embed.add_field(name="Auteur du message", value=message.author.name, inline=True)
                    embed.add_field(name="Message", value=message.content, inline=False)
                    embed.set_thumbnail(url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png")
                    
                    # 5. On envoie la notification dans votre salon Discord
                    await channel_to_notify.send(embed=embed)

                except discord.errors.Forbidden:
                    print(f"[ERREUR DISCORD] Le bot n'a pas les permissions pour envoyer un message dans le salon ID {channel_id}.")
                except Exception as e:
                    print(f"[ERREUR DISCORD] Une erreur inattendue est survenue : {e}")
            else:
                print(f"[ERREUR DISCORD] Impossible de trouver le salon avec l'ID {channel_id}. Le bot est-il bien sur le serveur ? L'ID est-il correct ?")
            # --- FIN DU CODE AJOUTÉ ---

# --- 2. STOCKAGE (EXISTANT) ---
alerts = []
streamer_id_cache = {}

# --- 3. FONCTIONS UTILITAIRES TWITCH (EXISTANT) ---
# Ces fonctions ne changent pas, elles servent pour les alertes de live.
async def get_streamer_id(streamer_name: str) -> str | None:
    if streamer_name in streamer_id_cache: return streamer_id_cache[streamer_name]
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"login": streamer_name.lower()}
    try:
        r = requests.get("https://api.twitch.tv/helix/users", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"):
            user_id = data["data"][0]["id"]
            streamer_id_cache[streamer_name] = user_id
            return user_id
    except requests.exceptions.RequestException as e: print(f"Erreur API (get_streamer_id): {e}")
    return None

async def get_stream_status(streamer_id: str) -> dict | None:
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"user_id": streamer_id}
    try:
        r = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"): return data["data"][0]
    except requests.exceptions.RequestException as e: print(f"Erreur API (get_stream_status): {e}")
    return None


# --- 4. COMMANDES SLASH (INCHANGÉ) ---
# Toutes vos commandes Discord restent exactement les mêmes.

async def streamer_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not current: return []
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"query": current, "first": 7}
    try:
        r = requests.get("https://api.twitch.tv/helix/search/channels", headers=headers, params=params, timeout=3)
        if r.status_code == 200:
            return [app_commands.Choice(name=c['display_name'], value=c['broadcaster_login']) for c in r.json()['data']]
    except requests.exceptions.RequestException: pass
    return []

@bot.tree.command(name="alerte_live", description="Crée une alerte simple pour savoir quand un streamer se connecte.")
@app_commands.autocomplete(streamer=streamer_autocomplete)
async def alerte_live(interaction: discord.Interaction, streamer: str):
    await interaction.response.defer(ephemeral=True)
    streamer_name_lower = streamer.lower()
    for alert in alerts:
        if alert['streamer'] == streamer_name_lower and alert['category'] == '*' and alert['author_id'] == interaction.user.id:
            await interaction.followup.send(f"❌ Vous avez déjà une alerte générale active pour **{streamer}**.")
            return
    new_alert = {"streamer": streamer_name_lower, "category": '*', "channel_id": interaction.channel.id, "author_id": interaction.user.id, "last_status": False}
    alerts.append(new_alert)
    await interaction.followup.send(f"✅ Alerte générale créée ! Je vous préviendrai dès que **{streamer.capitalize()}** lancera un stream.")

class AlertModal(discord.ui.Modal, title="Créer une Alerte Twitch Spécifique"):
    streamer = discord.ui.TextInput(label="Nom du streamer Twitch", placeholder="Ex: squeezie", required=True)
    category = discord.ui.TextInput(label="Nom de la catégorie (jeu)", placeholder="Ex: Grand Theft Auto V", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        s_lower, c_lower = self.streamer.value.lower(), self.category.value.lower()
        for alert in alerts:
            if alert['streamer'] == s_lower and alert['category'] == c_lower and alert['author_id'] == interaction.user.id:
                await interaction.response.send_message(f"❌ Alerte déjà active pour **{self.streamer.value}**.", ephemeral=True)
                return
        new_alert = {"streamer": s_lower, "category": c_lower, "channel_id": interaction.channel.id, "author_id": interaction.user.id, "last_status": False}
        alerts.append(new_alert)
        await interaction.response.send_message(f"✅ Alerte créée pour **{self.streamer.value}** sur **{self.category.value}**.", ephemeral=True)

class PingPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Créer une Alerte Spécifique", style=discord.ButtonStyle.primary, emoji="➕")
    async def create_alert_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AlertModal())

@bot.tree.command(name="alerte", description="Affiche un panel pour configurer une alerte sur un jeu précis.")
async def alerte_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🔔 Configuration des Alertes Twitch", description="Utilisez le bouton ci-dessous pour créer une alerte sur une catégorie de jeu spécifique.", color=discord.Color.purple())
    embed.set_thumbnail(url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png")
    await interaction.response.send_message(embed=embed, view=PingPanelView())

# --- 5. COMMANDES DE MODÉRATION (INCHANGÉ) ---
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_alerts(ctx):
    guild_id = ctx.guild.id
    to_remove = [a for a in alerts if bot.get_channel(a['channel_id']) and bot.get_channel(a['channel_id']).guild.id == guild_id]
    if not to_remove: return await ctx.send("Aucune alerte active à supprimer sur ce serveur.")
    for alert in to_remove: alerts.remove(alert)
    await ctx.send(f"✅ {len(to_remove)} alerte(s) ont été supprimée(s) pour ce serveur.")

@bot.command(name="all")
@commands.has_permissions(administrator=True)
async def clear_all_messages(ctx):
    msg = await ctx.send(f"Êtes-vous sûr de vouloir supprimer **TOUS** les messages ?\nRépondez par `oui` pour confirmer (15s).")
    try:
        await bot.wait_for('message', timeout=15.0, check=lambda m: m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'oui')
        await ctx.send("Confirmation reçue. Suppression...", delete_after=2)
        deleted = await ctx.channel.purge(limit=None)
        await ctx.send(f"✅ {len(deleted)} messages supprimés.", delete_after=5)
    except asyncio.TimeoutError: await msg.edit(content="Délai dépassé. Annulation.")

# --- 6. TÂCHE DE FOND (INCHANGÉ) ---
@tasks.loop(minutes=1)
async def check_streams():
    if not alerts: return
    print(f"[DISCORD] Vérification des streams... ({len(alerts)} alerte(s))") # Ajout d'un préfixe pour clarté
    for alert in alerts:
        streamer_id = await get_streamer_id(alert['streamer'])
        if not streamer_id: continue
        stream_info = await get_stream_status(streamer_id)
        
        condition_met = False
        if stream_info:
            if alert['category'] == '*' or alert['category'] in stream_info.get("game_name", "").lower():
                condition_met = True
        
        if condition_met and not alert['last_status']:
            try:
                channel = bot.get_channel(alert['channel_id'])
                user = await bot.fetch_user(alert['author_id'])
                if channel and user:
                    message = (f"🔔 **ALERTE** 🔔\n{user.mention}, **{stream_info['user_name']}** est en live sur **{stream_info['game_name']}** !\n"
                               f"Titre : {stream_info['title']}\nhttps://www.twitch.tv/{stream_info['user_login']}")
                    await channel.send(message)
            except Exception as e: print(f"Erreur envoi notif: {e}")
        
        alert['last_status'] = condition_met

# --- 7. DÉMARRAGE ET GESTION DES ERREURS ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Vous n'avez pas les permissions pour cette commande.")
    else: print(f"Erreur de commande non gérée: {error}")

@bot.event
async def on_ready():
    # Message de connexion pour le bot Discord
    print(f"-------------------------------------------------")
    print(f"Bot Discord '{bot.user.name}' connecté.")
    print(f"-------------------------------------------------")
    try:
        synced = await bot.tree.sync()
        print(f"[DISCORD] Synchronisé {len(synced)} commande(s) slash.")
    except Exception as e: print(f"Erreur de synchronisation: {e}")
    check_streams.start()

# --- NOUVEAU : Démarrage simultané des deux bots ---
# On remplace l'ancien `bot.run(DISCORD_TOKEN)` par cette fonction main
# pour lancer les deux bots en parallèle.
async def main():
    # On crée les instances des deux bots
    discord_bot_instance = bot
    twitch_bot_instance = WatcherBot(discord_bot_instance)

    # On utilise asyncio.gather pour les lancer en même temps
    await asyncio.gather(
        discord_bot_instance.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    # On lance la fonction main qui gère le démarrage
    asyncio.run(main())
