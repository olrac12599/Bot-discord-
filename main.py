import asyncio
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

# Assuming these are defined elsewhere or need to be implemented
# For this corrected main.py, I'm providing placeholder functions.
# You should replace these with your actual Xvfb and FFmpeg implementations.
async def start_xvfb():
    # Placeholder: Replace with your actual Xvfb startup logic
    # Example: return await asyncio.create_subprocess_exec("Xvfb", ":99", "-screen", "0", "1920x1080x24")
    print("Placeholder: Xvfb started.")
    class MockProcess:
        returncode = None
        def terminate(self):
            print("Placeholder: Xvfb terminated.")
            self.returncode = 0
        async def wait(self):
            print("Placeholder: Waiting for Xvfb to terminate.")
    return MockProcess()

async def start_ffmpeg_capture():
    # Placeholder: Replace with your actual FFmpeg startup logic
    # Example:
    # command = ["ffmpeg", "-f", "x11grab", "-s", "1920x1080", "-i", ":99.0", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"]
    # process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    # This is a simplified mock. Your actual ffmpeg_reader_thread would read from process.stdout.
    print("Placeholder: FFmpeg capture started.")
    class MockProcess:
        returncode = None
        def terminate(self):
            print("Placeholder: FFmpeg terminated.")
            self.returncode = 0
        async def wait(self):
            print("Placeholder: Waiting for FFmpeg to terminate.")
    class MockThread:
        should_stop = False
        def is_alive(self): return False # Mock thread is never really alive for this placeholder
        def join(self, timeout=None): pass
    
    current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = f"capture_{current_time_str}.mp4"
    return MockProcess(), video_filename, asyncio.Queue(), MockThread()

# --- Playwright specific imports ---
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# --- Logging Configuration ---
# Ensure your logging is configured correctly if not already.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Log to console
        # logging.FileHandler("app.log") # Uncomment to also log to a file
    ]
)
logger = logging.getLogger(__name__)

# --- Custom Exception ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

# --- Global Configuration (Replace with your actual credentials) ---
CHESS_USERNAME = os.getenv("CHESS_USERNAME", "your_chess_username")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD", "your_chess_password")
# Make sure to set these environment variables or replace directly for testing.

# --- Blocker Handling Function (Improved) ---
async def handle_initial_blockers(page: Page, attempt: int = 1):
    """
    Attempts to handle common initial blockers like cookie consent pop-ups.
    Incorporates iframe handling and retries.
    """
    if attempt > 5:  # Limit attempts to prevent infinite loops
        logger.info(f"[Initial Load (Attempt {attempt})] Exceeded max attempts for blocker handling.")
        return False # Blocker not handled after max attempts

    logger.info(f"[Initial Load (Attempt {attempt})] AI-like blocker handler: Checking for common pop-ups...")

    # Define a list of potential cookie/accept button selectors
    # These are common. Add more specific ones if you find them by inspecting Chess.com.
    selectors = [
        'button:has-text("I Accept")',
        'button:has-text("J\'accepte")',  # French acceptance
        '[aria-label="Accept"]',
        '[aria-label="J\'accepte"]',
        '[data-testid="accept-button"]',
        'button[class*="accept"], .accept-button',  # Generic class-based selectors
        'div[role="button"]:has-text("I Accept")',
        'div[role="button"]:has-text("J\'accepte")',
        '#onetrust-accept-btn-handler',  # Specific to OneTrust cookie banners
        'button.qc-cmp2-summary-tapbtn',  # Specific to Quantcast Choice cookie banners
        '#consent-accept-button',
        'button[id*="consent"][class*="accept"]', # More generic consent button
        'a[class*="button"][text*="Accept"]', # If it's an anchor tag
    ]

    # Potential iframe selectors for cookie consent
    iframe_selectors = [
        'iframe[title*="Privacy"]',
        'iframe[name*="privacy"]',
        'iframe[src*="privacy-policy"]',
        'iframe[src*="cookie-consent"]',
        'iframe[id*="sp_message_container"]',  # Sourcepoint
        'iframe[title*="cookie"]',
        'iframe[src*="youtube.com"]', # Sometimes YouTube embeds have their own cookie consent
        'iframe' # Last resort, general iframe
    ]

    blocker_handled = False

    # Try to find and click cookie buttons directly on the page
    for selector in selectors:
        try:
            # Check if the button is visible and click it
            # Short timeout for is_visible to quickly check existence
            if await page.locator(selector).is_visible(timeout=1000): # Reduced timeout for quick check
                await page.locator(selector).click(timeout=3000) # Longer timeout for click action
                logger.info(f"[Initial Load (Attempt {attempt})] Clicked cookie/accept button with selector '{selector}'.")
                blocker_handled = True
                break  # Exit after clicking one
        except PlaywrightTimeoutError:
            # Not found or not visible within the short timeout, continue to next selector
            pass
        except PlaywrightError as e:
            logger.warning(f"[Initial Load (Attempt {attempt})] Error clicking cookie/accept button with selector '{selector}': {e}")
        except Exception as e:
            logger.warning(f"[Initial Load (Attempt {attempt})] Unexpected error clicking cookie/accept button with selector '{selector}': {e}")

    if blocker_handled:
        await asyncio.sleep(1) # Give a moment for the banner to disappear
        return True

    # If not handled directly, check inside iframes
    logger.info(f"[Initial Load (Attempt {attempt})] Checking for cookie buttons inside iframes...")
    for iframe_sel in iframe_selectors:
        try:
            iframe_element = page.frame_locator(iframe_sel)
            if iframe_element: # Ensure the iframe element locator was found
                logger.info(f"[Initial Load (Attempt {attempt})] Found potential iframe with selector '{iframe_sel}'. Checking for cookie button inside.")
                for selector in selectors:
                    try:
                        if await iframe_element.locator(selector).is_visible(timeout=1000):
                            await iframe_element.locator(selector).click(timeout=3000)
                            logger.info(f"[Initial Load (Attempt {attempt})] Clicked cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}'.")
                            blocker_handled = True
                            break  # Exit after clicking one in iframe
                    except PlaywrightTimeoutError:
                        pass # Button not found in this iframe, try next selector/iframe
                    except PlaywrightError as e:
                        logger.warning(f"[Initial Load (Attempt {attempt})] Error clicking cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}': {e}")
                    except Exception as e:
                        logger.warning(f"[Initial Load (Attempt {attempt})] Unexpected error clicking cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}': {e}")
            if blocker_handled:
                break  # Exit after handling in an iframe
        except PlaywrightTimeoutError:
            pass # Iframe not found, try next iframe selector
        except PlaywrightError as e:
            logger.warning(f"[Initial Load (Attempt {attempt})] Error locating/accessing iframe {iframe_sel}: {e}")
        except Exception as e:
            logger.warning(f"[Initial Load (Attempt {attempt})] Unexpected error with iframe {iframe_sel}: {e}")

    if blocker_handled:
        await asyncio.sleep(1) # Give a moment for the banner to disappear
        return True

    # Generic pop-up closers (e.g., modals, signup prompts that are not cookies)
    # Add selectors for common "X" buttons or "No Thanks" type elements.
    generic_closers = [
        '[aria-label="Close"]', # Common for close buttons
        'button.close',
        '.modal-close-button',
        'div[role="button"][aria-label="Close"]',
        'button:has-text("No Thanks")',
        'button:has-text("Later")',
        'a[aria-label="Close"]',
    ]
    for closer_selector in generic_closers:
        try:
            if await page.locator(closer_selector).is_visible(timeout=1000):
                await page.locator(closer_selector).click(timeout=3000)
                logger.info(f"[Initial Load (Attempt {attempt})] Clicked generic closer with selector '{closer_selector}'.")
                blocker_handled = True
                await asyncio.sleep(0.5) # Small pause
                if blocker_handled: break
        except PlaywrightTimeoutError:
            pass
        except PlaywrightError as e:
            logger.warning(f"[Initial Load (Attempt {attempt})] Error clicking generic closer '{closer_selector}': {e}")

    if blocker_handled:
        return True

    # Specific Chess.com pop-up handlers (if any are known and not covered by generic)
    # You might need to add specific selectors for Chess.com's unique modals or upsells.
    try:
        # Example for a specific Chess.com pop-up (verify with inspection)
        # await page.locator('.some-chesscom-specific-modal-close-button').click(timeout=2000)
        pass # No specific Chess.com handler added by default here, as they change.
    except PlaywrightTimeoutError:
        pass
    except PlaywrightError as e:
        logger.warning(f"[Initial Load (Attempt {attempt})] Error handling Chess.com specific pop-up: {e}")

    logger.info(f"[Initial Load (Attempt {attempt})] No known blockers handled after all strategies.")
    logger.info(f"Initial blocker still present after attempt {attempt}. Waiting 2 seconds and retrying...")
    await asyncio.sleep(2)
    return await handle_initial_blockers(page, attempt + 1) # Retry


# --- Main Scraping Function ---
async def get_pgn_from_chess_com(url: str, username: str, password: str) -> tuple[str, str]:
    video_path = None
    browser = None
    context = None
    page = None
    xvfb_process = None
    ffmpeg_process = None
    ffmpeg_reader_thread = None # Define outside try for finally block

    try:
        # 1. Start Xvfb and FFmpeg for screen recording
        logger.info("Starting Xvfb on display :99...")
        xvfb_process = await start_xvfb()
        logger.info("Xvfb started successfully.")

        logger.info("Starting FFmpeg to capture Xvfb display...")
        ffmpeg_process, video_path, frame_queue, ffmpeg_reader_thread = await start_ffmpeg_capture()
        logger.info("FFmpeg capture process started.")
        if ffmpeg_reader_thread: # Check if thread was actually created
            logger.info("FFmpeg frame reader thread started.")
        else:
            logger.warning("FFmpeg frame reader thread not initiated correctly.")

        async with async_playwright() as p:
            logger.info("Launching Chromium with Playwright...")
            browser = await p.chromium.launch(
                headless=True, # Set to False for visual debugging if needed (requires X server access)
                args=['--no-sandbox', '--disable-setuid-sandbox'] # Essential for many Linux environments (e.g., Docker)
            )
            context = await browser.new_context(
                # Increase default timeout for actions, navigations, etc.
                timeout=90000, # Increased timeout to 90 seconds
                # Add a user-agent to mimic a real browser more closely
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 2. Navigate to Login Page
            logger.info("Navigating to login page...")
            try:
                await page.goto("https://www.chess.com/login", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_load_state('networkidle', timeout=60000) # Wait for network to settle
            except PlaywrightTimeoutError:
                logger.error("Timeout navigating to login page.")
                raise ScrapingError("Failed to load login page.")

            # 3. Handle Initial Blockers (e.g., Cookie Consent)
            logger.info("Checking for initial blockers immediately after page load and before login attempts...")
            await handle_initial_blockers(page) # Call the improved handler

            # 4. Perform Login
            logger.info("Attempting login...")
            login_success = False
            for attempt in range(1, 4): # Max 3 login attempts
                logger.info(f"Login attempt {attempt}...")
                try:
                    # After blocker handling, ensure page is ready before finding elements
                    await page.wait_for_load_state('networkidle', timeout=30000)

                    username_field = page.get_by_placeholder("Username, Email or Phone") # Corrected Chess.com placeholder
                    password_field = page.get_by_placeholder("Password")
                    login_button = page.get_by_role("button", name="Log In")

                    # Wait for elements to be visible before interacting
                    await username_field.wait_for(state='visible', timeout=15000)
                    await password_field.wait_for(state='visible', timeout=15000)
                    await login_button.wait_for(state='visible', timeout=15000)

                    await username_field.fill(username)
                    await password_field.fill(password)
                    await login_button.click()

                    # Wait for navigation after login, or for a specific element indicating success
                    # Chess.com often redirects to /home or a dashboard
                    await page.wait_for_url("https://www.chess.com/home**", wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    logger.info("Successfully logged in.")
                    login_success = True
                    break # Exit login loop on success

                except PlaywrightTimeoutError as e:
                    logger.error(f"Login attempt {attempt} failed: Timeout ({e}). Reloading page and retrying...")
                    await page.reload(wait_until="domcontentloaded") # Reload page on failure
                except PlaywrightError as e:
                    logger.error(f"An unexpected Playwright error during login attempt {attempt}: {e}. Reloading page and retrying...")
                    await page.reload(wait_until="domcontentloaded") # Reload page on failure
                except Exception as e:
                    logger.error(f"An unknown error occurred during login attempt {attempt}: {e}. Reloading page and retrying...")
                    await page.reload(wait_until="domcontentloaded") # Reload page on failure

            if not login_success:
                raise ScrapingError("Failed to log in after multiple attempts.")

            # 5. Navigate to the Specific Game URL
            logger.info(f"Navigating to game URL: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_load_state('networkidle', timeout=60000) # Wait for the game page to fully load
            except PlaywrightTimeoutError:
                logger.error(f"Timeout navigating to game URL: {url}")
                raise ScrapingError(f"Failed to load game URL: {url}")
            except PlaywrightError as e:
                logger.error(f"Playwright error navigating to game URL {url}: {e}")
                raise ScrapingError(f"Playwright error loading game URL: {e}")

            # 6. Extract PGN
            logger.info("Attempting to extract PGN...")
            pgn = ""
            try:
                # Often, PGN is in a specific section. You may need to click 'Analysis' or 'Download' tab first.
                # Inspect Chess.com game page carefully for the exact path to PGN.

                # Common Chess.com PGN button/text area pattern:
                # 1. Look for a "Download" or "PGN" button to reveal the PGN
                download_pgn_button_selectors = [
                    'button[data-cy="game-actions-pgn-button"]', # Common button to open PGN panel
                    'div.game-view-buttons button:has-text("Download")',
                    'div.game-view-buttons button:has-text("PGN")',
                    '[aria-label*="download pgn"]',
                    'a[href*="/pgn/download/"]', # Direct download link if available
                ]

                pgn_text_area_selectors = [
                    'textarea.game-pgn-textarea', # Common PGN text area
                    'code.game-pgn-code', # Sometimes it's in a <code> block
                    'pre.pgn-notation', # Or <pre>
                    'div[data-cy="pgn-content"]',
                ]

                # Try clicking a button to reveal PGN if necessary
                for btn_sel in download_pgn_button_selectors:
                    try:
                        if await page.locator(btn_sel).is_visible(timeout=2000):
                            logger.info(f"Clicking PGN button with selector: {btn_sel}")
                            await page.locator(btn_sel).click(timeout=5000)
                            await page.wait_for_load_state('networkidle', timeout=10000) # Wait for modal/section to load
                            break # Button clicked, move to extraction
                    except PlaywrightTimeoutError:
                        pass # Button not found, try next
                    except PlaywrightError as e:
                        logger.warning(f"Error clicking PGN button {btn_sel}: {e}")

                # Now, attempt to extract PGN from a text area or code block
                for pgn_sel in pgn_text_area_selectors:
                    try:
                        pgn_element = page.locator(pgn_sel)
                        if await pgn_element.is_visible(timeout=5000):
                            pgn = await pgn_element.text_content()
                            if pgn.strip(): # Ensure PGN is not empty
                                logger.info("Successfully extracted PGN from text content.")
                                break # PGN found, exit loop
                            else:
                                logger.warning(f"Found PGN element with selector '{pgn_sel}' but it was empty.")
                    except PlaywrightTimeoutError:
                        pass # PGN element not found, try next
                    except PlaywrightError as e:
                        logger.warning(f"Error extracting PGN from {pgn_sel}: {e}")
                
                if not pgn.strip():
                    logger.error("PGN could not be extracted from any known selectors.")
                    raise ScrapingError("PGN extraction failed: No PGN content found.")

            except PlaywrightError as e:
                logger.error(f"Playwright error during PGN extraction: {e}")
                raise ScrapingError(f"PGN extraction failed due to Playwright error: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during PGN extraction: {e}")
                raise ScrapingError(f"PGN extraction failed due to an unexpected error: {e}")

        logger.info("Scraping completed successfully.")
        return pgn.strip(), video_path

    except ScrapingError as e:
        logger.error(f"Scraping Error: {e.args[0]}. Attempting to capture debug info.")
        screenshot_bytes = None
        if page and not page.is_closed(): # Ensure page is still open before trying to screenshot
            try:
                screenshot_bytes = await page.screenshot(full_page=True)
                logger.info("Debug screenshot captured.")
            except Exception as ss_e:
                logger.error(f"Error during debug screenshot capture: {ss_e}")
        raise ScrapingError(f"Scraping failed: {e.args[0]}", screenshot_bytes, video_path)
    except PlaywrightError as e:
        logger.error(f"A critical Playwright error occurred: {e}. Attempting to capture debug info.")
        screenshot_bytes = None
        if page and not page.is_closed():
            try:
                screenshot_bytes = await page.screenshot(full_page=True)
                logger.info("Debug screenshot captured.")
            except Exception as ss_e:
                logger.error(f"Error during debug screenshot capture: {ss_e}")
        raise ScrapingError(f"Critical Playwright error: {e}", screenshot_bytes, video_path)
    except Exception as e:
        logger.error(f"An unhandled critical error occurred: {e}. Attempting to capture debug info.")
        screenshot_bytes = None
        if page and not page.is_closed():
            try:
                screenshot_bytes = await page.screenshot(full_page=True)
                logger.info("Debug screenshot captured.")
            except Exception as ss_e:
                logger.error(f"Error during debug screenshot capture: {ss_e}")
        raise ScrapingError(f"An unexpected critical error occurred: {e}", screenshot_bytes, video_path)
    finally:
        # --- Resource Cleanup ---
        if browser:
            logger.info("Closing Playwright browser...")
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing Playwright browser: {e}")

        logger.info("Terminating FFmpeg process...")
        if ffmpeg_process and ffmpeg_process.returncode is None:
            try:
                ffmpeg_process.terminate()
                await asyncio.wait_for(ffmpeg_process.wait(), timeout=5) # Wait with timeout
            except asyncio.TimeoutError:
                logger.warning("FFmpeg process did not terminate gracefully, killing.")
                ffmpeg_process.kill()
            except Exception as e:
                logger.warning(f"Error terminating FFmpeg process: {e}")
        
        if ffmpeg_reader_thread and ffmpeg_reader_thread.is_alive():
            logger.info("Stopping FFmpeg frame reader thread...")
            # Signal the thread to stop if it has a `should_stop` flag
            if hasattr(ffmpeg_reader_thread, 'should_stop'):
                ffmpeg_reader_thread.should_stop = True
            ffmpeg_reader_thread.join(timeout=5) # Wait for thread to finish
            if ffmpeg_reader_thread.is_alive():
                logger.warning("FFmpeg frame reader thread did not terminate cleanly.")

        logger.info("Terminating Xvfb process...")
        if xvfb_process and xvfb_process.returncode is None:
            try:
                xvfb_process.terminate()
                await asyncio.wait_for(xvfb_process.wait(), timeout=5) # Wait with timeout
            except asyncio.TimeoutError:
                logger.warning("Xvfb process did not terminate gracefully, killing.")
                xvfb_process.kill()
            except Exception as e:
                logger.warning(f"Error terminating Xvfb process: {e}")
        
        logger.info("All browser, FFmpeg, and Xvfb processes cleaned up.")

# --- Example Usage (main execution block) ---
async def main():
    test_url = "https://www.chess.com/game/live/10900000000" # Replace with a valid Chess.com game URL
    
    # You might get these from environment variables or a config file
    # For testing, you can put them directly, but use environment variables for production.
    # CHESS_USERNAME = "your_username"
    # CHESS_PASSWORD = "your_password"

    if CHESS_USERNAME == "your_chess_username" or CHESS_PASSWORD == "your_chess_password":
        logger.error("Please set CHESS_USERNAME and CHESS_PASSWORD environment variables or update the script.")
        return

    try:
        pgn_data, video_output_path = await get_pgn_from_chess_com(test_url, CHESS_USERNAME, CHESS_PASSWORD)
        logger.info(f"Successfully scraped PGN:\n{pgn_data[:500]}...") # Print first 500 chars
        logger.info(f"Video recorded to: {video_output_path}")
    except ScrapingError as e:
        logger.error(f"Scraping operation failed: {e}")
        if e.screenshot_bytes:
            screenshot_filename = "debug_screenshot.png"
            with open(screenshot_filename, "wb") as f:
                f.write(e.screenshot_bytes)
            logger.error(f"Debug screenshot saved to {screenshot_filename}")
        if e.video_path:
            logger.error(f"Recorded video path: {e.video_path}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
