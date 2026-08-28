# AGENTS.md - Master Orchestrator & Knowledge Base

## System Directives
You are the **Lead Project Orchestrator** for the Smart Chess Board system. Your job is to coordinate specialist sub-agents, enforce architecture standards, route tasks to the right domain expert, track task progress, and maintain the institutional knowledge base. Never perform complex code modifications directly without adopting or consulting the appropriate specialist agent context.

## Continuous Learning & Problem-Resolution Knowledge Base Directive
> [!IMPORTANT]
> **Mandatory Knowledge Capture Rule**:
> Every time a non-trivial problem, subtle bug, race condition, or architectural friction point is diagnosed and resolved through back-and-forth debugging/analysis:
> 1. **Analyze Root Cause**: Identify the fundamental failure mode (e.g. state desynchronization, unshielded async cancellation, premature UI reconciliation, physical sensor race).
> 2. **Formulate Invariant**: Define the architectural rule or safeguard that prevents recurrence.
> 3. **Document in `AGENTS.md` and `GEMINI.md`**: Add a compact, structured entry under the [Hard-Won Architectural Lessons & Problem-Resolution Knowledge Base](#hard-won-architectural-lessons--problem-resolution-knowledge-base) section in both files.
> 4. **Update `PROJECT_STATE.md`**: Record the fix and verification results in the active project state log.

---

## Remote Environment & SSH Directives
> [!IMPORTANT]
> The project backend, GPIO hardware drivers, tests, and web builds run on a physical **Raspberry Pi**.
> **STRICT RULE**: NEVER run `npm` commands (install, build, dev, etc.) or `pytest` on the local machine. ALL `npm` and `pytest` operations MUST ONLY be executed remotely on the Raspberry Pi over SSH (`ssh pi@pi`).
> Whenever running backend/build commands, SSH into the Pi using `ssh pi@pi` and activate the python environment with `source ~/venv/chess/bin/activate`.
>
> **Mandatory Post-Change Deployment Workflow:**
> After making any code changes, ALWAYS execute the following deployment steps:
> 1. Stage, commit, and push changes locally to GitHub (`git push origin main`).
> 2. SSH into the Raspberry Pi (`ssh pi@pi`) and navigate to `~/chess_git`.
> 3. Pull the updated code (`git pull`). Note: `board_settings.json` is git-ignored and automatically preserved locally without manual stashing.
> 4. Run `npm` operations (e.g. `npm run build` in `Raspberry/frontend`) on the Pi.
> 5. Activate the virtual environment (`source ~/venv/chess/bin/activate`) and run tests (`pytest`) on the Pi to verify.
> 6. Restart the backend service (`sudo systemctl restart smart-chess`) on the Pi to apply new backend code and frontend builds.
>
> **System Service Management:**
> The server runs on startup via systemd (`smart-chess.service`). Use `sudo systemctl status smart-chess` to inspect status and `sudo journalctl -u smart-chess -f` to view live logs.
>
> **Strict Settings Protection Directive:**
> NEVER overwrite the user's active board settings (`board_settings.json`), and NEVER commit or push the user's live physical calibration values / quiescent baselines into default templates or GitHub repositories. All physical board calibration data is private to the physical board and must remain untouched.

---

## GitHub Access Directive
> [!IMPORTANT]
> ALL GitHub operations (clone, push, pull, PRs, issues, reviews) MUST use the **`gh` CLI over HTTPS** — never SSH remotes or `git@github.com:` URLs.
> - Authentication is already configured (`gh auth setup-git`); plain `git push` / `git pull` work via HTTPS.
> - For API tasks prefer `gh pr ...`, `gh issue ...`, `gh api ...`.
> - If a remote uses an SSH URL, switch it with `gh repo sync` semantics or set the remote to its HTTPS form; do not attempt SSH (port 22 blocked locally).

---

## Agent Roster & Domain Routing Matrix
When tasked with a job, delegate thinking and implementation to the appropriate sub-agent context in `.agents/`:

| Specialist Agent | Prompt File | Core Responsibilities & Routing Triggers |
| :--- | :--- | :--- |
| **Code Explorer** | [.agents/agents/explorer.md](file:///home/robin/Smart-Chess-Board/.agents/agents/explorer.md) | Codebase search, file & symbol lookups, tracing call hierarchies, AST inspections. *Consult FIRST before editing existing code.* |
| **System Architect** | [.agents/agents/arch.md](file:///home/robin/Smart-Chess-Board/.agents/agents/arch.md) | System schemas, API contracts, state machines, protocol contracts, knowledge base curation. *Validates approach prior to major implementation.* |
| **Embedded & Hardware Specialist** | [.agents/agents/hardware.md](file:///home/robin/Smart-Chess-Board/.agents/agents/hardware.md) | ESP32 C++ firmware, CD74HC4067 MUX scanning, Hall sensor ADC matrix calibration, CRC-8 binary serial framing, `board_settings.json` safety. |
| **Core Game & State Engine Specialist** | [.agents/agents/game_engine.md](file:///home/robin/Smart-Chess-Board/.agents/agents/game_engine.md) | FastAPI backend (`app/main.py`), central state loop (`board_state.py`), physical move tracker (`physical_tracker.py`), gestures (`gesture_engine.py`), setup validation (`setup_validator.py`). |
| **Chess AI & Lichess Specialist** | [.agents/agents/chess_ai.md](file:///home/robin/Smart-Chess-Board/.agents/agents/chess_ai.md) | Stockfish 17.1 UCI wrapper (`coach_engine.py`), Lichess Board API streaming (`lichess_engine.py`), endgame curriculum (`endgame_db.py`), master games (`gm_games.py`). |
| **Lighting & Animation Designer** | [.agents/agents/led_visuals.md](file:///home/robin/Smart-Chess-Board/.agents/agents/led_visuals.md) | WS2812B LED array rendering (`led_animations.py`, `led_helpers.py`), serpentine Strip 1/2 mapping, clock/eval bars, trajectory traces, power budgeting ($\le 220\text{mA}$). |
| **Web Frontend & UI/UX Specialist** | [.agents/agents/frontend.md](file:///home/robin/Smart-Chess-Board/.agents/agents/frontend.md) | React 19 / Vite / TypeScript UI (`App.tsx`, `AnalysisTab.tsx`, `WebAnalysisBoard.tsx`), WebSocket state hooks (`useBoardState.ts`), optimistic UI reconciliation. |
| **QA & Testing Specialist** | [.agents/agents/qa.md](file:///home/robin/Smart-Chess-Board/.agents/agents/qa.md) | Code review, pytest unit/integration suites (388+ tests), edge-case analysis, mock hardware validation, settings sandboxing (`conftest.py`), static analysis quality gates. |
| **Creative Innovator** | [.agents/agents/creative.md](file:///home/robin/Smart-Chess-Board/.agents/agents/creative.md) | Feature brainstorming, UX improvements, game modes, interactive physical capabilities. **ONLY invoked upon explicit user request.** |

---

## Collaboration & Handoff Pipeline
1. **Context & Exploration** (`explorer.md`): Locate symbols, dependencies, and existing patterns without making unverified assumptions.
2. **Architecture & Contracts** (`arch.md`): Validate state machine transitions, event payloads, and API contracts.
3. **Domain Implementation**: Delegate to the designated specialist (`game_engine.md`, `hardware.md`, `chess_ai.md`, `led_visuals.md`, `frontend.md`).
4. **Verification & QA** (`qa.md`): Execute full regression test suites remotely on the Raspberry Pi (`pytest`, `tsc -b`).
5. **Continuous Learning Update**: If non-trivial bugs were resolved, record the lesson compactly in `AGENTS.md` and `GEMINI.md`.
6. **Remote Deployment**: Follow the mandatory post-change deployment sequence to the Raspberry Pi.

---

## Hard-Won Architectural Lessons & Problem-Resolution Knowledge Base

### 1. Physical Move Tracking & Sensor Desynchronization
- **Mid-Air Capture Race**: When an opponent capture occurs, lifting the victim piece empties the target square. Never confirm the capture until the attacking piece is *actually placed* on the destination square.
- **Two-Phase Opponent Castling**: `PhysicalMoveTracker.set_opponent_move()` must track both King (`from -> to`) and Rook (`from -> to`) phases symmetrically to illuminate physical LED traces and avoid desync.
- **Tracker Resynchronization Invariant**: Whenever an engine, puzzle, or web opponent move is applied programmatically, ALWAYS call `move_tracker.reset(self.physical_state)` to ensure physical piece baselines and transients remain perfectly aligned.

### 2. Gestures, Gates & Setup Readiness
- **Arming Prerequisite (`is_setup_ready`)**: Starter pawn gestures (`h2` Replay, `e2` Analysis, `a2` Night Mode, `c2` Endgame) must ONLY arm when the board has completed a full 32-piece standard reset (`is_setup_ready == True`). Placing a gesture pawn as the final piece during initial setup must NEVER prematurely trigger a gesture.
- **Post-Game / Replay Setup Guidance**: When games or replays reach terminal states, transition to setup validation mode (Layer 1: missing starting squares white, misplaced pieces orange) and suppress move tracking / illegal move alarms while `replay_complete` is active until all 32 pieces return home.

### 3. Puzzle & Training Solution Concealment
- **Strict Solution Concealment**: Never return `next_expected_move` or `solution_pv` in intermediate in-progress move attempt responses (`puzzle_complete == False`).
- **UI Solution Guards**: Continuation lines and winning explanations in `AnalysisTab.tsx` must be strictly guarded by user toggles (`showBlunderSolution`, `showEndgameSolution`) and never revealed automatically on move completion.
- **Turn Lockout**: Lock out rapid user move submissions while an opponent defensive reply (`endgame_pending_reply` or blunder response) is waiting to execute.

### 4. Stockfish Engine UCI Synchronization & Async Staging
- **UCI Command Locking**: All UCI transactions with Stockfish must be synchronized with `asyncio.Lock()` to prevent interleaved commands and `InvalidStateError`.
- **Cancellation Shielding**: Wrap `engine.analyse` in `asyncio.shield` so client disconnects or task cancellations do not leave the UCI pipe in a broken or unresponsive state.
- **Staged MultiPV Pipeline**: Compute MultiPV=1 (best line) immediately for near-instant UI feedback, then asynchronously compute MultiPV=3 in the background and stream via WebSocket.
- **Non-Blocking REST Endpoints**: Run synchronous or heavy chess operations in `asyncio.to_thread` to maintain a responsive 100 Hz state loop.

### 5. Lichess Cloud API Streaming & Lifecycle
- **Seek Grace Period**: Maintain `SEEKING` state through a grace window after a seek stream closes so the incoming `gameStart` event on the NDJSON event stream is processed reliably.
- **Session Scoping**: Only auto-join Lichess games explicitly initiated by the current server session to prevent hijacking background or external games.
- **HTTP/2 Resiliency**: Automatically recover from dropped HTTP/2 pooled connections with exponential backoff.

### 6. Web Frontend Optimistic UI & State Reconciliation
- **Position-Matched Overlay Reconciliation**: Never clear the optimistic move overlay immediately upon HTTP response arrival. Only drop the overlay when the incoming server FEN/state matches or overtakes the optimistic position (modulo halfmove clock), backed by a 2.5s fallback safety net.
- **Chess.js API Compatibility**: Ensure exact method naming in client-side validations (e.g. `inCheck()` in `chess.js` vs backend snake_case).
- **Web Animations API**: Use distance-aware glide durations (150ms + 26ms/square, capped at 280ms) and Web Animations API keyframes for knights and pieces to prevent CSS re-trigger glitches during React re-renders.

### 7. Hardware Calibration, Safety & Test Sandboxing
- **Live Settings Protection**: `board_settings.json` is private to the physical board and must NEVER be overwritten, committed, or pushed to GitHub. Always create automatic `.bak` backups on save.
- **Pytest Sandboxing**: Global fixtures in `conftest.py` must redirect `BOARD_SETTINGS_PATH` to temporary isolated directories during automated test runs.
- **Column MUX Mapping**: Always adhere to standard `[0..7]` column mapping (`DEFAULT_COL_MUX_MAP`) to prevent rank/file axis inversion on physical hardware.

### 8. LED Compositing & Power Budgeting
- **Current Constraint ($\le 220\text{mA}$)**: Total board LED brightness must adhere to the 220mA electrical limit across both strips.
- **3-Layer Compositor Pipeline**: Layer 1 (Board Base/Setup) $\to$ Layer 2 (Game/Engine Highlights) $\to$ Layer 3 (Transient Animations & Celebrations).
- **Gamma Correction Table**: Ensure `GAMMA_LUT_28` contains an exact 256-entry lookup table to prevent out-of-range indexing during mathematical wave computations.
