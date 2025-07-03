import os
import asyncio
from pathlib import Path
from discord.ext import commands
import discord
from playwright.async_api import async_playwright

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

screenshots_dir = Path("screenshots")
screenshots_dir.mkdir(exist_ok=True)

active_capture_tasks = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def start_chess_capture(ctx, url: str):
    if ctx.channel.id in active_capture_tasks:
        await ctx.send("⚠️ Capture déjà en cours.")
        return

    task = asyncio.create_task(capture_loop(ctx, url))
    active_capture_tasks[ctx.channel.id] = task
    await ctx.send(f"📸 Capture d'écran toutes les 2 secondes sur `{url}`.\nUtilise `!stop` pour arrêter.")

async def capture_loop(ctx, url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        try:
            await page.goto("https://www.chess.com/login_and_go")
            await page.get_by_placeholder("Username, Phone, or Email").fill(CHESS_USERNAME)
            await page.get_by_placeholder("Password").fill(CHESS_PASSWORD)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)
            await page.goto(url)

            count = 0
            while ctx.channel.id in active_capture_tasks:
                screenshot_path = screenshots_dir / f"capture_{ctx.channel.id}_{count}.png"
                await page.screenshot(path=str(screenshot_path))
                await ctx.send(file=discord.File(str(screenshot_path)))
                count += 1
                await asyncio.sleep(2)

        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

        await context.close()
        await browser.close()
        active_capture_tasks.pop(ctx.channel.id, None)

@bot.command(name="stop")
async def stop_capture(ctx):
    task = active_capture_tasks.pop(ctx.channel.id, None)
    if task:
        task.cancel()
        await ctx.send("🛑 Capture arrêtée.")
    else:
        await ctx.send("❌ Aucune capture en cours.")

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())