import os
import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from playwright.async_api import async_playwright

# ⛔️ Ne mets plus: from playwright_stealth import Stealth

async def launch():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        # ...
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

active_sessions = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def cmd_chess(ctx, url: str):
    await ctx.send("🔴 Lancement du navigateur et du live...")
    asyncio.create_task(launch_browser(ctx.channel.id, url))  # ne bloque pas
    await ctx.send("🎥 Live disponible ici : **`/live`** (ou lien Railway)\n⚠️ Active pendant 5 minutes.")

async def launch_browser(channel_id: int, url: str):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--start-maximized',
                '--display=:0'
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        active_sessions[channel_id] = {"page": page, "context": context, "browser": browser}

        try:
            await page.goto("https://www.chess.com/login_and_go", timeout=60000)
            await page.wait_for_timeout(5000)
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(120000)  # laisser 2 min de visualisation
        except Exception as e:
            print("[Erreur navigateur]:", e)

        await context.close()
        await browser.close()
        active_sessions.pop(channel_id, None)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())