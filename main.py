import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

async def handle_initial_blockers(page: Page, attempt: int = 1):
    """
    Attempts to handle common initial blockers like cookie consent pop-ups.
    Incorporates iframe handling and retries.
    """
    if attempt > 5: # Limit attempts to prevent infinite loops
        print(f"INFO: [Initial Load (Attempt {attempt})] Exceeded max attempts for blocker handling.")
        return False

    print(f"INFO: [Initial Load (Attempt {attempt})] AI-like blocker handler: Checking for common pop-ups...")

    # Define a list of potential cookie/accept button selectors
    # Add more selectors if needed based on the target website's HTML
    selectors = [
        'button:has-text("I Accept")',
        'button:has-text("J\'accepte")', # French acceptance
        '[aria-label="Accept"]',
        '[aria-label="J\'accepte"]',
        '[data-testid="accept-button"]',
        'button[class*="accept"], .accept-button', # Generic class-based selectors
        'div[role="button"]:has-text("I Accept")',
        'div[role="button"]:has-text("J\'accepte")',
        '#onetrust-accept-btn-handler', # Specific to OneTrust cookie banners
        'button.qc-cmp2-summary-tapbtn', # Specific to Quantcast Choice cookie banners
        '#consent-accept-button' # Another common one
    ]

    # Potential iframe selectors for cookie consent
    iframe_selectors = [
        'iframe[title*="Privacy"]',
        'iframe[name*="privacy"]',
        'iframe[src*="privacy-policy"]',
        'iframe[src*="cookie-consent"]',
        'iframe[id*="sp_message_container"]', # Sourcepoint
        'iframe[title*="cookie"]',
        'iframe' # Last resort, general iframe
    ]

    blocker_handled = False

    # Try to find and click cookie buttons directly on the page
    for selector in selectors:
        try:
            # Check if the button is visible and click it
            if await page.locator(selector).is_visible(timeout=2000): # Short timeout for visibility check
                await page.locator(selector).click(timeout=5000) # Longer timeout for click
                print(f"INFO: [Initial Load (Attempt {attempt})] Clicked cookie/accept button with selector '{selector}'.")
                blocker_handled = True
                break # Exit after clicking one
        except PlaywrightTimeoutError:
            print(f"WARNING: [Initial Load (Attempt {attempt})] Cookie/accept button with selector '{selector}' not found or not visible within timeout.")
        except PlaywrightError as e:
            print(f"WARNING: [Initial Load (Attempt {attempt})] Error clicking cookie/accept button with selector '{selector}': {e}")
        except Exception as e:
            print(f"WARNING: [Initial Load (Attempt {attempt})] Unexpected error clicking cookie/accept button with selector '{selector}': {e}")

    if blocker_handled:
        return True

    # If not handled directly, check inside iframes
    print(f"INFO: [Initial Load (Attempt {attempt})] Checking for cookie buttons inside iframes...")
    for iframe_sel in iframe_selectors:
        try:
            iframe_element = page.frame_locator(iframe_sel)
            if iframe_element:
                print(f"INFO: [Initial Load (Attempt {attempt})] Found potential iframe with selector '{iframe_sel}'. Checking for cookie button inside.")
                for selector in selectors:
                    try:
                        # Check if the button is visible inside the iframe and click it
                        if await iframe_element.locator(selector).is_visible(timeout=2000):
                            await iframe_element.locator(selector).click(timeout=5000)
                            print(f"INFO: [Initial Load (Attempt {attempt})] Clicked cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}'.")
                            blocker_handled = True
                            break # Exit after clicking one in iframe
                    except PlaywrightTimeoutError:
                        # Button not found in this iframe, try next selector/iframe
                        pass
                    except PlaywrightError as e:
                        print(f"WARNING: [Initial Load (Attempt {attempt})] Error clicking cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}': {e}")
                    except Exception as e:
                        print(f"WARNING: [Initial Load (Attempt {attempt})] Unexpected error clicking cookie/accept button with selector '{selector}' inside iframe '{iframe_sel}': {e}")
            if blocker_handled:
                break # Exit after handling in an iframe
        except PlaywrightTimeoutError:
            # Iframe not found, try next iframe selector
            pass
        except PlaywrightError as e:
            print(f"WARNING: [Initial Load (Attempt {attempt})] Error locating/accessing iframe {iframe_sel}: {e}")
        except Exception as e:
            print(f"WARNING: [Initial Load (Attempt {attempt})] Unexpected error with iframe {iframe_sel}: {e}")

    if blocker_handled:
        return True

    # Add other specific pop-up handlers here if necessary (e.g., "Aw, Snap!" or specific site pop-ups)
    # Note: The 'Frame.is_visible() got an unexpected keyword argument 'timeout'' error
    #       for generic/Chess.com pop-ups likely goes away with Playwright update.
    #       If it persists, those specific handler functions need correction.
    try:
        # Example: Chess.com specific pop-up (if not covered by generic cookie banners)
        # You'll need to inspect Chess.com's current pop-ups if they exist
        # Example: await page.locator(".modal-close-button").click(timeout=2000)
        pass # No specific handler for now
    except PlaywrightTimeoutError:
        pass
    except PlaywrightError as e:
        print(f"WARNING: [Initial Load (Attempt {attempt})] Error handling Chess.com specific pop-up: {e}")
    except Exception as e:
        print(f"ERROR: [Initial Load (Attempt {attempt})] Error handling 'Aw, Snap!' elements: {e}")


    print(f"INFO: [Initial Load (Attempt {attempt})] No known blockers handled after all strategies.")
    print(f"INFO: Initial blocker still present after attempt {attempt}. Waiting 2 seconds and retrying...")
    await asyncio.sleep(2)
    return await handle_initial_blockers(page, attempt + 1) # Retry

