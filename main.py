import os
import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from playwright.async_api import async_playwright

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

VNC_PUBLIC_URL = "https://worker-production-22ad.up.railway.app/vnc_lite.html"

active_sessions = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def cmd_chess(ctx, url: str):
    await ctx.send("🟢 Lancement du navigateur et du live...")
    asyncio.create_task(launch_browser(ctx.channel.id, url))
    await ctx.send(f"🎥 Live en cours ici : {VNC_PUBLIC_URL}\n⚠️ Actif ~5 minutes.")

async def launch_browser(channel_id: int, url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--start-maximized",
                "--display=:0"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        active_sessions[channel_id] = {"page": page, "context": context, "browser": browser}

        try:
            await page.goto("https://www.chess.com/login_and_go", timeout=60000)
            await page.wait_for_timeout(2000)

            await page.get_by_placeholder("Username, Phone, or Email").fill(CHESS_USERNAME)
            await page.get_by_placeholder("Password").fill(CHESS_PASSWORD)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)

            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(120000)  # Laisse visible 2 min

        except Exception as e:
            print(f"[Erreur navigateur] : {e}")

        await context.close()
        await browser.close()
        active_sessions.pop(channel_id, None)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)} ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())