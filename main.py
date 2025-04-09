import discord
from discord.ext import commands
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import os

# Configuration du bot
TOKEN_DISCORD = os.getenv('TOKEN_DISCORD')  # Récupère le token depuis les variables d'environnement
intents = discord.Intents.default()
intents.message_content = True  # Assure-toi que l'intent pour le contenu des messages est activé

bot = commands.Bot(command_prefix="!", intents=intents)

# Fonction pour extraire l'ID de la vidéo à partir de l'URL
def get_video_id(url):
    if "youtube.com/watch?v=" in url:
        return url.split("v=")[-1]
    return None

# Fonction pour rechercher la phrase dans les sous-titres
def search_in_subtitles(video_id, phrase):
    try:
        # Récupérer les sous-titres de la vidéo
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['fr', 'en'])

        results = []
        # Afficher tous les sous-titres récupérés pour déboguer
        print("Sous-titres récupérés:")
        for entry in transcript:
            print(entry['start'], entry['text'])  # Affiche l'heure et le texte des sous-titres

        # Chercher la phrase dans les sous-titres
        for entry in transcript:
            if phrase.lower() in entry['text'].lower():
                time = int(entry['start'])
                results.append(f"À {time//60}:{time%60:02d} — {entry['text']}")
        
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