import discord
from discord.ext import commands
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from fuzzywuzzy import fuzz  # Recherche approximative
import os

# Configuration du bot
TOKEN_DISCORD = os.getenv('TOKEN_DISCORD')  # Récupère le token depuis les variables d'environnement
intents = discord.Intents.default()
intents.message_content = True  # Assure-toi que l'intent pour le contenu des messages est activé

bot = commands.Bot(command_prefix="!", intents=intents)

# Fonction pour extraire l'ID de la vidéo à partir de l'URL
def get_video_id(url):
    # Si l'URL est dans le format youtube.com
    if "youtube.com/watch?v=" in url:
        return url.split("v=")[-1].split("&")[0]  # Supprimer les paramètres supplémentaires
    # Si l'URL est dans le format youtu.be
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]  # Supprimer les paramètres supplémentaires
    return None

# Fonction pour rechercher la phrase dans les sous-titres avec une recherche approximative
def search_in_subtitles(video_id, phrase):
    try:
        # Récupérer les sous-titres de la vidéo (en plusieurs langues possibles)
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['fr', 'en', 'es', 'de'])

        results = []
        # Chercher la phrase dans les sous-titres
        for entry in transcript:
            score = fuzz.ratio(phrase.lower(), entry['text'].lower())  # Recherche approximative
            if score > 80:  # Si la correspondance est supérieure à 80%
                time = int(entry['start'])
                results.append(f"À {time//60}:{time%60:02d} — {entry['text']} (score: {score}%)")
        
        return results
    except (TranscriptsDisabled, NoTranscriptFound):
        return ["Sous-titres non disponibles pour cette vidéo."]
    except Exception as e:
        return [f"Erreur: {str(e)}"]

# Commande Discord
@bot.command()
async def yt(ctx, url: str, *, phrase: str):
    video_id = get_video_id(url)
    if not video_id:
        await ctx.send("URL invalide. Assure-toi que c'est un lien YouTube valide.")
        return
    
    # Recherche des sous-titres
    results = search_in_subtitles(video_id, phrase)
    
    if results:
        await ctx.send("\n".join(results))
    else:
        await ctx.send("Aucun résultat trouvé.")

# Lancer le bot
bot.run(TOKEN_DISCORD)