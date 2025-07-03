import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

active_sessions = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def start_chess(ctx, url: str):
    if ctx.channel.id in active_sessions:
        return await ctx.send("⚠️ Une session est déjà en cours.")
    
    await ctx.send("📸 Lancement du navigateur et début des captures...")
    task = asyncio.create_task(capture_loop(ctx, url))
    active_sessions[ctx.channel.id] = task

@bot.command(name="stop")
async def stop_chess(ctx):
    task = active_sessions.pop(ctx.channel.id, None)
    if task:
        task.cancel()
        await ctx.send("🛑 Capture arrêtée.")
    else:
        await ctx.send("❌ Aucune capture active.")

async def capture_loop(ctx, url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        try:
            await page.goto("https://www.chess.com/login_and_go", timeout=60000)
            await page.get_by_placeholder("Username, Phone, or Email").fill(CHESS_USERNAME)
            await page.get_by_placeholder("Password").fill(CHESS_PASSWORD)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_timeout(2000)
            await page.goto(url, timeout=60000)

            count = 0
            while ctx.channel.id in active_sessions:
                path = f"/tmp/screenshot_{ctx.channel.id}_{count}.png"
                await page.screenshot(path=path)
                await ctx.send(file=discord.File(path))
                count += 1
                await asyncio.sleep(2)

        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

        await context.close()
        await browser.close()
        active_sessions.pop(ctx.channel.id, None)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())