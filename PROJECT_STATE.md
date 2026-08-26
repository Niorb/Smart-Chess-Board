# PROJECT_STATE.md

## Current Sprint Goal
Maintain AI Sub-Agent Roster and Implement Smart Chess Board Core Features.

## Latest Change — Tactical Puzzles & Opponent Moves (The Side We Don't Play) (2026-08-26)
1. **Opponent Setup Move & Contextual Perspective (`coach_engine.py`, `board_state.py`)**:
   - `BlunderChallenge` and `extract_blunders()` now track:
     - `player_color` (the side we play to find the refutation) and `opponent_color` (the side we don't play).
     - `opponent_prev_move_san` and `opponent_prev_move_uci`: The initiating move played by the opponent leading into the puzzle position.
     - `solution_pv` & `solution_line_san`: Full multi-ply Grandmaster tactical solution line in SAN (e.g. `14. Nxe5! dxe5 15. Qxd8+`).
     - `player_moves` and `opponent_replies`: Separated sequences for player moves and opponent defensive replies (from the side we don't play!).
2. **Automatic Opponent Reply Execution & Multi-Step Puzzle Engine (`board_state.py`)**:
   - Starting a puzzle (`start_blunder_drill`) highlights the opponent's previous move on physical LEDs and the web board.
   - When a player submits their correct move, the backend automatically provides and executes the opponent's defensive reply (from the side we don't play), updating the active board, triggering arrival flashes and LED traces, and prompting for the next tactical move in multi-ply puzzles.
   - Upon completing the tactical sequence, returns the full Grandmaster solution line and congratulatory feedback.
3. **Interactive Web Board & Tactical UI (`AnalysisTab.tsx`, `useBoardState.ts`, `api.ts`)**:
   - Added interactive `WebAnalysisBoard` embedded directly inside Sub-view 2 (Blunder Blitz / Tactical Puzzles) supporting move clicks/drags.
   - Added perspective banner clearly showing "You play as White/Black" and "Opponent just played: [Move]".
   - Added "Opponent Response (Side we don't play)" notification card and full Grandmaster continuation line card.
4. **Automated Verification (`test_blunder_drill.py`)**:
   - Added `test_puzzle_opponent_moves_and_continuation` verifying extraction of opponent moves and execution of opponent replies.
   - Verified all 368 pytest test cases passing on the Raspberry Pi.

## Previous Change — Endgame Tablebase Trainer ("Endgame Academy") (2026-08-26)
1. **Curriculum & Tablebase Database (`endgame_db.py`)**:
   - Implemented 12-drill theoretical endgame curriculum across 4 core categories:
     - **Pawn Endgames**: Pawn Opposition & Key Squares, Rook Pawn Draw Fortress, Square of the Pawn Rule.
     - **Rook Endgames**: Lucena Position (Bridge Building), Philidor Defense (Passive 6th Rank Cutoff), Short Side Defense.
     - **Minor Piece Endgames**: King + Bishop + Knight Mate (W-Manouevre), King + Two Bishops Mate, Knight vs Outside Passed Pawn.
     - **Queen Endgames**: Queen vs Pawn on 7th (c/a-pawn stalemate trap), Queen vs Rook (Philidor Triangle).
   - Added persistence manager (`endgame_progress.json`, git-ignored) tracking 3-star rating, moves played vs par, accuracy %, and custom FEN user drills.
2. **Two-Phase Physical Piece Setup & Piece-Type LED Color Coding (`config.py`, `led_helpers.py`, `led_animations.py`, `board_state.py`)**:
   - Universal Piece-Type Color Palette (identical for White & Black):
     - ♔ King: Royal Gold (`#FFD700`)
     - ♕ Queen: Royal Violet (`#8C28F0`)
     - ♖ Rook: Azure Cyan (`#00A0FF`)
     - ♗ Bishop: Warm Sun Amber (`#DC8C00`)
     - ♘ Knight: Mint Emerald (`#00DC8C`)
     - ♙ Pawn: Pearl White (`#DCDCF0`)
   - Phase 1 (White Setup): Target squares glow in piece colors; misplaced pieces glow warning amber; correctly placed South-pole pieces lock in.
   - Transition: 0.8s warm Ivory wave (`render_white_setup_complete_wave`) sweeps across ranks 1–2 confirming White pieces.
   - Phase 2 (Black Setup): Target squares glow in same piece colors; placed North-pole pieces lock in.
   - Readiness: 0.5s emerald snap-flash (`BOARD_READY`) begins drill.
3. **Move Grading & Defense Reply Engine (`board_state.py`, `coach_engine.py`)**:
   - Optimal moves ($\le 10$ cp): Emerald Green confirmation flash (`COLOR_INT_MOVE_CONFIRM`).
   - Sub-optimal winning moves ($10 < \Delta \le 100$ cp): Amber flash (`COLOR_INT_MOVE_INACCURACY`).
   - Blunders ($\Delta > 100$ cp or loss of win): Crimson flash (`COLOR_INT_ILLEGAL`) + Royal Violet return-home undo anchor to retry.
   - Defense Reply: Stockfish 17.1 automatically computes best defensive resistance and queues move for physical execution.
4. **Physical Gesture Engine (`c2` Pawn) (`gesture_engine.py`)**:
   - Lifting `c2` starter pawn opens Endgame Academy directly on board.
   - Rank 1 lights category selectors (`a1`: Pawns, `b1`: Rooks, `c1`: Minors, `d1`: Queens).
   - Lifting category piece cycles drills with live piece previews on ranks 2–7.
   - Replacing `c2` confirms selection and begins two-phase setup.
5. **REST API & React Web UI (`main.py`, `api.ts`, `useBoardState.ts`, `AnalysisTab.tsx`)**:
   - Added REST endpoints: `GET /api/endgame/drills`, `POST /api/endgame/start`, `POST /api/endgame/stop`, `POST /api/endgame/hint`, `POST /api/endgame/custom`, `POST /api/endgame/reset-progress`.
   - Added dedicated "Endgame Academy" sub-tab in `AnalysisTab.tsx` with curriculum browser, category filtering, live two-phase setup guidance, move history, mistake counter, and custom FEN creator modal.
6. **Automated Verification (`test_endgame_trainer.py`, `test_gesture_starters.py`)**:
   - Comprehensive test suite verifying core curriculum integrity, two-phase setup validation, moves and hints execution, LED piece color palettes, and `c2` gesture lifecycle.

## Previous Change — Gesture Arming Requires Full Board Reset (`is_setup_ready`) (2026-08-26)
1. **Gesture Setup-Readiness Prerequisite (`gesture_engine.py`, `board_state.py`)**:
   - Gestures (e.g. `h2` Replay Menu, `e2` Analysis Gate, `d2` Memory Replay Gate, `a2` Night Mode Toggle) can now ONLY start when the physical board was already fully reset in the standard 32-piece starting position (`is_setup_ready == True`).
   - When setting up the board piece by piece, placing `h2` (or any other gesture pawn) as the 32nd piece will no longer prematurely arm or light up as a gesture.
   - Once all 32 pieces are in place, the `BOARD_READY` snap-flash plays, starter pawns glow, and lifting a starter pawn will cleanly start the intended gesture.
2. **Automated Verification**: Added `test_gestures_not_startable_before_board_reset` in `test_gesture_engine.py`.

## Previous Change — Post-Replay Setup Validation Lighting & Reset Guidance (2026-08-26)
1. **Post-Replay Board State & Setup Guidance (`board_state.py`)**:
   - When a replay game reaches the end (whether completed with or without mistakes), the `RECALL_COMPLETE` celebration animation plays as expected.
   - Once the celebration animation completes, the board transitions cleanly into setup validation mode (Layer 1): missing starting squares are lit in White (`c_setup_missing`) and misplaced piece squares are lit in Orange (`c_setup_misplaced`).
   - Move tracking and guardrail evaluation are suppressed while `replay_complete` is active, allowing the user to reset pieces freely without triggering illegal move warnings.
   - Restoring all 32 pieces to starting squares concludes the session to `IDLE` with the standard emerald snap-flash `BOARD_READY` animation.
2. **Automated Verification**: New regression unit test in `test_gm_replay.py`.

## Previous Change — Optimistic Overlay Reconciliation Fix (2026-08-26)
1. **Glitch fix**: the optimistic overlay was cleared as soon as the HTTP response
   arrived — often BEFORE the WebSocket broadcast with the new position — so the
   board snapped back to the pre-move position for a frame ("back and forth once").
   The overlay is now dropped only when the server FEN has actually caught up with
   the optimistic position (comparison modulo move counters); WS arrivals also
   trigger reconciliation. Hard rollback retained for rejected moves.
2. **Automated Verification**: frontend build clean; 359/359 passing on Pi; service
   restarted healthy.

## Previous Change — Optimistic UI: Instant Moves & Navigation (2026-08-26)
1. **Client-side instant application (`AnalysisTab.tsx` + `chess.js`)**: keyboard
   navigation (← → Home End / h l g G) and web moves now apply LOCALLY the instant
   they happen — FEN, last-move highlight, legal-move dots and check state are
   computed client-side with chess.js — so the piece moves with zero perceived
   latency. The backend remains the source of truth: its response/WS payload
   reconciles the overlay as soon as it arrives (~100 ms), illegal moves roll back,
   and a 2.5 s safety net clears stale overlays.
2. **Automated Verification**: frontend build clean; 359/359 passing on Pi; service
   restarted healthy.

## Previous Change — Staged Lines Compute (2026-08-26)
1. **Best line first**: the PV-lines background job is now two-stage — stage 1
   computes only the BEST line (MultiPV=1) and publishes it to the UI immediately;
   stage 2 then computes all three lines and replaces them. On-device: mainline
   visible ~1.5 s sooner than before; side lines follow a few seconds later.
2. Refactor: `compute_top_lines()` (pure compute, no cache) + `_store_lines()`;
   `get_top_lines()` keeps its cached API for the REST endpoint.
3. **Automated Verification**: staged timing confirmed on device (1 line → 3 lines);
   359/359 passing on Pi.

## Previous Change — Lines Panel Beside Board, Toast Banners Removed (2026-08-26)
1. **Engine Lines panel moved beside the board**: the panel now sits as a sibling
   column in the eval-bar + board flex row (right of the board) instead of stacking
   underneath it; layout container widened accordingly.
2. **Layout-shifting toasts removed**: the Feedback Toast Banner and the
   "Back on the main game line" confirmation banner were removed from Game Review —
   they pushed page content when appearing (typically on divergence / return to the
   mainline). State plumbing trimmed with them.
3. **Automated Verification**: frontend build clean; 359/359 passing on Pi; service
   restarted healthy.

## Previous Change — Engine Lines Panel, Always-On Best Arrow, Instant Web Moves (2026-08-26)
1. **Chess.com-style "Engine Lines" panel (`WebAnalysisBoard.tsx`)**: three clickable
   PV lines (SAN sequence + eval) rendered right of the board. Clicking a line snaps
   back from any variation and plays that line's first move as a branch; the engine
   keeps computing down the followed line only.
2. **Always-on best-move arrow while branched**: in a variation sandbox the emerald
   arrow continuously shows `top_lines[0]`; on the mainline it still appears only
   after inaccuracy/mistake/blunder as before.
3. **Instant web moves (`main.py`)**: `/api/analysis/move` now runs via
   `asyncio.to_thread`, so the HTTP response returns immediately and state flows to
   clients through the WS broadcast — no more ~0.5 s stall per move.
4. **Async lines compute**: new `coach_engine.get_top_lines()` (MultiPV=3, depth 10,
   12-ply PVs, SAN conversion, per-position cache) + non-blocking `request_lines()`;
   results reach the UI via the WS payload `top_lines` (digest-tracked so clients get
   them the moment Stockfish finishes). New endpoint `/api/analysis/lines`. Depth
   precompute may take seconds — user preference: quality over speed; UI never blocks.
5. **Automated Verification**: end-to-end on-device check confirmed lines arrive
   (~5 s first compute at depth 10, instant thereafter from cache); frontend build
   clean; 359/359 passing on physical Raspberry Pi; service restarted healthy.

## Previous Change — "Analyse on Board" Button for Recent Lichess Matches (2026-08-26)
1. **New button (`AnalysisTab.tsx`)**: each card in Recent Lichess Matches now has an
   emerald **Analyse on Board** button next to the violet **Analyse Web** one. It starts
   the Stockfish analysis of that game on the PHYSICAL board (LED move traces,
   piece-by-piece stepping) by calling `/api/analysis/start` with `moves_uci` and no
   `web_only` flag, closing the web board and showing a loading/success toast.
2. **Automated Verification**: frontend build clean; 359/359 passing on physical
   Raspberry Pi; service restarted healthy.

## Previous Change — Smoother Piece Movement Animations (2026-08-26)
1. **Web board animation upgrades (`WebAnalysisBoard.tsx`)**:
   - Distance-aware glide duration (150 ms base + 26 ms per square, capped 280 ms)
     with snappier easing, replacing the fixed 140 ms slide.
   - Knights get a gentle hop (lift ~22% mid-flight via Web Animations API).
   - Captured pieces fade/shrink out (~180 ms) instead of vanishing; en passant
     handled via a previous-placement-grid diff.
   - Castling rook glides alongside the king instead of teleporting.
2. **Automated Verification**: frontend build clean; 359/359 passing on Pi.

## Older — Eval Bar Tracks Variations (2026-08-26)
1. **Fix**: while in a variation sandbox the eval bar read `evaluations[current_ply]` (the
   stale mainline evaluation at the anchor ply) before falling back to `current_eval`, so it
   never reflected sideline positions. It now prefers the live branch evaluation from
   `current_eval` whenever branched, falling back to mainline data on the game line.
2. **Automated Verification**: frontend build clean; service restarted healthy.

## Previous Change — Live Sideline Engine & Suggestion Arrows (2026-08-26)
1. **Stockfish stays live in variations**: `get_analysis_payload()` now serves the cached
   live engine evaluation of the branch position as `current_eval` while in a variation
   sandbox (requested on every branch move and on step-back within a line), so Top
   Candidates keep updating off the mainline.
2. **Suggestion arrows**: after a mainline move classified inaccuracy / mistake / blunder,
   an emerald arrow on the web board shows the engine's better move (`played_analyses[ply].
   best_move`). The arrow is clickable — it steps back to the pre-move position, plays the
   suggestion as a new variation, and Stockfish immediately evaluates the fresh line
   (Top Candidates + eval bar update live).
3. **Automated Verification**: 2 new tests (branch eval serving via coach cache;
   engine re-engagement on branch step-back); 359/359 passing on physical Raspberry Pi.

## Previous Change — Board Orientation & Mirrored-Board Fix (2026-08-26)
1. **Critical fix — vertically mirrored board (`WebAnalysisBoard.tsx`)**: FEN rows were
   parsed rank 8-first but indexed as rank 1-first, so ALL pieces rendered on the mirrored
   rank (white looked like it was on black's side) and clicking a piece read the wrong
   cell — selection and legal-move dots could never match what was on screen. This was the
   root cause of "cannot play moves by clicking" and the black-side appearance.
2. **Orientation**: board auto-orients to the user's game color (`my_color`) with a manual
   **White ▲ / Black ▼** flip toggle in the header; piece-slide animation deltas account
   for orientation.
3. **Eval bar orientation**: white's share now grows from the player's side of the board,
   keeping quality indications consistent with the viewed orientation.
4. **Automated Verification**: frontend build clean; 357/357 passing on physical Raspberry Pi.

## Previous Change — Smoother Web Board, Always-On Eval Bar & Color-Coded Moves (2026-08-25)
1. **Click-to-move fixed**: first click on a piece selected AND instantly deselected it
   (pointerup treated every quick release as a toggle). Selection now persists on the first
   click; only a second click on the same piece deselects — click-piece-then-square works.
2. **Smoother animations (`WebAnalysisBoard.tsx`)**:
   - Drag ghost no longer re-renders the 64-square grid per mousemove — it follows the
     pointer via direct DOM `transform` writes (single React render per grab).
   - Arriving pieces glide from their origin square with a 140 ms cubic-bezier CSS
     transition on every navigation step / played move.
3. **Always-on eval bar**: vertical win-chance bar rendered beside the web board regardless
   of the play-section `eval_bar_enabled` setting; shows the numeric eval (+x.x / M#) at the
   boundary line, animated height transitions.
4. **Chess.com-style color coding**: mainline notation tiles tinted by classification
   (emerald BEST / teal GOOD / yellow INACC / orange MISTAKE / red BLUNDER) with an inline
   legend; the web-board last-move highlight is tinted by the played move's classification
   too. Variation moves keep the violet sandbox tint.
5. **Automated Verification**: frontend build clean; 357/357 passing on physical Raspberry Pi.

## Previous Change — Lichess-Style Interactive Web Board (2026-08-25)
1. **Full redesign (`WebAnalysisBoard.tsx`)**:
   - **Geometry fixed**: explicit `grid-template-rows: repeat(8, minmax(0,1fr))` inside an
     `aspect-square` container — perfectly square cells on every row (empty rows no longer
     collapse).
   - **SVG pieces**: bundled cburnett set (lichess default, 12 files, ~7 KB) replaces
     Unicode glyphs — crisp and consistent across devices.
   - **Three themes with toggle** (persisted in localStorage): Lichess Green, Wood Brown,
     Dark Slate; framed board with layered shadow.
   - **Overlays**: amber last-move tint, blue selection halo, legal-move dots + capture
     rings, red inset glow on a checked king.
2. **Drag & drop + click-to-move (pointer events, mouse & touch)**:
   - Press/drag with floating ghost piece; click piece → click destination also plays;
     re-click selected piece deselects; illegal drops snap back.
   - Legality from new backend payload fields `legal_moves` (UCI list) and `in_check`
     added to `get_analysis_payload()` — no client chess library needed.
   - Promotion picker overlay (Q/R/B/N) on the destination file for pawn last-rank moves.
   - Moves dispatch through the passive web endpoint `/api/analysis/move`; keyboard
     navigation unchanged and coexists.
3. **Automated Verification**: payload tests (legal move filtering by side-to-move,
   check reporting); frontend build clean; 357/357 passing on physical Raspberry Pi.

## Previous Change — Web-Only Sessions Fully Isolate the Physical Board (2026-08-25)
1. **Critical fix**: Webapp analysis sessions were being silently concluded by the
   physical board-reset gate (board sitting at the start position + `analysis_has_advanced`
   ⇒ instant IDLE), which made the web board vanish on the first keyboard step.
2. **`analysis_web_only` session flag (`board_state.py`)**: `start_analysis_mode(source="web")`
   (exposed via `POST /api/analysis/start {"web_only": true}`) now suppresses the reset-to-IDLE
   gate, physical move tracking/anchor restoration, guardrail noise, and ALL analysis LED layers —
   the board stays completely dark for the whole session.
3. **Frontend**: Recent Lichess matches now load straight into the interactive web board
   ("Analyse Web" button); the "Analyse in Webapp" launcher restarts the webapp-only session.
4. **Automated Verification**: 2 new tests (web-only gate immunity incl. board-source parity,
   flag cleared on stop); 355/355 passing on physical Raspberry Pi.

## Previous Change — Dedicated "Analyse in Webapp" Board (2026-08-25)
1. **Explicit webapp-only analysis entry point (`AnalysisTab.tsx`)**:
   - New "Analyse in Webapp" card at the top of Game Review: starts the Stockfish
     analysis without touching the physical board, then opens an interactive web
     board panel where keyboard navigation lives.
   - **New `WebAnalysisBoard.tsx` component**: renders the analysis-engine FEN as a
     Unicode-piece 8x8 board with rank/file labels, highlights the latest move
     (sky on mainline / violet while in a variation), and badges MAIN GAME LINE vs
     VARIATION SANDBOX state.
   - Keyboard hints printed under the board; `← →` / `h l` stepping and
     `Home End` / `g G` jumping work whenever the Game Review view is open with a
     running analysis; Top-Candidate chips + free-text move input explore variations.
2. **Automated Verification**: frontend build clean; 353/353 tests passing on
   physical Raspberry Pi.

## Previous Change — Web-Only Analysis Navigation (2026-08-25)
1. **Keyboard-driven analysis in the webapp (board fully passive)**:
   - **Navigation endpoint** (`POST /api/analysis/nav {"direction": ...}` →
     `BoardStateManager.navigate_analysis()`): "back"/"forward" step the mainline;
     while in a variation sandbox "back" un-plays exactly ONE branch move and
     rebuilds the position; "start"/"end" jump to first/last mainline ply exiting
     any branch. Responses carry an explicit `on_mainline` flag.
   - **Keyboard bindings** (`AnalysisTab.tsx`): `← →` / `h l` step moves,
     `Home End` / `g G` jump start/end (ignored while typing in inputs).
   - **Back-on-mainline indicator**: green toast "Back on the main game line"
     fires exactly on the false→true `on_mainline` transition.
   - **Web move playback**: Top Candidates chips are clickable and a free-text
     field accepts SAN (`Nf3`, `exd5`, `O-O`) or UCI; `/api/analysis/move` now uses
     `source="web"` which skips LED arrival flashes and tracker interaction so the
     physical board stays completely dark during web-only analysis.
   - Variation banner now shows the full off-line move sequence.
2. **Bug fixed**: `navigate_analysis("back")` clears divergence anchors when the
   last branch move is un-played (previously left stale violet anchor state).
3. **Automated Verification**: 5 new tests (branch pop-one-at-a-time FEN
   reconstruction, forward-no-op while branched, start/end branch exit, board-passive
   web moves, SAN input incl. castling); 353/353 passing on physical Raspberry Pi.

## Previous Change — Seek Match Grace Window (Event-Stream Fallback Fix) (2026-08-25)
1. **Regression fixed (`lichess_engine.py`)**: The previous stale-connection fix snapped status
   back to IDLE the instant the seek NDJSON stream closed without a match — but Lichess often
   delivers the matched `gameStart` via the persistent event stream instead, milliseconds later.
   With status already IDLE, the seek-stream fallback rejected our own match ("ignoring
   gameStart ... not initiated by this session"), leaving orphaned games on Lichess and a board
   that reset without starting a game.
2. **Fix**: On seek-stream close without a match, `_schedule_seek_grace_end()` holds SEEKING for
   10 s so the event-stream fallback can accept the match; a generation counter invalidates the
   grace timer when a newer seek starts. Regression test covers stream-close → event-stream
   gameStart → PLAYING.
3. **Automated Verification**: 348/348 tests passing on physical Raspberry Pi.

## Previous Change — Seek Stale-Connection Recovery & Unified Replay-Menu Colors (2026-08-25)
1. **Intermittent "gesture completes but never enters queue" fixed (`lichess_engine.py`)**:
   - **Root Cause**: Lichess closes idle HTTP/2 pooled connections server-side; httpx does not
     report these as `client.is_closed`, so the next seek POST on the stale connection threw
     `ConnectionInputs.RECV_HEADERS in ConnectionState.CLOSED`, silently aborting matchmaking
     (status snapped back to IDLE → only BOARD_READY visible).
   - **Fix**: `_recreate_client()` helper + one-shot retry in `_seek_and_stream` when a
     transport/stale-h2 error occurs (`_is_stale_connection_error`). On final failure a crimson
     error flash fires on g1/h1 so the user is never left without feedback.
   - Natural seek-stream end now also returns status to IDLE.
2. **Replay menu option colors unified (`gesture_engine.py`)**: all three time-control options
   (e1/f1/g1) share Cyan Azure; the currently selected time control glows Royal Violet with a
   breathing pulse. Rook AI/Human indicator unchanged (Magenta=AI / Gold=Human).
3. **Automated Verification**: 2 new regression tests (retry-once + no-retry paths); 348/348
   tests passing on physical Raspberry Pi.

## Previous Change — Replay Trainer (Memory Training) & Memory Replay Gesture (2026-08-25)
1. **Replay Trainer replaces GM Guess-the-Move ("GM Time Machine")**:
   - **Phase 1 — Learn (`replay_learn`)**: Pick a curated GM masterpiece and physically play it
     move-by-move; the board shows the next Grandmaster move as an azure LED trace. Correct moves
     auto-advance with a green confirmation flash; diverging moves flash crimson and anchor for
     guided snap-back to the game line.
   - **Phase 2 — Recall (`replay_recall`)**: Setting all 32 pieces back to the starting position
     ends the learn phase and starts memory recall scoped to *exactly the plies just learned*.
     No move hints — only side-to-move King pulse. Green flash = correct move remembered
     (mint arrival flash); wrong legal move = crimson flash + amber LED reveal of the grandmaster
     continuation; the user un-plays their piece (violet anchor + return-home guide) then follows
     the revealed move free of charge.
   - **Completion**: Reaching the learned depth fires the new golden "Memory Bloom"
     `RECALL_COMPLETE` celebration animation plus a UI summary (correct/total, mistakes,
     memory score). Restoring the start position afterwards concludes to IDLE.
   - **Accessibility**: Stopping mid-game is first-class — partial learning yields a shorter
     recall target. Abandoned incomplete recalls exit cleanly on board reset.
   - Direct-recall entry point `start_replay_recall()` replays the last played game with no learn
     phase (move-source hierarchy identical to analysis mode).
2. **Memory Replay Gate gesture (`gesture_engine.py`)**:
   - Lift **d2** first → lift **e2** → replace both = instant memory replay of the last played game.
   - Disambiguated from the Analysis gate purely by lift order (e2-first still arms Analysis only).
   - Radiant Gold starter glow on d2 (vs. Royal Violet on e2); error cue (crimson d2/e2 flash +
     stay IDLE) when no previous game is stored.
3. **API**: `POST /api/analysis/gm/guess` removed; `POST /api/analysis/replay/recall` added;
   `/api/analysis/gm/start` now begins a learn session. WS payload: `gm_score`/`gm_guesses`
   replaced by `replay: {phase, learned_ply, results[], mistakes, reveal_uci, complete}`.
4. **Frontend**: New Replay Trainer view in `AnalysisTab.tsx` (learn progress + revealing move list,
   hidden-notation per-ply ✓/✕ chips during recall, victory summary), types in `useBoardState.ts`,
   client in `api.ts`.
5. **Automated Verification**: New `tests/test_gm_replay.py` (learn/gate/recall/reveal/completion/
   direct-recall/gesture disambiguation); updated `test_blunder_drill.py`.

## Previous Change — Fast Game Start Animation & Persistent First-Move Color Anchor (2026-08-25)
1. **Snappy `GAME_STARTED` Lifecycle Animation (`led_animations.py`, `config.py`)**:
   - **Reduced Duration**: Shortened from $2.2\text{s}$ to $1.2\text{s}$ for a fast, punchy color proclamation.
   - **Choreography**:
     - Fast electric lightning wave across player's home ranks (Ranks 1–2 in Ivory Gold for White; Ranks 8–7 in Cosmic Cyan for Black).
     - Radiant royal crown pulse on the King and Queen squares (`e1/d1` or `e8/d8`).
2. **Persistent First-Move Color Anchor (`board_state.py`)**:
   - **Visual Anchor**: Until the player plays their first physical move (`move_count == 0` for White; `move_count <= 1` for Black), the player's home royal thrones (`e1/d1` for White; `e8/d8` for Black) maintain a gentle, rhythmic breathing halo ($I = 0.28 + 0.14 \sin(3.0 t)$) in the player's signature army color (Warm Ivory Gold for White, Electric Cosmic Cyan for Black).
   - **Looking Away Safety**: Even if the player was looking away when the game started, glancing at the board at any time before their first move unambiguously reveals which color they are playing.
   - **Seamless Dissolve**: As soon as the player executes their first physical move, the persistent anchor deactivates and standard turn breathing takes over.
3. **Automated Verification**:
   - 339/339 unit tests passing on physical Raspberry Pi.

## Previous Change — Color-Harmonized Opponent Movement & Two-Phase Castling (2026-08-25)
1. **Opponent Movement Color Harmonization (`config.py`, `board_state.py`)**:
   - **Origin Square (Piece to Move)**: Lit in distinct Solar Orange `COLOR_OPPONENT_FROM` (`220, 100, 0` Day / `240, 140, 0` Night).
   - **Quiet Move Path & Arrival**: 100% unified in **Electric Sky Azure** `(0, 150, 240)` Day / `(0, 220, 230)` Night. Destination square rests in this hue and flares smoothly to full brightness on comet arrival with zero color clash artifacts.
   - **Capture Move Path & Arrival**: 100% unified in **Radiant Ruby Crimson** `(220, 20, 50)` Day / `(255, 10, 40)` Night.

2. **Two-Phase Opponent Castling Sequence ("In 2 Times", `physical_tracker.py`, `board_state.py`)**:
   - **Phase 1 (King Time)**: Displays ONLY the King's move (e.g. `e8` origin in Solar Orange, `g8` destination in Sky Azure + animated comet trace `e8 -> g8`).
     - Placing King on `g8` triggers King green arrival flash and automatically advances state to Phase 2.
   - **Phase 2 (Rook Time)**: Displays ONLY the Rook's move (e.g. `h8` origin in Solar Orange, `f8` destination in Sky Azure + animated comet trace `h8 -> f8`).
     - Placing Rook on `f8` triggers Rook green arrival flash and completes the castling sequence.
   - **Simultaneous/Rook-First Resilience**: Handles simultaneous piece placement or rook-first movement gracefully without lockups.

3. **Automated Verification**:
   - All 338 unit tests passed on physical Raspberry Pi.

## Previous Change — Redesigned Defeat & Draw Animations (2026-08-25)
1. **"The Sovereign's Eclipse" (`GAME_LOST` Redesign in `led_animations.py`)**:
   - **Unified Realm Symmetry**: Removed the single-square "meteor" strike coordinate artifact. The animation is centered on the symmetrical board center $(3.5, 3.5)$ with identical visual majesty for White and Black.
   - **Phase 1: Inward Perimeter Collapse ($0.00 \le p < 0.35$)**: Inward-sweeping Gaussian ring closing in from the 28 perimeter squares to the central royal core in Obsidian Garnet and Blazing Ruby.
   - **Phase 2: Crown Fracture & Shatter Shockwave ($0.35 \le p < 0.70$)**: White-hot crown detonation flash on the central thrones, an expanding circular ruby shockwave ring, and 4 flying molten gold shards along diagonal rays.
   - **Phase 3: Smoldering Embers & Obsidian Dissolve ($0.70 \le p \le 1.00$)**: Dual-harmonic organic flickering cinders with a central dying hearth cardiac pulse fading smoothly into obsidian darkness.
   - **Power Budget**: Peak $\le 18$ active squares ($\approx 179.2\text{mA} \ll 220\text{mA}$ limit; $\le 80\text{mA}$ in Night Mode).
   - **Duration**: $2.8\text{s}$.

2. **"The Celestial Equilibrium" (`GAME_DRAWN` Redesign in `led_animations.py`)**:
   - **Harmonic Dual Tides ($0.00 \le p < 0.38$)**: Luminous Pearl White wave (Rank 1–2 advancing upward from SW) meets Celestial Sapphire wave (Rank 7–8 advancing downward from NE).
   - **The Equatorial Vortex ($0.38 \le p < 0.72$)**: The two tides collide at Ranks 4–5, swirling in a gentle Yin-Yang breathing equilibrium and blending into Radiant Aqua.
   - **Serene Horizon Dissolve ($0.72 \le p \le 1.00$)**: Tranquil outward horizontal dispersion settling the entire board into peaceful stillness.
   - **Power Budget**: Peak $\le 16$ active squares ($\approx 135\text{mA} \ll 220\text{mA}$ limit; $\le 60\text{mA}$ in Night Mode).
   - **Duration**: $2.6\text{s}$.

3. **Automated Verification**:
   - 338/338 unit tests passing on physical Raspberry Pi.

## Previous Change — The King's Bow Physical Resignation Gesture & Opening Hints Switch (2026-08-25)
1. **The King's Bow Physical Resignation Gesture (`physical_tracker.py`, `board_state.py`)**:
   - **Pondering Safety**: Lifting the friendly King displays normal legal move targets. Moving the King to a legal destination always executes a standard chess move with 100% priority.
   - **The King's Bow Surrender**: Holding the King lifted for $\ge 3.0\text{s}$ arms resignation (pulsing Laser Crimson origin halo + soft garnet cross-halo). Replacing the King back on its origin square while armed **confirms resignation**.
   - **King Laid to Rest (Tipped)**: Leaving the King off the board for $\ge 5.0\text{s}$ auto-confirms resignation on abandonment timeout.
   - **Short Cancel**: Replacing the King before the 3.0s arming threshold cleanly cancels move selection without side effects.
   - **Game Engine Integration**: Automatically dispatches resignation to online Lichess games (`POST /api/board/game/{game_id}/resign`) and concludes Local matches (`stop_local_game(reason="resignation")`).
   - **Visuals & Electrical Power Budget**: Low-power LED rendering (`render_resignation_aura`) consuming $\le 10$ LEDs ($\approx 92.8\text{mA} \ll 220\text{mA}$ ceiling), with Day and Night Mode variants.
   - **React 19 Frontend**: Real-time "The King's Bow Armed" toast notification banner and WebSocket synchronization.
   - **Automated Test Suite**: 5 dedicated tests in `Raspberry/tests/test_gesture_resignation.py` (338/338 total tests passing on Pi).

2. **Cartographer's Path Toggle Switch (`App.tsx`, `main.py`, `board_hardware.py`)**:
   - Added `opening_hints_enabled: bool` setting in backend, REST API (`POST /api/board/settings`), and local storage.
   - Added toggle switch in Settings panel with Compass icon to enable/disable opening trailblazers and novelty flares.

## Previous Change — Cyber-Physical Local Game Engine & Setup Auto-Start (2026-08-24)
Implemented zero-touch automatic Local Two-Player game initiation and cyber-physical state management:
1. **Setup Readiness Arming Gate (`can_start_local_game`)**:
   - Strictly armed only when all 32 pieces are in standard starting positions (`is_setup_ready == True`), no transients exist, and gestures are idle.
   - **Teardown & Setup Immunity**: Putting pieces back one by one or clearing the board will never accidentally trigger a game.
   - Gesture disambiguation: Lifting `a2`, `e2`, or `h2` and placing on legal chess squares starts the game; lifting secondary gesture pieces advances into the gesture sequence instead.
2. **Cyber-Physical Local Game Engine (`LocalGameEngine`)**:
   - Symmetrical over-the-board physical play for White and Black turns with legal move hints, Cartographer's Path opening dots, capture tracking, castling, en passant, and the Royal Promotion Scepter.
   - Real-time endgame detection (Checkmate, Stalemate, 50-move rule, Threefold repetition).
   - Seamless post-game recording (`_record_last_game_from_local`): finished local games are immediately ready for Stockfish 17.1 coach analysis and Blunder Blitz drills via Center Royal Gate (`e2+d2`) or web UI.
   - Zero-touch board reset: restoring 32 starting pieces in `GAME_OVER` automatically resets state back to `IDLE` with `BOARD_READY` flash.
3. **REST API & Web UI**:
   - Added `POST /api/game/local/start` and `POST /api/game/local/stop`.
   - Updated `POST /api/game/move`, `POST /api/game/resign`, and `POST /api/game/draw` to support local matches.
   - React 19 Frontend: Added "Local Match (OTB)" indicator badge, turn labels, and local game controls.
4. **Automated Test Suite**:
   - Comprehensive test coverage in `Raspberry/tests/test_local_game.py`.

## Previous Change — Feature P1 (Royal Promotion Scepter) & Feature P2 (Cartographer's Path) (2026-08-24)
Implemented two major cyber-physical intelligence features:
1. **Feature P1: The Royal Promotion Scepter (Multi-Piece Underpromotion Selector)**:
   - Dynamic 4-piece slot allocation algorithm (`compute_promotion_layout` in `Raspberry/app/physical_tracker.py`):
     - Assigns distinct coordinates for Queen (Royal Violet), Knight (Mint Emerald), Rook (Azure Cyan), Bishop (Warm Sun Amber).
     - Target back-rank is Rank 8 for White, Rank 1 for Black.
     - Fallback rule: When a backrank square is the promotion arrival square or occupied by a piece or already allocated, it automatically falls back to the **same file 1 row ahead** (Rank 7 for White, Rank 2 for Black).
     - Center-out file search relative to `promo_col` with robust whole-board fallbacks for crowded positions.
   - Physical placement detection, pawn return-to-origin cancellation, and auto-queen timer ($5.0\text{s}$).
   - External resolution via REST API `POST /api/game/promote` and Web UI Royal Promotion Scepter modal.
   - Low-power WS2812B visual guide (`render_promotion_scepter`) consuming $\le 5$ active squares ($< 120\text{mA}$ on 5V rail).

2. **Feature P2: The Cartographer's Path (Opening Book Trailblazer & ECO Classifier)**:
   - High-speed embedded Opening Engine (`Raspberry/app/openings.py`):
     - Full ECO classification taxonomy (A00-E99), opening names, variations, and candidate book moves with weighted probabilities.
     - Polyglot `.bin` support for custom opening libraries.
   - In-game LED trailblazer target hints when a piece is lifted:
     - Mainline book target highlighted in **Mint Emerald**.
     - Sideline book targets highlighted in **Azure Cyan**.
   - **Uncharted Novelty Flare** (`render_uncharted_novelty` in `Raspberry/app/led_animations.py`):
     - 350ms radial Gaussian starburst ripple ($< 90\text{mA}$ peak) triggered when moving out-of-book.
   - React 19 Frontend opening badges in header and analysis tabs.
   - Unit test suites in `test_openings.py`, `test_physical_tracker.py`, and `test_led_animations.py`.

## Previous Change — Agent Fleet Redesign & Domain Specialization (2026-08-24)
Redesigned and optimized the AI Agent Fleet to align with the matured cyber-physical codebase:
- Decommissioned obsolete Playwright / Chess.com browser automation specialist (`automation.md`).
- Decomposed monolithic full-stack developer role into 4 dedicated specialists:
  - **Core Game & State Engine Specialist** (`game_engine.md`): `board_state.py`, `physical_tracker.py`, `gesture_engine.py`, `setup_validator.py`, `main.py`.
  - **Chess AI & Lichess Cloud Specialist** (`chess_ai.md`): Stockfish 17.1 UCI async wrapper (`coach_engine.py`), Lichess Board API NDJSON streaming (`lichess_engine.py`), clock synchronization, blunder scoring, `gm_games.py`.
  - **Lighting & Animation Designer** (`led_visuals.md`): WS2812B LED array rendering (`led_animations.py`, `led_helpers.py`), serpentine Strip 1/2 mapping, clock/eval bars, trajectory traces, electrical power budgeting ($\le 220\text{mA}$).
  - **Web Frontend & UI/UX Specialist** (`frontend.md`): React 19 / Vite / TypeScript components (`App.tsx`, `AnalysisTab.tsx`), WebSocket client hooks (`useBoardState.ts`), typed REST client (`api.ts`), Tailwind styling.
- Refined and updated **System Architect** (`arch.md`), **Embedded & Hardware Specialist** (`hardware.md`), **QA & Testing Specialist** (`qa.md`), **Code Explorer** (`explorer.md`), and **Creative Innovator** (`creative.md`).
- Synchronized `AGENTS.md`, `GEMINI.md`, and `.agents/skills/agentic-orchestrator/SKILL.md` with the new roster and strict SSH Pi deployment protocols.


## Previous Change — Smooth clock ticking + return-home divergence guide (rev 4b13dac, deployed 2026-08-24)
**Smooth clocks**: Lichess pushes gameState ~1Hz (push stream, no polling possible) — the web UI was the slow surface. `LichessEngine.get_interpolated_clocks()` drains the side-to-move clock locally between events; `update_loop` now recomputes formatted `self.clocks` every tick and `_build_broadcast_payload` gained `clocks_raw` ({white, black, updated_at, turn}). Frontend (`App.tsx`) snapshots raw values on receipt, ticks the turn side every 500 ms client-side (skew-free local elapsed), falls back to strings when absent. LED bars were already smooth.
**Return-home guide**: while branching in ANALYSIS, a pulsing gold halo (`render_return_home_guide`, `COLOR_RETURN_HOME`/night variant) marks the arrival square of the LAST branch move ("un-play this next") with a steady 35% dot on its origin; it steps back automatically as physical un-plays truncate `analysis_branch_moves`. Origin dot suppressed when it coincides with the violet anchor square. Web banner chip "Off line · ply N + [Return to game]" added to the ANALYSIS banner wired to existing `branch_reset` API. Tests: interpolation (4), renderer (5), integration guide (1), payload shape (1); **296/296 pytest passed on Pi**, frontend rebuilt, service restarted.

## Previous Change — LED chess-clock drain bars (rev 5038a41, deployed 2026-08-24)
New PLAYING-mode LED visualization (`Raspberry/app/led_animations.py::render_clock_bar`): the **white clock drains down file h, black down file a**, replacing the perimeter eval bar while active (setting `clock_bar_enabled`, default True; eval bar renders as fallback when clocks are invalid/unlimited or the toggle is off). Urgency colors: green >25% remaining, amber ≤25%, red + sine pulse ≤10% (`COLOR_CLOCK_OK/WARN/CRIT` day + night palettes in `config.py`, packed in `led_helpers.py`). Only the side-to-move clock interpolates between Lichess events (`raw_clocks_ms` − elapsed since new `clocks_updated_at`; totals from `initial_clocks_ms` captured in `_handle_game_full`). Bar fills rank 1 upward via truncation with a breathing fractional edge square. Painted early in the Layer-2 stack so piece lifts / legal-move dots / traces overwrite it (last-writer-wins); renders regardless of `fair_play_active` (clocks are public data). Settings plumbing mirrors `eval_bar_enabled` (`board_hardware.py` defaults, `ThresholdSettings` + `apply_settings` in `main.py`). Tests: 11 renderer cases in `test_led_animations.py`, 3 integration cases in `test_board_state.py`; **285/285 pytest passed on Pi**; service restarted and healthy.

## Previous Change — Replay Last Game selection menu (rev 73747de, deployed 2026-08-23)
`RestartPreviousGameGesture` rewritten from the h2→h1 corner gate into an interactive selection menu (`Raspberry/app/gesture_engine.py`): lifting the **h2 pawn** opens a menu lighting four kingside back-rank pieces — **e1 King = 15+10**, **f1 Bishop = 10+0**, **g1 Knight = 3+2**, **h1 Rook = AI/Human toggle** (Magenta=AI / Gold=Human). Time-control choices register on replacement with an arrival flash; the rook toggles instantly at lift with live LED feedback. Multiple selections can be made while h2 stays lifted (each interaction refreshes the 30 s inactivity timer); replacing h2 starts matchmaking with the chosen time control/mode plus remaining params from persisted `last_game_params`. Cancellations (extra piece lifts, two options at once, dropping h2 while holding an option, center occupation, timeout) require all pieces replaced before re-arm (`_holdoff`). Defaults seeded from `last_game_params`; WS payload gained a `selection` field; frontend banner/labels updated. `_get_board_anomalies` moved to `BaseGesture`, which now accepts `state_manager`. Tests: 13 restart-gesture cases in `test_gesture_engine.py`; **271/271 pytest passed on Pi**, ruff clean, service restarted.

## Deployment Status — ✅ DEPLOYED & VERIFIED ON DEVICE (2026-08-23, rev 32574fc)
All optimization commits plus the coach-engine analysis fix are live on the Raspberry Pi and the ESP32 runs the new firmware. Final on-device verification:
- `git pull` clean; frontend built; **265/265 pytest passed**; ruff clean; service active with no error-level journal entries.

### BOARD_READY snap-flash rework (rev 32574fc)
`render_board_ready` replaced with "The Emerald Snap Flash": duration cut 1.4s → 0.5s (`ANIM_BOARD_READY_DURATION_S`). Phase 1 (0–40%) is a rapid dual-army inward sweep; Phase 2 (40–100%) is a bright center-diamond pop decaying exponentially while corner rooks + kings fade in to hand off to ambient. Power budget unchanged (≤ 10 squares).

### Analysis reset-to-IDLE fix (rev d2c5431)
Root cause: free-form piece restoration during Analysis mode wedged `PhysicalMoveTracker` with a stale `lifted_square` (an illegal placement sets `invalid_placement` but never clears `lifted_square`, physical_tracker.py Case B.3), and the ANALYSIS loop branch — unlike IDLE — had no transient-recovery path. The auto-exit gate required all transients `None`, so restoring the starting position was never recognized and the 3-pawn starter gestures never returned. Fix: extracted `_try_conclude_analysis_on_board_reset()` in `board_state.py`; a complete 32-piece starting layout proves no piece is in hand, so stale tracker transients are discarded and the transition to IDLE + `BOARD_READY` + `gesture_engine.reset()` proceeds. Regression tests added (wedged-tracker conclusion, loading-immunity, review-progress requirement).

## Previous Deployment Status — rev 8b66efb
All optimization commits plus the coach-engine analysis fix are live on the Raspberry Pi and the ESP32 runs the new firmware. Final on-device verification:
- `git pull` clean; frontend built; **259/259 pytest passed**; service active.
- ESP32 flashed (freshness-gated scan cache, parser self-resync, legacy protocol removal) — 0 serial/CRC errors since flash.
- **Coach fix verified end-to-end**: fresh 10-ply batches run through REAL Stockfish in ~1.1–1.3 s with realistic varied score trajectories (e.g. `[38, 30, 27, 28, 26, 27, 25, 15, 33, 31, 29]`), `error: None`, and **zero CommandState / heuristic-fallback warnings** in the journal during batches. Second identical request served from the persistent cache in **0.035 s** (~38× faster).
- Analysis results persist to `Raspberry/analysis_cache.json` (LRU 8 games, git-ignored sibling of board settings) — re-analyzing a finished game is instant across restarts.

### Coach root cause (for the record)
`request_analysis` cancelled the in-flight evaluation task on every position change during play. With `asyncio.shield` removed (optimization pass), cancellation propagated into python-chess and killed queued UCI commands (`CommandState.NEW`), so every live position silently fell back to the flat material heuristic. The warm heuristic cache then made post-game batch analysis finish instantly with wrong classifications/recommendations and no visible computing animation. Fix: never cancel in-flight analyses (skip while busy — 100 ms limit keeps evals fresh), make Stockfish mandatory (`CoachEngineUnavailable` raised after one relaunch/retry, surfaced in payload `error` + UI banner), auto-relaunch crashed engines, and persist per-game analyses for fast reuse.

## Active Agents Roster
- **System Architect** (`.agents/agents/arch.md`) - System design, schemas, API contracts, state machines, serial framing.
- **Embedded & Hardware Specialist** (`.agents/agents/hardware.md`) - ESP32 firmware, GPIO, CD74HC4067 MUX, Hall sensor matrix calibration, binary CRC-8 serial protocol.
- **Core Game & State Engine Specialist** (`.agents/agents/game_engine.md`) - Central state coordinator (`board_state.py`), physical move tracker, board gestures, setup validator, FastAPI app.
- **Chess AI & Lichess Specialist** (`.agents/agents/chess_ai.md`) - Stockfish 17.1 UCI wrapper (`coach_engine.py`), Lichess Board API NDJSON streaming (`lichess_engine.py`), clock synchronization, blunder scoring, GM games database.
- **Lighting & Animation Designer** (`.agents/agents/led_visuals.md`) - WS2812B LED array rendering (`led_animations.py`, `led_helpers.py`), serpentine mapping, clock/eval bars, trajectory traces, electrical power budgeting ($\le 220\text{mA}$).
- **Web Frontend & UI/UX Specialist** (`.agents/agents/frontend.md`) - React 19 / Vite / TypeScript SPA (`App.tsx`, `AnalysisTab.tsx`), WebSocket state hooks (`useBoardState.ts`), typed REST client (`api.ts`).
- **QA & Testing Specialist** (`.agents/agents/qa.md`) - Pytest unit/integration test suites (~300 tests), mock hardware drivers, test sandboxing (`conftest.py`), regression prevention, static analysis quality gates.
- **Code Explorer** (`.agents/agents/explorer.md`) - Search, index, trace, and locate codebase information and symbol definitions.
- **Creative Innovator** (`.agents/agents/creative.md`) - Feature brainstorming & ideas (Invoked ONLY on explicit user request).

## Completed Tasks
- [x] ESP32 Firmware Optimization & Legacy Protocol Removal (`Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino`, `Raspberry/hardware_test.py`):
  - **Freshness-Gated Scan Cache**: `CMD_SCAN_ADC` now serves the continuously-maintained `latest_scan` when it is at most 20 ms old (`SCAN_CACHE_MAX_AGE_MS`), performing a fresh blocking scan only when stale. Previously EVERY host poll triggered a full ~10-15 ms blocking scan in the request path, and loop()'s idle branch could run a second redundant scan immediately after — capping the effective scan rate and adding latency to every physical-move detection cycle.
  - **Parser Self-Resync**: the 50 ms partial-packet staleness reset moved out of the `Serial.available()` branch, so a stream that stalls mid-packet recovers without waiting for more bytes (previously a corrupted/truncated frame could wedge the parser state until the next byte arrived).
  - **Legacy Single-Byte Handlers Deleted**: removed `handleLegacyCommand` ('B'/'L'/'W'/'C'/'A'/'S') including three busy-wait receive loops that could block parsing for up to 10 ms each. Sole consumer `hardware_test.py` migrated to the framed binary protocol (`build_packet(CMD_SCAN_ADC)` + shared `_read_adc_packet`), given a proper serial lock on `set_serial_conn`, and equipped with a `--quiet` flag that suppresses per-tick timing/grid spam (prints only on state change).
  - **Idle Scan Rate Gate**: idle background scanning rate-limited to one scan per 5 ms (`IDLE_SCAN_INTERVAL_MS`) instead of back-to-back full-speed passes, reducing idle CPU load and ADC self-heating while keeping the cache warm.
  - Verification: Python-side gates all green locally (261/261 pytest, ruff clean, vulture clean, hardware_test import smoke test). On-device: compile via Arduino IDE is the pre-flash gate; post-flash journalctl must show no CRC/TIMEOUT/PARSE_ERROR storms.
- [x] Full Codebase Optimization Pass (dead code elimination, performance, correctness, static-analysis clean):
  - **Serial Protocol Correctness (`Raspberry/board_hardware.py`)**: Enforced CRC-8 validation on framed ADC packets (the `or len(full_payload) == 128` clause made it vacuous — corrupted packets became phantom piece lifts); framed-packet trailing-read timeout no longer falls through returning header bytes as raw sensor data; hot scan loop hoists baselines/thresholds/normalized `disabled_squares` set once per scan (was O(n) list membership × 64 squares × 2 sites per tick); calibration sampling skeleton deduplicated into `_collect_calibration_samples`; O(n) baseline-history pruning.
  - **Event-Loop & Broadcast Architecture (`Raspberry/app/board_state.py`, `main.py`)**: Update-loop tick exceptions now log with traceback and continue (previously one transient error permanently killed scanning/LEDs/WS until restart); LED frame flush deduplicated into `flush_frame()`; arrival-flash decay and eval-bar math extracted to single helpers; per-tick setup validation contract preserved; analysis anchor-board reconstruction cached + gated on physical-state signature; `AnalysisEngineAdapter` hoisted to module scope (was re-created 100×/sec); digital grid rebuilt only on FEN change; idle tracker reset skips deep copy when clean; gesture reset now transition-based. `ConnectionManager` rewritten with per-client outgoing queues + sender tasks (slow client can no longer stall the loop or other clients), broadcast failures logged, payload construction skipped at zero clients, event-driven broadcast with cheap change digest + 250 ms heartbeat replacing unconditional ~100 Hz full-state pushes; `/api/board/clear_leds` moved off the event loop; fire-and-forget tasks held via `_spawn_task`.
  - **Security & API Hardening (`Raspberry/app/main.py`, `lichess_engine.py`)**: Fixed path traversal in frontend static serving (realpath containment); dropped CORS `allow_credentials` wildcard combo; unmatched `/api/*` GETs return 404 instead of `200 null`; fixed `mux_settle_ms` being persisted with a microsecond value; Lichess engine now reuses one pooled httpx AsyncClient via `_request_client` proxy (previously created throwaway TLS clients per move/resign/seek — 100-300 ms extra latency per move); resign/abort only finalize game state on confirmed HTTP 200 (failed calls previously polluted last-game stats and dropped the board to IDLE mid-game); `stop()` awaits cancelled tasks before closing the client; event-stream headers refreshed per reconnect; `_apply_moves` redundant legality check removed with sync warning logged; `get_game_payload` pop/push trick replaced by cached capture flag.
  - **Coach Engine (`Raspberry/app/coach_engine.py`)**: `CancelledError` is re-raised instead of swallowed as heuristic fallback (swallowing defeated the cancellation design and could interleave concurrent Stockfish analyses after lock release); `asyncio.shield` removed accordingly; dead `_transport` field removed; move-quality tier constants (`TIER_BEST_MAX_LOSS=10/GOOD=50/INACCURACY=150`) are now the single source of truth reused by board_state LED classification (LED fallback previously used diverging 15/60/150 thresholds).
  - **Gesture Engine Consolidation (`Raspberry/app/gesture_engine.py`)**: Three ~90% copy-pasted corner-gate gesture classes collapsed into one parametrized `CornerGateGesture` base (~200 duplicate lines removed) preserving exact state-machine semantics, LED palettes, hints, and completion-flash primary squares; shared `_schedule_task` helper keeps task references (GC-safety) with consistent no-loop handling; duplicated Azure/Royal-Violet/Mint-Emererald color definitions now imported from led_helpers; dead imports removed; `starter_color`/`starter_coord` use `is not None` checks.
  - **Physical Tracker (`Raspberry/app/physical_tracker.py`)**: Removed futile castling fallback that recomputed an identical pure-geometric call and iterated all legal moves a second/third time per placement; contradictory double-negative placement predicate extracted to `_sensor_polarity` helper; `to_dict()` is now the production serializer consumed by `get_physical_payload` (was test-only while the payload hand-duplicated every field).
  - **Dead Code Elimination (repo-wide)**: Deleted the superseded thread-based animation subsystem in `led_helpers.py` (`flash_leds`, `animate_*`, `signal_*`, `start/stop_animation`, perimeter helper — zero references); removed ~60 dead config entries/constants (`BUTTON_PIN`, rpi_ws281x direct-drive leftovers, legacy lifecycle colors/flash timings), unused imports across app+tests, unused `getAnalysisState`/`sendAnalysisMove` API functions and unreachable positional branch, unused exported types, dead assets (`vite.svg`, `icons.svg`), unreachable `my_color` validator param, futile castling recompute; fixed unreachable GM annotations (kasparov ply 88 > 77 plies, tal ply 85 > 79 plies) with a new bounds test; `physical_tracker.to_dict` consolidated; `setup_validator` unused param dropped; `highlighted_square` vestigial feature removed end-to-end.
  - **Frontend Performance & Robustness (`frontend/src`)**: WebSocket hook skips identical consecutive payloads (JSON string compare) before touching React state; StrictMode/unmount-safe socket lifecycle (disposed flag, handler detachment, CONNECTING guard); central typed `request<T>()` API layer with `response.ok` enforcement, safe error extraction, and per-endpoint timeouts (29 fetches previously had neither ok-checks nor aborts); relative `/api` base + Vite dev proxy for `/api` and `/ws` (fixes mixed-content breakage under HTTPS); claim countdown derived from server value instead of dual-driven interval jitter; settings debounce reads live state ref (stale-closure bug resurrecting disabled squares); triplicated 16-field settings payload builders unified into `buildSettingsPayload()`; AnalysisTab lazy-loaded (32 KB chunk split out of the main bundle) with follow-the-server submode semantics; all 19 ESLint errors fixed (hook deps, set-state-in-effect patterns, unused bindings, explicit types replacing `any`).
  - **Static Analysis Clean**: Repo passes project-configured Ruff (was 332 findings incl. 47 unused imports), Vulture (only intentional mock stubs remain), Knip (unused exports resolved; knip now usable offline as a quality gate), `tsc --noEmit`, ESLint, and `vite build`; full suite green at **261 passed** with updated tests (tuple index assertions, patch targets aligned to single module-level settings binding, claim-victory URL assertion decoupled from client internals).
- [x] Implemented Post-Game Board Gesture Analysis & Real-Time Computing LED Animation:
  - **Completed Game Move History Capture (`Raspberry/app/lichess_engine.py`)**: Added centralized `_record_last_game(state_manager)` capturing the complete UCI move stack, `game_id`, and match metadata across all game completion paths (checkmate, resignation, timeout, draw, victory claim, and abort). Automatically persists `last_game_moves` and `last_game_id` to hardware `board_settings.json` to survive application restarts.
  - **Prioritized Last-Game Analysis Resolution (`Raspberry/app/board_state.py`)**: Updated `start_analysis_mode()` fallback hierarchy so when the player triggers analysis with no explicit arguments (e.g. via board gesture or 1-click review), it automatically prioritizes the game just played (`self.last_game_moves` -> `lichess_engine.last_game_moves` -> `move_stack` -> `settings["last_game_moves"]`), falling back to demo openings only if no game was ever played.
  - **Procedural Low-Power Computing Animation (`Raspberry/app/led_animations.py` `render_analysis_computing`)**:
    - **Visual Choreography**: Central 2x2 core (`d4`, `e4`, `d5`, `e5`) in soft breathing Royal Violet (`0x5000A0`), surrounded by an orbital 12-square ring with dual sweeping Mint Emerald (`0x009040`) and Cyan Azure (`0x006090`) calculation probes sweeping at ~1.35 rev/sec in opposing $180^\circ$ phase.
    - **Power & Safety Compliance**: Strictly limited to $\le 8$ simultaneous active squares ($\le 16$ WS2812B LEDs, $< 220\text{mA}$ current draw on the 5V rail), with Night Mode power attenuation ($0.45\times$).
    - **Glitch-Free Frame Pipeline (`Raspberry/app/board_state.py`)**: Renders dynamically while `self.analysis_is_loading == True`, smoothly transitioning into the Move 1 / Ply 0 review trace and live File 'h' evaluation bar the exact frame Stockfish batch evaluation completes.
  - **Physical Gesture Integration (`Raspberry/app/gesture_engine.py`)**: Verified `CenterRoyalGateGesture` (e2 -> d2 -> replace both pieces to initial setup) triggers arrival confirmation flare and launches Stockfish pre-analysis for the just-completed match.
  - **Testing & Deployment**: Added test suites across `test_lichess_engine.py`, `test_analysis_state.py`, `test_led_animations.py`, and `test_gesture_analysis.py`. All 257 pytest unit tests passing on the physical Raspberry Pi over SSH; frontend built and `smart-chess.service` running live.
- [x] Fixed Analysis Loading Animation Pipeline & Gesture State Collision (`Raspberry/app/board_state.py`, `Raspberry/app/led_animations.py`):
  - **Root Cause of Glitch/Loop**: When the user triggered the analysis gesture (lifting `e2` and `d2`), `start_analysis_mode()` was launched while the pieces were still momentarily off the squares. The state loop saw `setup_res.is_setup_ready == False` and immediately marked `self.analysis_has_advanced = True`. When the pieces were replaced to complete the gesture, the loop saw all 32 pieces in starting position and concluded the user was trying to *exit* analysis, calling `stop_analysis_mode()` and triggering `BOARD_READY` (3 pawns lit), causing a rapid visual flicker between analysis loading and idle state.
  - **Dedicated Layer 0.6 & Strict Loading Immunity**:
    - Created a dedicated top-level LED pipeline Layer 0.6 for `render_analysis_computing` when `analysis_is_loading == True`, isolating it completely from idle gesture overlays or gameplay highlights.
    - Guarded the auto-exit condition (`if not getattr(self, "analysis_is_loading", False) and getattr(self, "analysis_has_advanced", False) and setup_res.is_setup_ready:`), and ensured `analysis_has_advanced` is ONLY marked when the player actually reviews forward in the game (`ply > 0` or branch move played).
  - **Verification**: Verified on Raspberry Pi over SSH with all 257 unit tests passing and `smart-chess.service` running live.

- [x] Implemented Automatic Conclusion of Analysis & Return to Gesture-Ready IDLE on Full Board Reset:
  - **Full Setup Recognition during Analysis (`Raspberry/app/board_state.py`)**: Added starting position setup validation (`setup_validator.validate(physical_state).is_setup_ready`) inside the Analysis mode update loop.
  - **Auto-Exit to Default State**: Once the player has reviewed/progressed through the analysis (or moved pieces during analysis) and puts all 32 physical pieces back into their standard initial starting ranks (White on rows 1-2, Black on rows 7-8, center rows empty):
    - Automatically concludes Analysis mode (`stop_analysis_mode()`).
    - Transitions `game_status` back to `"IDLE"`.
    - Triggers the `BOARD_READY` illumination ripple animation.
    - Re-activates the `PhysicalGestureEngine` (`gesture_engine.reset()`) to immediately begin listening for physical gestures (e.g. starter gestures, double-taps, rematch gates).
  - **Testing & Deployment**: Added unit test `test_analysis_board_reset_to_starting_position_transitions_to_idle` in `test_analysis_state.py`. Verified all 250 unit tests passing on the Raspberry Pi over SSH.
- [x] Implemented Automatic Snap-Back to Game Timeline upon Physical Anchor Restoration:
  - **Automatic Divergence Resolution (`Raspberry/app/board_state.py`)**: Added `_check_analysis_board_restoration()` executing on each cycle of the background state update loop during Analysis mode.
  - **Physical State Validation**: When the player is in an off-game virtual branch, once the board detects that all physical pieces have been put back into the exact configuration of the divergence anchor position (the ply where the divergence began), it automatically snaps back to the main game timeline:
    - Clears the anchor coordinate (`analysis_anchor_coord = None`), anchor ply, and virtual branch moves.
    - Restores the active game review board to `analysis_anchor_ply`.
    - Resets the physical move tracker and triggers a brief arrival confirmation flash.
    - Immediately re-renders the game move at that ply (with move quality trajectory animations, comet pulse, or blunder refutations) and allows the user to seamlessly resume stepping through the game.
  - **Step-by-Step Branch Undo**: Also supports undoing branch moves step-by-step; if the player takes back moves along the branch, it updates the branch depth accordingly until returning to the anchor position.
  - **Testing & Deployment**: Added unit tests in `test_analysis_state.py` (`test_analysis_auto_snap_back_on_anchor_restoration`, `test_analysis_step_by_step_branch_undo`). All 249 unit tests pass on Raspberry Pi over SSH.
- [x] Fixed Physical & UCI/SAN Castling in Analysis Mode (Preventing False Divergence / Branching):
  - **Root Cause**: During physical castling (King moves `e1 -> g1`, followed by Rook `h1 -> f1`), the King move advanced the active board to the next ply (changing turn to Black). When the user subsequently lifted and placed the `h1` Rook, `PhysicalMoveTracker.process_physical_state()` was falling through to standard piece movement detection instead of returning `None` while `pending_castling_rook` was active. This caused the Rook placement (`h1f1`) to be emitted as a separate move for Black, creating an unwanted off-game virtual branch.
  - **Physical Tracker Castling Absorption (`Raspberry/app/physical_tracker.py`)**: Updated `process_physical_state()` to suppress all other piece move evaluations while `pending_castling_rook` is in progress until the Rook reaches its target square or times out.
  - **Flexible Move Matching in Analysis (`Raspberry/app/board_state.py`)**: Updated `handle_analysis_move()` to seamlessly match both UCI (`e1g1`, `e1c1`, `e8g8`, `e8c8`) and SAN (`O-O`, `O-O-O`, `0-0`, `0-0-0`) moves without treating castling notations as divergences.
  - **LED Guidance for Castling Rook (`Raspberry/app/board_state.py`)**: Added visual LED prompts and animated traces for `pending_castling_rook` in Review mode so the player sees clear physical cues to complete the Rook move.
  - **Testing & Deployment**: Added unit tests in `test_analysis_state.py` covering physical castling absorption, auto-advance on castling, and SAN/UCI matching. All 247 unit tests passing on the Raspberry Pi over SSH.
- [x] Installed & Optimized **Stockfish 17.1** with NNUE & Multi-Core Pre-Analysis:
  - **Engine Installation**: Installed the latest official **Stockfish 17.1 (ARM64 with NNUE neural networks)** directly onto the Raspberry Pi system (`/usr/games/stockfish`).
  - **Multi-Threading & Memory Hash (`Raspberry/app/coach_engine.py`)**: Configured UCI engine options to utilize 3 CPU cores (`Threads: 3`) and 64 MB of transposition hash memory (`Hash: 64`), reaching >100,000 nodes/second evaluation speed on the Pi.
  - **Instant Move Navigation via Upfront Pre-Analysis**: When a game is loaded into Analysis Mode, `coach_engine.batch_evaluate_game()` pre-evaluates all positions and classifies all moves upfront in memory. Stepping forward/backward through moves (`step_analysis`) is 100% instantaneous ($0\text{ms}$) with zero lag and immediate LED animations.
  - **Thread-Safe Synchronization**: Added `asyncio.Lock` to serializing UCI protocol commands and handled `asyncio.CancelledError` gracefully during rapid asynchronous evaluations.
  - **Verification**: Verified all 244 unit tests passing, `smart-chess.service` running Stockfish 17.1 live as a child process, and verified API responses returning full evaluations in <1s.
- [x] Protected `board_settings.json` against accidental test overwrites & added automatic backup:
  - **Root Cause**: Traced that when `pytest` ran on the Raspberry Pi during deployment, unit tests (`test_calibrate_board_clears_baseline_history`, `test_step2_completion_toggles_night_mode`, `test_seek_routing_over_8_mins_to_human`) executed code paths that called `save_settings()` against the live `/home/pi/chess_git/Raspberry/board_settings.json` file without redirecting `BOARD_SETTINGS_PATH` to a temporary directory, overwriting physical calibration baselines with dummy test values (`1900` / defaults).
  - **Session-Scoped Test Sandboxing (`Raspberry/conftest.py`)**: Added a global session fixture that redirects `BOARD_SETTINGS_PATH` into an isolated temporary directory for the duration of the test suite. All tests execute reads and writes in a sandbox without touching the physical board's configuration.
  - **Per-Test Settings Isolation (`Raspberry/conftest.py`)**: Added an autouse function fixture that cleanly snapshots and restores factory default in-memory settings between individual tests, preventing test pollution.
  - **Automatic Live Backup (`Raspberry/board_hardware.py`)**: Updated `save_settings()` to create an automatic backup (`board_settings.json.bak`) whenever settings are persisted on the physical board.
  - **Verification**: Verified on the Raspberry Pi over SSH that all 244 unit tests pass cleanly, `board_settings.json` timestamp remains untouched after running pytest, and `smart-chess.service` starts and runs without any configuration loss.
- [x] Implemented Lichess Match History & Direct Analysis Mode Loading:
  - **Lichess API Game History Engine (`Raspberry/app/lichess_engine.py`)**: Added `get_user_recent_games(username, max_games)` streaming and parsing NDJSON records from `GET https://lichess.org/api/games/user/{username}`. Automatically extracts user perspective (White vs Black), opponent username/rating/title/AI status, game result (Win/Loss/Draw), opening name and ECO code, time control, creation date, and converts SAN move strings into full UCI move lists using `python-chess`.
  - **REST API Endpoint (`Raspberry/app/main.py`)**: Added `GET /api/lichess/games/recent?max_games=10` returning structured game summaries ready for 1-click analysis.
  - **Frontend UI & Interactive Picker (`Raspberry/frontend/src/components/AnalysisTab.tsx` & `Raspberry/frontend/src/api.ts`)**:
    - Added "Recent Lichess Matches" interactive drawer in Analysis Mode (`Game Review` submode).
    - Features match cards showing Win/Loss/Draw badges, White/Black piece indicators, opponent names/ratings, opening details, time controls, move counts, and external links to Lichess.org.
    - Added 1-click "⚡ Analyze" action that feeds the game's UCI moves directly into the Stockfish batch analysis pipeline, lighting up physical LED piece trajectory animations, blunder training puzzles, and centipawn loss graphs.
  - **Testing & Deployment**: Added unit tests in `test_lichess_engine.py` and `test_api_routes.py`. Compiled frontend (`tsc -b && vite build`), passed all 244 unit tests on Raspberry Pi over SSH, and restarted `smart-chess.service`.
- [x] Implemented Analysis Mode Move Quality Animations, Delta-Based Color Rules, Best Move Guidance, and Off-Game Variation Indicators:
  - **Full Move Animations in Review Mode**: Fixed the missing animation issue in Analysis mode by wiring `interpolate_move_path()`, `render_move_trace()`, and `render_castle_trace()` directly into the `BoardStateManager._update_leds()` review pipeline.
  - **Delta-Based Move Classification & Colors**:
    - **Rule A ($\Delta\text{cp} \le 60$ / Best or Good)**: Best moves ($\Delta \le 15\text{cp}$) animate the full piece trajectory in **Mint Emerald** (`COLOR_MINT_EMERALD = (0, 220, 140)`); Good moves ($15 < \Delta \le 60\text{cp}$) animate in **Cyan Azure** (`COLOR_AZURE = (0, 160, 255)`). Alternative move suggestions are suppressed to maintain a clean board focus.
    - **Rule B ($\Delta\text{cp} > 60$ / Inaccuracy or Blunder)**: Inaccuracies ($60 < \Delta \le 150\text{cp}$) animate in **Warm Sun Amber** (`COLOR_MOVE_INACCURACY = (220, 160, 0)`); Blunders ($\Delta > 150\text{cp}$) animate in **Laser Crimson** (`COLOR_MOVE_BLUNDER = (220, 24, 40)`). Simultaneously suggests the engine's best refutation move by lighting origin and target in breathing Emerald Green and rendering the best move trajectory interleaved with a $180^\circ$ phase offset.
  - **Off-Game Variation Sandbox Indicators**:
    - When a player plays an alternative move to diverge from the main game timeline, the anchor square is solidly illuminated in **Royal Violet** (`COLOR_ROYAL_VIOLET = (140, 40, 240)`), and all 4 corner rooks (`a1`, `h1`, `a8`, `h8`) pulse with a subtle 0.5 Hz breathing Royal Violet beacon as a perimeter sandbox boundary.
    - If cached engine evaluations exist for the diverged position, the engine's best reply is animated dynamically.
  - **React Frontend UI Enhancements (`AnalysisTab.tsx`)**:
    - Updated quality badges, delta thresholds, and tooltips matching Mint Emerald, Cyan Azure, Warm Amber, and Laser Crimson.
    - Prominent Off-Game Variation Sandbox banner indicating diverged ply count, anchor coordinate, physical board LED cues, and a one-click "Return to Game Timeline" button.
  - **Testing & Deployment**: Added unit test suite in `test_analysis_state.py` covering all LED rendering rules. Successfully built frontend (`tsc -b && vite build`), verified all 242 pytest test suites on Raspberry Pi over SSH, and restarted `smart-chess.service`.
- [x] Configured automatic startup on Raspberry Pi boot via systemd service (`Raspberry/smart-chess.service` installed to `/etc/systemd/system/smart-chess.service`):
  - **Service Specification**: Runs under user `pi`, working directory `/home/pi/chess_git/Raspberry`, loads `.env` secrets, executes `/home/pi/venv/chess/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` with `Restart=always` and `RestartSec=5s`.
  - **Verification**: Enabled and started with `systemctl enable --now smart-chess`. Verified active status, automatic restart resilience, journalctl logging, and clean API responses on port 8000.
- [x] Reworked LED ordering to a clean 2 LEDs/square base for Strip 1 (files a-d) and disabled Strip 2 (files e-h) completely.
- [x] Fixed software bug causing duplicate transposed square highlighting (e.g., lighting A4 also lighting D1) in `BoardStateManager._update_leds()`.
- [x] Configured real 18-LED column offset positions for Strip 1 (accounting for 2 skipped OFF LEDs after Rank 7 and Rank 3).
- [x] Implemented Strip 2 (files e-h) 2 LEDs/square base serpentine mapping starting at h8 down to h1, g1 to g8, f8 to f1, and e1 to e8.
- [x] Updated board recalibration function (`calibrate_board`) and baseline window (`baseline_window_s`) to use a 2-second continuous sampling window.
- [x] Implemented automatic 5-second ±1000 threshold recalibration sequence upon webapp WebSocket connection establishment.
- [x] Added webapp UI visual feedback banner during initial calibration and auto-restore parameter controls in the Calibration & Threshold tab upon completion.
- [x] Made row quadrant swap (1-4 ↔ 5-8) for right-side files e-h active by default when `swap_row_quadrants_right` is `False`.
- [x] Removed "Swap Row Quadrants a-d (1-4 ↔ 5-8)" and "Swap Row Quadrants e-h (1-4 ↔ 5-8)" options from the webapp frontend UI.
- [x] Disabled and suppressed LED illumination during initial webapp connection recalibration and manual board baseline calibration.
- [x] Fixed serial lock deadlock during webapp connection recalibration by upgrading `serial_lock` from non-reentrant `threading.Lock` to re-entrant `threading.RLock`.
- [x] Fixed row 1-4 ↔ 5-8 quadrant swap mismatch between webapp and physical board by setting row quadrant swap flags to false by default and correcting Strip 1 serpentine `sq_idx` calculation in `led_helpers.py` so rank 1 (`col=0`) maps to physical LED index 0 at `a1` and rank 8 (`col=7`) maps to physical LED index 16 at `a8`.
- [x] Added "Force All LEDs Off" button to webapp control interface and created corresponding `/api/board/clear_leds` backend endpoint.
- [x] Completely removed quadrant swapping logic and options from backend, hardware scanner, LED helpers, webapp frontend, and tests.
- [x] Removed inverted channel mapping (`7 - rank_idx`) for `COL_MUX` in ESP32 firmware [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino#L48-L51), mapping `COL_MUX` channels 0–7 directly to Ranks 1–8.
- [x] Fixed "Force Recalibrate Baselines" button by clearing `baseline_history` upon calibration completion in [`board_hardware.py`](file:///home/robin/Smart-Chess-Board/Raspberry/board_hardware.py#L313) (preventing background scan loop from immediately overwriting new baselines with pre-calibration averages) and adding serial buffer resync on framing timeout.
- [x] Updated [`Raspberry/ESP32_firmware/WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt) to reflect 8x8 matrix topology using analog linear Hall effect sensors (VCC/2 ratiometric output), active ADC reading on `GPIO 34`, and current [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino) pinouts.
- [x] Migrated `WIRING_GUIDE.txt` to [`Raspberry/ESP32_firmware/WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt) and deleted the obsolete top-level `ESP32/` prototype directory.
- [x] Increased upper and lower deviation threshold limits to 3000 in the webapp UI (range sliders up to 3000 and direct numeric inputs).
- [x] Fixed row/column transposition between physical board and webapp by updating MUX scan order (`file_idx` outer loop, `rank_idx` inner loop) in [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino) and [`board_hardware.py`](file:///home/robin/Smart-Chess-Board/Raspberry/board_hardware.py) so selecting a column in webapp manual mode activates the corresponding column (Files a-h) on the physical board.
- [x] Created `codebase-optimization` skill (`.agents/skills/codebase-optimization/SKILL.md`), reference guides (`python-optimization.md`, `typescript-optimization.md`), and automated static analysis audit script (`run_audit.py`).
- [x] Executed full codebase optimization pass across Python backend, hardware drivers, Playwright scripts, and React frontend: eliminated dead functions/unused constants, resolved all Mypy static type errors, removed inline module imports from tight loop execution paths, and optimized React state/effect dependencies and piece rendering allocations. All audit gates (`ruff`, `vulture`, `mypy --check-untyped-defs`, `tsc`, `knip`, `eslint`, `vite build`) pass cleanly with 0 errors.
- [x] Fixed file-axis (column) reversal in `board_hardware.py` (`scan_board` & `calibrate_board`) and `hardware_test.py` (`read_active_values`) where `c` was iterated in reverse (`range(BOARD_COLS - 1, -1, -1)`). This ensures magnet detection on square `a1` correctly maps to `matrix[0][0]` and illuminates LEDs on square `a1` (instead of `h1`). All 34 pytest unit test suites pass on the physical Raspberry Pi over SSH and Playwright browser integration tests pass.
- [x] Configured exact serpentine physical LED strip routing in [`led_helpers.py`](file:///home/robin/Smart-Chess-Board/Raspberry/playwright_chesscom/led_helpers.py) and documented in [`WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt):
  - **Strip 1 (left side / files a-d)**: Starts at `a8` (LED 0, 1) -> `a1` (LED 16, 17) [Down], `b1` -> `b8` [Up], `c8` -> `c1` [Down], `d1` -> `d8` [Up].
  - **Strip 2 (right side / files e-h)**: Starts at `h8` (LED 76, 77) -> `h1` (LED 90, 91) [Down], `g1` -> `g8` [Up], `f8` -> `f1` [Down], `e1` -> `e8` [Up].
- [x] Standardized Antigravity Custom Agent YAML frontmatter format across all agent files in `.agents/agents/` (`arch.md`, `automation.md`, `creative.md`, `dev.md`, `explorer.md`, `hardware.md`, `qa.md`).
- [x] Implemented thread-safe `SettingsManager` in `board_hardware.py` with atomic JSON persistence, locking controls, auto-migration, and backward-compatible dictionary magic methods.
- [x] Cleaned up fragile `sys.path.append` hacks across FastAPI `main.py`, `board_state.py`, and `chess_engine_async.py`.
- [x] Successfully deployed and verified code changes on Raspberry Pi over SSH: frontend build succeeded (`vite build`) and all 34 pytest unit/integration tests passed cleanly.
- [x] Migrated Playwright browser automation driver (`chesscom_browser.py`, `game_seeker.py`, `interactive_game.py`, `test_connection.py`, `chess_engine_async.py`) from synchronous `playwright.sync_api` to asynchronous `playwright.async_api`, enabling native `asyncio` execution in FastAPI without thread starvation. Verified via 34 passing pytest tests on Raspberry Pi over SSH.
- [x] Implemented Lichess Board API async integration (`Raspberry/app/lichess_engine.py`), replacing legacy Playwright automation with direct NDJSON streaming and OAuth authentication.
- [x] Created centralized config (`Raspberry/app/config.py`) and standalone LED helper library (`Raspberry/app/led_helpers.py`), decoupling board hardware from web scrapers.
- [x] Archived legacy Playwright automation scripts into `Raspberry/legacy_chesscom_backup/` and updated `.gitignore` and `Raspberry/requirements.txt`.
- [x] Implemented Virtual-Only mode with real-time UI toggle, pawn promotion modal dialog, active turn clock glowing indicator with low-time warning, check indicator ring, and legal move dots in `Raspberry/frontend/src/App.tsx`.
- [x] Added unit tests for Lichess engine (`test_lichess_engine.py`) and updated test suites (`test_board_state.py`, `test_api_routes.py`, `test_led_helpers.py`, `test_highlight_row_swap.py`).
- [x] Resolved Lichess Board API time control restriction (`Invalid time control` on Blitz seeks) by adding native Stockfish AI challenge support (`POST /api/challenge/ai`), difficulty levels 1–8, and auto-routing matches < 8 minutes (Bullet/Blitz) to instant AI play while preserving live human matchmaking for Rapid/Classical. Verified live virtual board game creation, move execution (`e2e4` -> Stockfish `e7e5`), and 52 passing pytest tests on the Raspberry Pi over SSH.
- [x] Added configurable ELO rating boundaries (`ratingRange` parameter in `POST /api/board/seek`) to backend and web frontend, supporting presets (`Any`, `±100`, `±200`, `±300`, `±500`) and custom Min/Max ELO filters. All 53 unit/integration tests and frontend production build verified on Raspberry Pi.
- [x] Restored dynamic baseline drift tracking for empty middle ranks (Ranks 3-6) in `scan_board()` with starting piece ranks (Ranks 1-2 and 7-8) inheriting Rank 3 and Rank 6 baseline updates per column, preventing piece magnet absorption while maintaining live ambient temperature/voltage drift compensation.
- [x] Implemented smart piece auto-detection against reference ranks 3 & 6, 3-way mode switch (`Auto` / `Pieces Placed` / `Empty Board`), ±100 default thresholds, 1000 max slider cap, and live Web UI status badge.
- [x] Fixed LED flickering on physical player moves by implementing `in_flight_move` state locking in `PhysicalMoveTracker` (suppressing 50-100Hz re-trigger loops during network latency) and differential zero-blackout LED updates in `DualPixelStrip.show()`.
- [x] Implemented animated move traces and full-board lifecycle animations:
  - **Move Trace Flow**: Dynamic Gaussian comet pulse flowing along piece trajectory (orthogonal ranks/files, diagonals, Knight L-shapes, Bresenham lines) rendered in vibrant magenta (`COLOR_MOVE_TRACE`), while keep start (amber) and arrival (cyan) squares continuously lit.
  - **Game Lifecycle Animations**: Procedural non-blocking animations for **Game Start** (radial expanding emerald wave), **Victory** (cascading gold & emerald celebration waves), **Defeat** (collapsing perimeter crimson wave), and **Draw** (symmetrical sapphire & white curtain sweep).
  - **API & Web UI Controls**: Added `/api/leds/trigger_animation` and `/api/leds/test_trace` endpoints and debug testing buttons in `App.tsx`.
  - **Verification & Deployment**: All 94 unit/integration test suites and frontend production build verified cleanly on the physical Raspberry Pi over SSH.
- [x] Applied 20% power and brightness reduction across all LED color channels and `LED_BRIGHTNESS` (from 50 to 40) in [`config.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/config.py) to stabilize the 5V power rail, eliminate transient voltage drops, and protect Hall sensor analog baseline stability during dense full-board animations. Verified on Pi with 94 passing pytest tests.
- [x] Implemented baseline freezing and sensor reading suppression during animations:
  - **Baseline Freezing**: Snapshots analog baselines before full-board lifecycle animations and LED diagnostic tests, suppresses dynamic baseline drift tracking during animation frames, and cleanly restores original baselines and resets drift window upon animation completion.
  - **Reading Suppression**: Freezes physical piece state and disables debounce move tracking during active animations, preventing power-drop voltage ripples from triggering false piece lifts or invalid placements.
  - **Default Thresholds Updated**
- [x] Implemented animated move trace arrival pulse, capture move distinction, and settings protection:
  - **Arrival Square Pulse Flare**: Enhanced `render_move_trace()` with virtual trajectory overshoot and additive luminance flare on the arrival square upon comet arrival, supporting 1-step moves (e.g. `e2e3`) and seamless wrap-around continuity.
  - **Capture Move Visual Distinction**: Added `COLOR_OPPONENT_CAPTURE` (`(192, 0, 32)`) and `COLOR_CAPTURE_TRACE` (`(204, 32, 64)`). Wired `is_capture` detection in `PhysicalMoveTracker.sync_game()` and `LichessEngine.get_game_payload()`, layering distinct ruby/crimson destination highlights and fiery trace pulses on capture moves.
  - **Hardware Settings Isolation & Git Protection**: Untracked `board_settings.json` from git, added it to `.gitignore`, created tracked default template `Raspberry/board_settings.default.json`, and implemented 3-tier fallback initialization in `board_hardware.load_settings()` to guarantee user baselines/thresholds are never overwritten on `git pull`.
  - **Web UI & REST API**: Extended `POST /api/leds/test_trace` and frontend UI with capture move trace testing (`d4 ⚔ e5`).
- [x] Redesigned victory animation (`render_game_won`) to be lightweight and low-power:
  - Replaced full-board 64-square sinusoidal wash with dual high-speed sweeping diagonal laser comets ($a1 \to h8$ gold beam and $a8 \to h1$ emerald counter-beam), sparse high-threshold stardust twinkles (1-2 squares max), and a central diamond flare ($d4, d5, e4, e5$).
  - Reduced peak active simultaneous squares from 64 down to 3-6 squares (< 10% of board) and reduced power draw by > 90% while dramatically improving visual contrast and fluidity.

- [x] Configured default positive and negative analog deviation thresholds to **±200** across backend defaults, fallback templates, and web UI.
- [x] Implemented continuous settings remembering in Web UI:
  - All slider movements and mode toggles (positive/negative shift, scan delay, col mode, pieces mode, settle time, debounce threshold, baseline window) immediately sync to `localStorage` and debounced auto-persist to the FastAPI backend (`board_settings.json`).
- [x] Implemented continuous "Waiting for Opponent" (Seeking) radar animation:
  - **Perimeter Orbital Comet**: Clockwise orbital pulse along the 28 perimeter squares ($a1 \to h1 \to h8 \to a8 \to a1$) with bright cyan-white head (`(140, 240, 255)`), electric azure body (`(0, 140, 255)`), and deep sapphire decay (`(0, 36, 160)`).
- [x] Implemented immediate visual confirmation flash on move arrival square:
  - **Arrival Registration Feedback**: Whenever a physical move or opponent mirror move is registered on the physical board, triggers an instant 450ms exponential-decay flash on the destination square.
  - **Color Coding**: High-contrast vibrant emerald green (`COLOR_MOVE_CONFIRM = (48, 255, 128)`) for standard quiet moves; radiant ruby crimson (`COLOR_CAPTURE_CONFIRM = (255, 32, 64)`) for capture moves.
- [x] Implemented distinct color differentiation for legal capture targets:
- [x] Implemented choreographed 2-phase castling animation and physical dual-piece mirror tracking:
  - **2-Phase Choreography**: For Kingside and Queenside castling (e1g1, e1c1, e8g8, e8c8), Phase 1 ($\tau \in [0.0, 0.5]$) animates the King's 2-square move with destination flare, and Phase 2 ($\tau \in [0.5, 1.0]$) animates the Rook's move with destination flare (`render_castle_trace()`).
  - **Player & Opponent Symmetry**:
    - When the opponent castles, both King and Rook moves are animated in sequence and 4 squares are illuminated until both pieces are physically mirrored.
- [x] Implemented Board Setup Ready Detection Animation & Persistent Ready Visual Indication:
  - **State Machine Edge Detection (`Raspberry/app/board_state.py`)**: Automatically detects the exact rising edge (`is_setup_ready` changes from `False` to `True`) during `IDLE`, `SETUP`, and `GAME_OVER` states and triggers the celebratory 1.4s `BOARD_READY` animation. Falling edge immediately cancels any active ready animation and restores sensor baselines so missing piece indicators display without delay.
  - **Procedural 3-Phase Animation (`Raspberry/app/led_animations.py` `render_board_ready`)**:
    1. Phase 1 ($0.00 \le \tau < 0.48$, Dual Army Inward Sweep): Symmetrical inward sweep from flank files (a/h) toward center (d/e) along Ranks 1-2 (White) and Ranks 7-8 (Black) with emerald and gold/cyan secondary blending.
    2. Phase 2 ($0.48 \le \tau < 0.76$, Center Battle Line Harmony Flare): Gentle sinusoidal diamond flare on center battle squares (`d4`, `e4`, `d5`, `e5`).
    3. Phase 3 ($0.76 \le \tau \le 1.00$, Settle & Anchor Transition): Fades center light while illuminating the 4 corner rooks (`a1`, `h1`, `a8`, `h8`) and 2 kings (`e1`, `e8`) to transition seamlessly into the ambient steady indication.
    - Strict power budget: Max $\le 8$ simultaneous illuminated squares at any single instant ($< 13\%$ of board).
  - **Persistent Visual Indication ("The Royal Guard Anchor")**: Layer 1 in `_update_leds()` continuously renders a gentle 0.5 Hz breathing glow on the 4 corner rooks (`a1`, `h1`, `a8`, `h8`) and 2 kings (`e1`, `e8`) whenever all 32 pieces are in place and no animation or physical gesture is active.
  - **Night Mode Adaptability**: Full support for both Day Mode (warm emerald / gold-lime) and Night Mode (vivid aqua / electric cyan against deep moonlight blue floor).
  - **Web Frontend (`Raspberry/frontend/src/App.tsx`)**: Dynamic "Board Setup Complete" emerald confirmation banner in the Play tab, real-time "Physical Board Ready" badge and green aura on the board sensor overlay, and "Board Ready (Emerald)" debug test trigger button.
  - **Verification**: All 220 pytest tests pass cleanly on the physical Raspberry Pi over SSH and frontend production build succeeds with 0 errors.
- [x] Implemented Live Perimeter Evaluation Bar & Blunder Guard (Color-Coded Move Quality):
  - **Asynchronous Coach Engine (`Raspberry/app/coach_engine.py`)**: Real-time position analysis with multi-PV candidate evaluation, logistic win probability ($W = \frac{100}{1 + 10^{-cp / 400}}$), move delta classification (`best` $\le 10$ cp, `good` $\le 50$ cp, `inaccuracy` $\le 150$ cp, `blunder` $> 150$ cp), FEN caching, and graceful offline heuristic fallback.
  - **Physical LED File 'h' Perimeter Eval Bar (`app/board_state.py`)**: Ranks 1–8 along File 'h' (Strip 2, row 7) continuously render a smooth White vs Black win chance gauge when enabled during AI matches.
  - **Blunder Guard Destination Color Tiers**: When a piece is physically lifted or selected on the digital board during an AI match, destination squares are dynamically illuminated in Emerald Green (`BEST`), Cyan (`GOOD`), Amber (`INACCURACY`), or Crimson (`BLUNDER`).
  - **Strict Fair-Play Invariant**: All coaching hints and live evaluation bars are strictly active only in matches against Stockfish AI, and hard-disabled in online matches against human opponents on Lichess.
- [x] Implemented Automated & Manual Lichess Victory Claiming on Opponent Disconnection:
  - **Automated Stream Countdown & Task Scheduler (`Raspberry/app/lichess_engine.py`)**: Listens to Lichess `opponentGone` NDJSON events. When an opponent leaves, tracks remaining seconds (`claimWinInSeconds`) and automatically claims victory via `POST /api/board/game/{game_id}/claim-victory` as soon as the waiting window expires without requiring browser intervention.
  - **Reconnection & Lifecycle Task Cancellation**: Seamlessly cancels pending auto-claim timers if the opponent returns before the timer elapses, or if the game finishes, is resigned, or is aborted.
  - **Real-Time WebSocket State**: Streams `opponent_gone: { gone: bool, claim_win_in: number }` across `/ws/state`.
  - **REST API Endpoints (`Raspberry/app/main.py`)**: Added `POST /api/lichess/claim-victory` and `POST /api/game/claim-victory`.
  - **React UI Banner & Manual Claim**: Animated "Opponent Disconnected" countdown banner in the Play tab with smooth 1-second countdown and active "Claim Victory" button.
- [x] Implemented In-Loop Auto Calibration Toggle (Active by Default, Switchable In-Game):
  - **Dynamic Baseline Drift Gating (`Raspberry/board_hardware.py`)**: Gated the continuous background analog baseline drift compensation on `settings["in_loop_calibration"]` (defaults to `True`). When disabled, baseline drift calculations are suppressed and static baselines are preserved.
  - **FastAPI & REST Persistence (`Raspberry/app/main.py`)**: Added `in_loop_calibration` to `ThresholdSettings` model and `POST /api/board/settings` with auto-save to `board_settings.json`.
  - **React UI In-Game Switch (`Raspberry/frontend/src/App.tsx`)**: Added an accessible **"In-Loop Auto Calibration"** toggle switch in both the **Play Tab** (for live adjustments during ongoing matches) and the **Debug Tab** (in the Initial Pieces Detection panel), with full local storage caching and server state synchronization.
- [x] Implemented Single-Square Baseline Calibration on Left-Click (Replaced Highlight Feature):
  - **Individual Square Baseline Setting (`Raspberry/board_hardware.py`)**: Added `set_square_baseline(col, row, value)` to immediately adopt the current ADC reading as that square's baseline and flush any stale drift history.
  - **REST API (`Raspberry/app/main.py`)**: Added `POST /api/board/calibrate_square` taking `{ col, row, value? }` with atomic persistence to `board_settings.json`.
  - **React UI Integration (`Raspberry/frontend/src/App.tsx`)**: Left-clicking any square in the **Play tab sensor matrix overlay** or **Debug tab physical ADC matrix** immediately calibrates that specific square's baseline to its live reading and displays a confirmation status toast.
- [x] Resolved Raspberry Pi `git pull` hanging issue:
  - **SSH Firewall / Outbound Block**: Identified that outbound SSH port 22 and 443 connections on the Raspberry Pi's local network timed out when connecting to GitHub.
  - **Remote Switch to HTTPS**: Reconfigured `origin` remote URL in `~/chess_git` on the Pi to HTTPS (`https://github.com/Niorb/Smart-Chess-Board.git`), enabling instant pulls.
  - **Physical Tracker & Test Isolation Fixes**: Initialized `_last_synced_move_uci` in `PhysicalMoveTracker.__init__` and isolated `test_board_hardware.py` in-loop calibration unit tests. Verified all 170 unit and integration tests passing on the physical Pi.
- [x] Implemented In-Game Safety Guardrails & Capture-in-Progress Handling:
  - **Live State Guardrail Synchronization (`Raspberry/app/setup_validator.py`)**: Continuously compares physical board matrix against digital engine state (`lichess_engine.board`), intelligently filtering out legitimate transient states (lifted friendly piece, legal capture destinations, pending capture target, pending opponent mirror, castling rook movement, and in-flight move locks).
  - **Capture-First State Machine (`Raspberry/app/physical_tracker.py`)**: Seamlessly supports player lifting opponent's piece first when taking a piece. Identifies valid candidate friendly attackers, preserves capture intent, supports lifting candidate attacker or direct piece placement, and cancels intent if the opponent piece is returned.
  - **Dynamic LED Animations & Alerts (`Raspberry/app/led_animations.py` & `board_state.py`)**:
    - **Capture-in-Progress Aura**: Sinusoidal pulsing radiant ruby aura (`(255, 32, 64)`) on capture destination with warm golden breathing glow (`(220, 160, 20)`) on candidate attacking squares.
    - **Guardrail Mismatch Feedback**: Rapid amber pulse (`(204, 120, 0)`) on missing piece squares and alert crimson pulse (`(204, 0, 0)`) on unexpected piece squares.
  - **Frontend UI Overlays & Alerts (`Raspberry/frontend/src/App.tsx` & `useBoardState.ts`)**: Real-time "Capture in Progress" banner, "Board State Mismatch" alert banner, and virtual chessboard square highlight rings/badges.
- [x] Reworked Game Started Animation, Active Turn Indicator & Opponent Disconnected Victory Claim Gauge:
  - **Low-Power Color-Differentiated Game Started Animation (`Raspberry/app/led_animations.py`)**: Replaced power-heavy full-board radial wave with a lightweight, high-contrast army ignition sweep and royal pulse. Uses max 2–4 simultaneous active squares (< 6% board, < 50mA total draw), eliminating power drop artifacts. Color-announces player assignment: sweeping luminous warm ivory/gold across Ranks 1–2 with King $e1$/Queen $d1$ pulse for White, and cosmic electric cyan/sapphire across Ranks 8–7 with King $e8$/Queen $d8$ pulse for Black.
  - **Active Player Turn Ambient Halo (`Raspberry/app/board_state.py`)**: Renders a subtle, non-intrusive breathing aura on the active turn King ($e1$ or $e8$) with color matching the active player (warm ivory for White, azure for Black), automatically suppressed when the King is in check or lifted.
  - **Physical Opponent Disconnected Beacon & Victory Claim Countdown Gauge (`Raspberry/app/led_animations.py` & `lichess_engine.py`)**: Renders an alert amber beacon on the opponent King square and a linear 8-LED countdown progress bar along the opponent's back rank that smoothly drains down as the victory claim timer elapses.
  - **UI Triggers & Unit Tests (`Raspberry/frontend/src/App.tsx` & `tests/`)**: Added Start (White) and Start (Black) animation debug triggers in the webapp, updated `test_led_animations.py`, and added test suites in `test_board_state.py`.
- [x] Implemented Extensible Physical Board Gesture Engine & "Restart Previous Game" Kingside Corner Gate:
  - **Extensible Physical Gesture Framework (`Raspberry/app/gesture_engine.py`)**: Created `BaseGesture` abstract base class and `PhysicalGestureEngine` subsystem manager. Gated to `IDLE` and `GAME_OVER` states, providing pluggable gesture registration, state serialization for WebSocket broadcasting, time remaining calculations, and LED overlay generation.
  - **Kingside Corner Gate Restart Gesture (`RestartPreviousGameGesture`)**:
    - **Step 1 (Armed)**: Lifting White $h2$ pawn from initial starting setup illuminates $h2$ in solid amber and pulses $h1$ in vibrant azure.
    - **Step 2 (Prompt)**: Lifting White $h1$ rook while $h2$ is lifted transitions both $h1$ and $h2$ to a rapid emerald pulse.
    - **Step 3 (Completion & Auto-Seek)**: Replacing both pieces back onto their home squares confirms full board starting setup (`SetupValidator.is_setup_ready == True`), triggers a 600ms arrival confirmation flash on $h1$ and $h2$, and automatically launches matchmaking with `last_game_params`.
    - **Safety Guards & Timeouts**: 5.0-second auto-timeout, premature $h2$ replacement cancellation, and multi-piece/center square bump cancellation prevent accidental triggers.
  - **Settings Persistence (`Raspberry/board_hardware.py` & `lichess_engine.py`)**: Added `last_game_params` schema to `board_settings.default.json` and automatically persist time control, rating range, color, opponent mode, and AI difficulty upon every seek.
  - **REST API Endpoints (`Raspberry/app/main.py`)**: Added `GET /api/game/last_params` and `POST /api/game/restart_previous`.
  - **Frontend UI & Visual Feedback (`Raspberry/frontend/src/App.tsx`)**: Added a quick-action "Restart Previous Game" button with subtitle parameters in the Play tab, and an animated Physical Gesture status banner with real-time countdown.
- [x] Reworked Game Lost (Defeat) Animation to Low-Power "The Sovereign's Requiem":
  - **Strict Low-Power Budget**: Replaced heavy full-board collapsing ring with a cinematic 3-phase sequence strictly limited to **max 1–3 simultaneous active squares** (< 5% of board, $< 75\text{mA}$ total current draw), eliminating power rail drops and voltage sag.
  - **3-Phase Narrative Choreography**:
    - **Phase 1 (0.00 $\to$ 0.35) — Checkmate Strike Ray**: A laser bolt tracking from opposing lines directly into the defeated King's square with a blazing ruby strike head and crimson fissure tail (1–2 squares).
    - **Phase 2 (0.35 $\to$ 0.70) — Crown Shatter & Radial Spark Dispersal**: Crown fracture upon impact, sending 3 amber-gold/ruby shards flying outward along divergent vectors into the board (max 3 squares).
    - **Phase 3 (0.70 $\to$ 1.00) — Monarch's Dying Ember Pulse**: Lone dying heartbeat pulse on the King's square in smoldering ruby and cinder amber fading into total black (1 square).
- [x] Implemented "Save Current Stats as Defaults" Persistent Calibration & Settings Store:
  - **Persistent Defaults Architecture (`Raspberry/board_hardware.py`)**: Added `save_defaults(overwrite_factory_template=True)` function that atomically writes live in-memory baselines, thresholds, timing delays, and board modes to both `board_settings.json` and the factory fallback template `board_settings.default.json`.
  - **FastAPI REST Endpoint (`Raspberry/app/main.py`)**: Added `POST /api/board/save_defaults` accepting `SaveDefaultsRequest` with full parameter overrides and atomic background persistence.
  - **React UI Integration (`Raspberry/frontend/src/App.tsx` & `api.ts`)**:
    - Added dedicated **"Save Current Stats as Defaults"** button in the Debug tab under Calibration & Hardware Utilities.
    - Captures live active baselines (including dynamic in-loop calibrated drifts and manual individual square calibrations), active positive/negative deviation thresholds, multiplexer timings, debounce settings, and piece modes.
    - Synchronizes browser `localStorage` and server state with instant visual confirmation status toasts.
- [x] Implemented Binary Packet Protocol, Non-Blocking ESP32 Firmware, Self-Healing Keyframe Sync & Perceptual Gamma Correction:
  - **ESP32 Binary Framing Protocol (`Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino`)**: Upgraded UART receiver with 2048-byte RX buffer, non-blocking FSM parser (`0xAA 0x55`, CMD, LEN LE, Payload, CRC-8-CCITT), and atomic batch execution (`CMD_SET_AND_SHOW`, `CMD_CLEAR_LEDS`, `CMD_SET_ALL`, `CMD_SCAN_ADC`, `CMD_SET_SETTLE`). Eliminates ASCII byte collisions (preventing random blackouts, color flashes, or premature latching when RGB values match `'C'`, `'W'`, `'A'`, or `'B'`).
  - **Self-Healing Keyframe & Chunked Transmission (`Raspberry/app/led_helpers.py`)**: Enhanced `DualPixelStrip` with chunked binary packet transmission (up to 38 LEDs / 152 bytes per packet) and an automated 60-frame (~2.0s) periodic keyframe resync that continuously heals any physical LED signal glitches.
  - **Robust Board Hardware Scanner (`Raspberry/board_hardware.py`)**: Updated `scan_board`, `calibrate_board`, and `calibrate_board_with_pieces` with binary framed requests (`CMD_SCAN_ADC`, `CMD_SET_SETTLE`) and backwards-compatible response decoding with automatic buffer resync.
- [x] Implemented Unified 64-Square Dynamic Baseline Drift Engine (`Raspberry/board_hardware.py`):
  - **Eliminated Destructive Rank Overwrite**: Removed piece-mode middle rank propagation (`settings["baselines"][c][0] = avg_val`), preventing Rank 3 and Rank 6 from destroying individual Hall sensor quiescent baselines on Ranks 1-2 and 7-8.
  - **Independent 64-Square Dynamic Drift**: Every unoccupied square (`raw_state == 0`) across all 64 squares dynamically tracks its own rolling average over `baseline_window_s` ($\ge 80\%$ span) without copying or overwriting adjacent squares.
  - **Occupied Square Isolation & Progressive Self-Calibration**: Occupied squares with magnets hold their calibrated baselines stable and isolated. When a piece vacates a square (e.g. `1. e4`), the square automatically self-calibrates to its measured ground truth baseline once unoccupied stability is reached.
  - **Test Suite & Verification**: Added comprehensive unit test suites in `Raspberry/tests/test_board_hardware.py` verifying independent 64-square drift, piece movement vacation calibration, occupied rank non-blocking behavior, and individual quiescent offset preservation.
- [x] Redesigned Defeat Animation to "The Royal Cataclysm (Requiem for a Fallen Sovereign)":
  - **4-Phase Cyber-Physical Choreography (`Raspberry/app/led_animations.py`)**:
    - **Phase 1 (0.00 $\to$ 0.25) — The Crimson Siege**: 3 lethal ballistic laser bolts converging from opposing perimeter vectors onto the defeated King's coordinate.
    - **Phase 2 (0.25 $\to$ 0.55) — Crown Shatter & Hyper-Radial Shockwave**: Detonation flash on King's square + expanding Gaussian shockwave ring ($R \to 8.2$) + 4 flying molten crown shards.
    - **Phase 3 (0.55 $\to$ 0.80) — Fissure Decay & Obsidian Abyss**: Organic smoldering cinders with harmonic noise in a tight $3\times 3$ perimeter around the fallen throne.
    - **Phase 4 (0.80 $\to$ 1.00) — The Royal Eclipse**: Solitary biphasic cardiac heartbeat pulse ("lub-dub") fading into total blackness.
  - **Hardware Stability Budget**: Strictly capped to $\le 15$ simultaneous active squares peak, safely supported by binary packet chunking and power rail stability.
- [x] Implemented Master LED Intensity Control (10%–100%) Across Hardware & Web UI:
  - **Pipeline-Wide Dimming Hook (`Raspberry/app/led_helpers.py`)**: Scaled outgoing RGB channel values by `intensity_factor = settings.get("led_intensity", 100) / 100.0` in `DualPixelStrip.show()`. Tracks intensity state changes to dynamically re-transmit active pixels immediately upon slider movement.
  - **Backend Settings & Defaults (`Raspberry/board_hardware.py`, `main.py`, `board_settings.default.json`)**: Added `led_intensity` (10..100) to hardware settings, REST schemas (`ThresholdSettings`, `SaveDefaultsRequest`), and WebSocket state payload (`get_physical_payload()`).
  - **React UI Slider & Persistence (`Raspberry/frontend/src/App.tsx`, `api.ts`)**: Added a Master LED Intensity range slider with percentage readout and `Sun` icon in the Debug tab under Calibration & Hardware Utilities. Integrates real-time debounced auto-persistence to `board_settings.json` and sync with browser `localStorage`.
- [x] Implemented Night Mode Ambient Backlighting & Queenside Corner Gate Toggle Gesture:
  - **Ultra-Low Current Ambient Backlighting (`Raspberry/app/board_state.py`, `config.py`, `led_helpers.py`)**: When Night Mode is enabled (`night_mode: true`), all 64 squares / 152 LEDs illuminate in deep moonlight sapphire (`COLOR_INT_NIGHT_MODE = (4, 12, 28)`), drawing $<400\text{mA}$ total across the entire board. Active highlights, coaching hints, move traces, and lifecycle animations cleanly layer on top without visual disturbance.
  - **Dedicated High-Contrast Night Mode Color Palette (`Raspberry/app/config.py`, `led_helpers.py`, `board_state.py`, `led_animations.py`)**:
    - **Day Mode Preserved 100%**: All daylight colors and effects remain completely unchanged.
    - **Lifted Piece Legal Destination Dots**: Tuned to **Luminous Mint Emerald / Aqua Green (`COLOR_NIGHT_LEGAL_TARGET = (0, 210, 140)`)**, ensuring razor-sharp contrast against the deep blue floor.
    - **Active Player Turn Breathing Halos**:
      - White's turn King: **Radiant Warm Sunlight / Gold Halo (`COLOR_NIGHT_TURN_WHITE = (240, 210, 120)`)**.
      - Black's turn King: **Electric Amethyst Purple Halo (`COLOR_NIGHT_TURN_BLACK = (170, 40, 230)`)**, unmistakable and distinct from the blue ambient background.
    - **Captures & Attacks**: **Pure Laser/Radiant Crimson (`(240, 20, 60)`)** for legal captures and capture trajectory pulses.
    - **Opponent Moves & Traces**: **Solar Orange (`(230, 90, 0)`)** origin square, **Vivid Mint-Cyan (`(0, 220, 200)`)** destination square, and **Vivid Magenta/Neon Violet (`(220, 30, 180)`)** comet trail.
    - **Evaluation Bar & State Overlays**: **Bright Pearl Silver (`(150, 150, 190)`)** and **Velvet Violet (`(60, 10, 95)`)** for evaluation bar, **Starlight Silver (`(70, 80, 110)`)** for missing setup pieces, and **Vivid Amber (`(220, 60, 0)`)** for misplaced pieces.
    - **Procedural Animations**: Updated `render_seeking`, `render_game_drawn`, `render_game_started`, `render_capture_aura`, and `render_guardrail_mismatch` to adapt to the Night Mode background.
  - **Queenside Corner Gate Physical Toggle Gesture (`Raspberry/app/gesture_engine.py`)**:
    - **Step 1 (a2 lifted)**: Lift White $a2$ pawn from starting setup. Visual feedback on $a2$/$a1$ indicates current board mode: **Dark Blue (`Color(0, 70, 220)`)** if currently in Night Mode, or **Warm Sun Amber (`Color(255, 160, 0)`)** if currently in Day Mode.
    - **Step 2 (a1 lifted)**: Lift White $a1$ rook while $a2$ is lifted. $a1$ and $a2$ rapidly pulse in the target mode's theme color.
    - **Step 3 (Replacement & Confirmation)**: Replace both pieces to starting squares to toggle Night Mode on/off, auto-persist to `board_settings.json`, and trigger a 600ms arrival confirmation flash.
  - **Web UI & REST Integration (`Raspberry/frontend/src/App.tsx`, `api.ts`, `main.py`)**: Added Night Mode toggle buttons in the Top Header navigation bar and in the Debug tab under Calibration & Hardware Utilities. Real-time bi-directional sync between physical board gestures and web UI.
  - **Verification**: All 211 test suites passed and frontend built cleanly on Raspberry Pi.
- [x] Fixed Settings Defaults Persistence & Initial Streaming Latency:
  - **Bulletproof Settings Persistence (`Raspberry/frontend/src/App.tsx`, `api.ts`)**: Refactored `persistSettings` and API handlers from error-prone 15-argument positional calls to a unified options object with full state merging. Eliminated the critical bug where slider adjustments or UI toggles inadvertently reset unpassed parameters to default values and corrupted `localStorage` / `board_settings.json`.
  - **Normalized Microsecond/Millisecond Timing (`Raspberry/board_hardware.py`, `app/main.py`, `frontend/src/api.ts`)**: Synchronized `mux_settle_us` and `mux_settle_ms` across frontend and backend, preventing timing values from being ignored or reverted.
  - **Fast Serial Stream Synchronization (`Raspberry/board_hardware.py`, `app/board_state.py`)**: Enhanced `_read_adc_packet` with a fast-path 2-byte read and a sub-millisecond stream scanner fallback that instantly discards coprocessor boot text or stray noise bytes. Lowered serial timeout to 50ms, eliminating multi-second board recognition delays.
  - **Instant 0ms WebSocket State Broadcast (`Raspberry/app/board_state.py`, `app/main.py`, `frontend/src/hooks/useBoardState.ts`)**: Added `get_full_state()` snapshot delivery immediately upon WebSocket `/ws/state` connection establishment. Reduced reconnect backoff to 1.0s, ensuring instantaneous streaming upon page load or server restart.
- [x] Implemented Post-Game Analysis ("The Grandmaster's Lens"), Blunder Blitz Drill, Master Game Time Machine & Dynamic Gesture Starter Pawns:
  - **Dynamic Gesture Starter Pawns & Board Ready Indicator Upgrade (`Raspberry/app/gesture_engine.py`, `board_state.py`)**:
    - Upgraded Layer 1 in `_update_leds()`: Replaced legacy 6 anchor squares with dynamic breathing glow on all registered gesture starter pawns ($a2$ Night Mode [Azure], $e2$ Post-Game Analysis [Royal Violet], $h2$ Instant Restart [Amber]).
    - Automatically discovers and updates starter squares as new physical gestures are registered in `PhysicalGestureEngine`.
  - **Center Royal Gate Physical Gesture (`Raspberry/app/gesture_engine.py`)**:
    - Intuitive 3-step physical gesture from starting setup: Lift $e2$ (White King's pawn) $\to$ Lift $d2$ (White Queen's pawn) while $e2$ is lifted $\to$ Replace both back to starting squares.
    - Activates Post-Game Analysis mode with Royal Violet and Mint Emerald feedback.
  - **Post-Game Analysis & Interactive Branch Exploration ("The Grandmaster's Lens", `Raspberry/app/board_state.py`, `coach_engine.py`)**:
    - Asynchronous batch evaluation with Stockfish / heuristic fallback computing accuracy percentages, per-ply evaluations, centipawn losses, and move quality tiers (Best, Good, Inaccuracy, Blunder).
    - LED Visual Language: Origin illuminates in Amber, destination illuminates in move quality grade (Mint Emerald $\le 20$ cp, Cyan Azure $\le 60$ cp, Warm Amber $\le 150$ cp, Rose Red $> 150$ cp), suggested best alternative pulses with a Mint Emerald halo.
  - **Automatic Ply Progression & Physical Analysis Move Execution (`Raspberry/app/board_state.py`, `app/main.py`)**:
    - Physical board piece manipulations and web app move inputs during `ANALYSIS` mode are routed through `handle_analysis_move()`.
    - Playing the highlighted game move immediately auto-advances to the next ply, triggers the arrival confirmation flash, updates the active board FEN, and syncs the 2D digital board without needing to press the "Next Ply" button in the webapp.
    - Playing an alternative legal move dynamically spawns or extends a virtual exploration branch and evaluates it in real-time.
  - **Concept A: Blunder Blitz Drill (Mistake Rehabilitation Mode, `Raspberry/app/coach_engine.py`, `board_state.py`, `frontend/src/components/AnalysisTab.tsx`)**:
    - Auto-extracts critical mistakes and blunders from the analyzed game.
    - Prompts user to find the grandmaster refutation with physical piece moves or web input, with attempt tracking (❤️❤️❤️) and physical board LED hint assistance.
  - **Concept B: Master Game Time Machine (Guess-the-Move Classics, `Raspberry/app/gm_games.py`, `board_state.py`, `frontend/src/components/AnalysisTab.tsx`)**:
    - Curated database of 6 historical masterpieces (*Kasparov's Immortal 1999*, *Tal's Hurricane Attack 1960*, *Fischer's Game of the Century 1956*, *Morphy's Opera Game 1858*, *The Immortal Game 1851*, *Carlsen's Python Squeeze 2013*).
    - Guess-the-move scoring system, move step navigation, and historical commentary annotations.
  - **Direct `board_settings.json` Persistence & Template Simplification (`Raspberry/board_hardware.py`, `app/main.py`, `frontend/src/App.tsx`)**:
    - Completely removed obsolete `board_settings.default.json` fallback layer; `load_settings()` and `save_defaults()` now directly read and write `board_settings.json`.
    - Enhanced "Save Current Stats as Defaults" with vivid emerald confirmation feedback including exact save timestamp and baseline/threshold summary.

## Task Backlog
- [ ] Promotion selection: physical underpromotion is silently auto-queened (`physical_tracker.py` hard-codes `"q"`). Consider a `promotion_mode` setting with a pending-selection LED prompt (pattern exists in `pending_castling_rook`).
- [ ] En-passant captured-pawn cleanup: no transient guardrail exemption/LED prompt for the vanishing enemy pawn square (unlike castling rook handling), causing a false `unexpected_piece` alert until the user removes the pawn.
- [ ] Split `App.tsx` (~2400 lines, ~45 `useState`) into PlayTab / DebugTab / ChessBoard / SensorOverlay / MatchmakingPanel components with memoized cell boundaries.
- [ ] Wire gamma LUT (`GAMMA_LUT_28`, already tested) into `DualPixelStrip.show()` intensity scaling if perceptual dimming is desired — visual/power behavior change, needs on-board validation.
- [ ] Persist `/tmp/opencode/scb_venv`-equivalent dev requirements for x86 offline testing (optional; Pi venv unaffected).

## Active Blockers





