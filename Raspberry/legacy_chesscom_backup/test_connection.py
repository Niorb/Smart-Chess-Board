#!/usr/bin/env python3
"""
test_connection.py

A standalone diagnostic script to verify the Playwright-based Chess.com connection.
This script has no dependencies on GPIO pins or WS2812B LEDs, making it ideal for
testing on a local development machine (like Windows/macOS) before deploying to the Raspberry Pi.

Usage:
  python playwright_chesscom/test_connection.py            # Headless connection test
  python playwright_chesscom/test_connection.py --visible  # Visible browser connection test
  python playwright_chesscom/test_connection.py --login    # First-time login / session setup
"""

import argparse
import asyncio
import os
import sys

# Ensure we can import modules from this directory regardless of execution context
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from chesscom_browser import (
    close,
    do_first_login,
    is_logged_in,
    launch,
    navigate_to_play,
)
from chesscom_config import CHESS_COM_PLAY_URL, TIME_CONTROL, USER_DATA_DIR


async def run_test(headless=True, force_login=False):
    print("=" * 60)
    print("        CHESS.COM PLAYWRIGHT CONNECTION TESTER")
    print("=" * 60)

    # Show configuration
    abs_session_path = os.path.abspath(USER_DATA_DIR)
    print(f"[*] Session data path: {abs_session_path}")
    print(f"[*] Target play URL:   {CHESS_COM_PLAY_URL}")
    print(f"[*] Time control:      {TIME_CONTROL}")
    print("-" * 60)

    # 1. Handle explicit login routine
    if force_login:
        print("[*] Running login setup (opening a visible browser)...")
        success = await do_first_login()
        if success:
            print("[+] Login verified and saved successfully!")
        else:
            print("[-] Login verification failed. Please try again.")
        return

    # 2. Regular Connection Test
    print(f"[*] Launching browser (headless={headless})...")
    context = None
    try:
        context, page = await launch(headless=headless)
        print("[+] Browser launched successfully!")
    except Exception as e:
        print(f"[-] ERROR: Failed to launch browser: {e}")
        print("\nPossible solutions:")
        print("  1. Ensure Playwright is installed: pip install playwright")
        print("  2. Install Chromium binaries: playwright install chromium")
        return

    try:
        # Check login status
        print("[*] Navigating to Chess.com and checking login status...")
        logged_in = await is_logged_in(page)

        if logged_in:
            print("[+] STATUS: Logged in!")
            print(f"[*] Current Page URL: {page.url}")

            # Test navigation to play page
            print("[*] Navigating to Play Online section...")
            await navigate_to_play(page)
            page_title = await page.title()
            print(f"[+] Loaded: {page_title} ({page.url})")

            # Wait for a couple of seconds to ensure page stabilizes
            await asyncio.sleep(2)
            print("[+] Test completed successfully! Playwright connection is operational.")
        else:
            print("[-] STATUS: NOT Logged in.")
            print("\nTo log in and save your session cookies:")
            print("  Run this script with the --login flag:")
            print("  python playwright_chesscom/test_connection.py --login")

    except Exception as e:
        print(f"[-] ERROR: Exception occurred during connection test: {e}")
    finally:
        if context:
            print("[*] Closing browser...")
            await close(context)
            print("[+] Browser closed.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Playwright connection to Chess.com.")
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run the browser in visible (non-headless) mode for debugging."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open a visible browser to perform the first-time login process."
    )
    args = parser.parse_args()

    headless_mode = not args.visible
    asyncio.run(run_test(headless=headless_mode, force_login=args.login))
