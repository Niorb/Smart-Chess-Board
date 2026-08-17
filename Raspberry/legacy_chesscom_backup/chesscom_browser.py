"""
chesscom_browser.py

Playwright-based browser automation for chess.com.
Handles session persistence, login detection, game seeking, and color detection.

This module is asynchronous and has no GPIO/LED knowledge.
It is imported by game_seeker.py and app/chess_engine_async.py.
"""

import asyncio
import os
import time

try:
    from chesscom_config import (
        BROWSER_LOCALE,
        CHESS_COM_PLAY_URL,
        GAME_SEARCH_TIMEOUT,
        LOCATORS,
        MOVE_CLICK_DELAY_S,
        POLL_INTERVAL,
        TIME_CONTROL,
        USER_DATA_DIR,
        VIEWPORT_HEIGHT,
        VIEWPORT_WIDTH,
    )
except ImportError:
    from .chesscom_config import (
        BROWSER_LOCALE,
        CHESS_COM_PLAY_URL,
        GAME_SEARCH_TIMEOUT,
        LOCATORS,
        MOVE_CLICK_DELAY_S,
        POLL_INTERVAL,
        TIME_CONTROL,
        USER_DATA_DIR,
        VIEWPORT_HEIGHT,
        VIEWPORT_WIDTH,
    )

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

_playwright_instance = None


async def launch(headless=True):
    global _playwright_instance
    user_data_dir = os.path.abspath(USER_DATA_DIR)

    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()

    context = await _playwright_instance.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=headless,
        locale=BROWSER_LOCALE,
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        args=[
            f"--lang={BROWSER_LOCALE}",
            "--disable-gpu",
            "--disable-extensions",
            "--no-first-run",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--shm-size=1gb",
            "--single-process",
            "--disable-setuid-sandbox",
            "--js-flags=--max-old-space-size=256",
            "--memory-pressure-off",
            "--disable-features=TranslateUI,BlinkGenPropertyTrees",
            "--disable-ipc-flooding-protection",
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def close(browser_context):
    global _playwright_instance
    try:
        if browser_context:
            await browser_context.close()
    except Exception:
        pass
    try:
        if _playwright_instance:
            await _playwright_instance.stop()
            _playwright_instance = None
    except Exception:
        pass


async def is_logged_in(page):
    if CHESS_COM_PLAY_URL not in page.url:
        await page.goto(CHESS_COM_PLAY_URL)
        await page.wait_for_load_state("domcontentloaded", timeout=60000)

    return "/login" not in page.url and "/register" not in page.url


async def do_first_login():
    print()
    print("=" * 50)
    print("  FIRST-TIME LOGIN")
    print("=" * 50)
    print()
    print("A browser window will open — log in to chess.com.")
    print("Once logged in, come back here and press ENTER.")
    print()

    context, page = await launch(headless=False)
    await page.goto(CHESS_COM_PLAY_URL)

    input()

    logged_in = await is_logged_in(page)
    await close(context)

    if logged_in:
        print("Login saved successfully.")
    else:
        print("WARNING: Could not detect login. Try again.")

    return logged_in


async def navigate_to_play(page):
    if "/play" not in page.url:
        await page.goto(CHESS_COM_PLAY_URL)
        await page.wait_for_load_state("load")


async def seek_game(page, time_control=None):
    try:
        await navigate_to_play(page)

        if time_control:
            print(f"Selecting time control: {time_control}")
            import re
            dropdown_pattern = re.compile(r"^(?:\d+\s*min|\d+\s*\|\s*\d+)\s*\([^)]*\)$")
            try:
                trigger = page.get_by_text(dropdown_pattern)
                await trigger.click()
                await asyncio.sleep(0.5)
                selector = page.get_by_role("button", name=time_control, exact=True)
                await selector.first.click(timeout=8000)
                print(f"Selected time control: {time_control}")
            except Exception as e:
                print(f"WARNING: Dynamic time control selection failed ({e}), trying standard select...")
                try:
                    await page.get_by_role("button", name=time_control, exact=True).click(timeout=5000)
                except Exception:
                    pass
        else:
            try:
                await page.get_by_role(
                    "button", name=LOCATORS["time_control_show_options"]
                ).click(timeout=5000)
                await page.get_by_role("button", name=TIME_CONTROL, exact=True).click(
                    timeout=5000
                )
            except PlaywrightTimeout:
                print(
                    "WARNING: Could not find time control button, proceeding with default."
                )

        await page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click(
            timeout=10000
        )
        print("Searching for a game...")
        return True

    except PlaywrightTimeout:
        print("ERROR: Could not find the Play button on chess.com.")
        return False
    except Exception as e:
        print(f"ERROR: Failed to seek game: {e}")
        return False


async def wait_for_game(page, timeout=None, cancel_event=None):
    if timeout is None:
        timeout = GAME_SEARCH_TIMEOUT

    deadline = time.time() + timeout
    board_locator = page.locator(LOCATORS["board_container"])

    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            return None

        try:
            if await board_locator.is_visible():
                return True
        except Exception:
            pass

        if cancel_event:
            if isinstance(cancel_event, asyncio.Event):
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(POLL_INTERVAL)
        else:
            await asyncio.sleep(POLL_INTERVAL)

    print("Search timed out — no game found.")
    return False


async def cancel_search(page):
    try:
        await page.get_by_role("button", name=LOCATORS["cancel_search"]).click(timeout=5000)
        print("Search cancelled.")
        return True
    except PlaywrightTimeout:
        print("WARNING: Could not find cancel button.")
        return False


async def detect_my_color(page):
    flipped_classes = LOCATORS["board_flipped_class"].split()
    board_selector = LOCATORS["board_container"]

    try:
        board = await page.query_selector(board_selector)
        if board:
            class_attr = (await board.get_attribute("class")) or ""
            element_classes = class_attr.split()
            is_flipped = all(cls in element_classes for cls in flipped_classes)
            color = "black" if is_flipped else "white"
            print(f"Game found! Playing as {color.upper()}.")
            return color
        else:
            print("WARNING: Board element not found, defaulting to white.")
            return "white"
    except Exception as e:
        print(f"WARNING: Could not detect color ({e}), defaulting to white.")
        return "white"


async def read_board(page):
    PIECE_CODES = {
        "wp", "wr", "wn", "wb", "wq", "wk",
        "bp", "br", "bn", "bb", "bq", "bk",
    }

    piece_map = [["." for _ in range(8)] for _ in range(8)]
    pieces_selector = LOCATORS["board_container"] + " .piece"

    try:
        elements = await page.query_selector_all(pieces_selector)
        for el in elements:
            class_attr = (await el.get_attribute("class")) or ""
            classes = class_attr.split()

            piece_code = None
            square_code = None
            for cls in classes:
                if cls in PIECE_CODES:
                    piece_code = cls
                elif cls.startswith("square-") and len(cls) == 9:
                    square_code = cls[7:]

            if not piece_code or not square_code:
                continue

            file_n = int(square_code[0])
            rank_n = int(square_code[1])
            col = file_n - 1
            row = rank_n - 1

            if not (0 <= row <= 7 and 0 <= col <= 7):
                continue

            color, piece = piece_code[0], piece_code[1]
            piece_map[row][col] = piece.upper() if color == "w" else piece

    except Exception as e:
        print(f"WARNING: Could not read board ({e})")

    return piece_map


def print_board(piece_map, color="white"):
    print()
    if color == "black":
        print("    h g f e d c b a")
        print("   ----------------")
        for rank in range(1, 9):
            row = rank - 1
            row_str = " ".join(reversed(piece_map[row]))
            print(f" {rank}| {row_str}")
    else:
        print("    a b c d e f g h")
        print("   ----------------")
        for rank in range(8, 0, -1):
            row = rank - 1
            row_str = " ".join(piece_map[row])
            print(f" {rank}| {row_str}")
    print()


async def read_clocks(page, color="white"):
    async def read_clock(selector):
        if not selector:
            return None
        try:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                return text.strip()
        except Exception:
            pass
        return None

    white = await read_clock(LOCATORS.get(f"white_clock_{color}"))
    black = await read_clock(LOCATORS.get(f"black_clock_{color}"))

    if not white or white == "?":
        sel = "#board-layout-player-bottom .clock-component" if color == "white" else "#board-layout-player-top .clock-component"
        white = (await read_clock(sel)) or "?"

    if not black or black == "?":
        sel = "#board-layout-player-top .clock-component" if color == "white" else "#board-layout-player-bottom .clock-component"
        black = (await read_clock(sel)) or "?"

    return white, black


async def make_move(page, from_file, from_rank, to_file, to_rank, color):
    try:
        box = await page.locator(LOCATORS["board_container"]).bounding_box()
        if box is None:
            print("ERROR: Board not visible, cannot make move.")
            return False

        sq_w = box["width"] / 8
        sq_h = box["height"] / 8

        if color == "white":
            def to_pixel(file, rank):
                x = box["x"] + (file - 1) * sq_w + sq_w / 2
                y = box["y"] + (8 - rank) * sq_h + sq_h / 2
                return x, y
        else:
            def to_pixel(file, rank):
                x = box["x"] + (8 - file) * sq_w + sq_w / 2
                y = box["y"] + (rank - 1) * sq_h + sq_h / 2
                return x, y

        src_x, src_y = to_pixel(from_file, from_rank)
        dst_x, dst_y = to_pixel(to_file, to_rank)

        await page.mouse.click(src_x, src_y)
        await asyncio.sleep(MOVE_CLICK_DELAY_S)
        await page.mouse.click(dst_x, dst_y)

        return True

    except Exception as e:
        print(f"ERROR: make_move failed ({e})")
        return False
