@@ -6,7 +6,7 @@
 import asyncio
 from enum import Enum, auto
 from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
-from playwright_stealth import Stealth  # ✅ Utilisation correcte
+from playwright_stealth import Stealth
 import io
 from pathlib import Path
 
@@ -45,7 +45,7 @@ async def get_pgn_from_chess_com(url: str, username: str, password: str) -> (str
     max_retries = 3
     browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
 
-    stealth = Stealth()  # ✅ Nouvelle instance
+    stealth = Stealth()
 
     async with stealth.use_async(async_playwright()) as p:
         browser = await p.chromium.launch(headless=True, args=browser_args)
@@ -68,18 +68,18 @@ async def get_pgn_from_chess_com(url: str, username: str, password: str) -> (str
 
                 try:
                     await page.get_by_role("button", name="I Accept").click(timeout=5000)
-                except PlaywrightTimeoutError:
+                except TimeoutError:
                     pass
 
                 await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
                 await page.get_by_placeholder("Password").type(password, delay=50)
                 await page.get_by_role("button", name="Log In").click()
-                
+
                 try:
                     await page.wait_for_url("**/home", timeout=15000)
                     login_successful = True
                     break
-                except PlaywrightTimeoutError:
+                except TimeoutError:
                     if await page.is_visible("text=This password is incorrect"):
                         continue
                     else:
@@ -195,13 +195,27 @@ async def send_last_video(ctx):
     video_path_str = last_video_paths.get(ctx.channel.id)
     if not video_path_str:
         return await ctx.send("❌ Aucune vidéo récente trouvée.")
+
     video_file = Path(video_path_str)
     if not video_file.exists():
         return await ctx.send("❌ Fichier vidéo introuvable.")
-    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
+
+    size = video_file.stat().st_size
+    if size <= DISCORD_FILE_LIMIT_BYTES:
         await ctx.send("📹 Voici la vidéo de la dernière opération `!chess` :", file=discord.File(str(video_file), "debug_video.webm"))
     else:
-        await ctx.send(f"📹 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")
+        await ctx.send(f"📦 La vidéo est trop lourde ({size / 1_000_000:.2f} Mo), découpage en cours...")
+
+        chunk_size = DISCORD_FILE_LIMIT_BYTES
+        with open(video_file, "rb") as f:
+            index = 1
+            while True:
+                chunk = f.read(chunk_size)
+                if not chunk:
+                    break
+                file = discord.File(io.BytesIO(chunk), filename=f"partie_{index}.webm")
+                await ctx.send(f"📹 Partie {index} de la vidéo :", file=file)
+                index += 1
 
 @bot.command(name="motcle")
 @commands.has_permissions(administrator=True)