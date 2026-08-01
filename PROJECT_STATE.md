# PROJECT_STATE.md

## Current Sprint Goal
Maintain AI Sub-Agent Roster and Implement Smart Chess Board Core Features.

## Active Agents Roster
- **Architect** (`.agents/arch.md`) - System design, protocols, state machines.
- **Developer** (`.agents/dev.md`) - FastAPI backend, React/Vite frontend, stockfish engine integration.
- **QA Specialist** (`.agents/qa.md`) - Unit tests, mock hardware drivers, edge cases.
- **Hardware Specialist** (`.agents/hardware.md`) - ESP32 firmware, GPIO, matrix inversion, LED strip driver.
- **Automation Specialist** (`.agents/automation.md`) - Playwright browser scripts, Chess.com online sync.
- **Creative Innovator** (`.agents/creative.md`) - Feature brainstorming & ideas (Invoked ONLY on explicit user request).
- **Code Explorer** (`.agents/explorer.md`) - Search, index, trace, and locate codebase information and symbol definitions.

## Completed Tasks
- [x] Analyzed existing project architecture across hardware, backend, frontend, and browser automation.
- [x] Defined 6 specialized AI agent personas in `.agents/`.
- [x] Updated `agent.md` with domain routing rules, handoff protocols, and Raspberry Pi SSH directives (`ssh pi`, `source ~/venv/chess/bin/activate`).
- [x] Implemented core unit test suite in `Raspberry/tests/`.
- [x] Implemented and verified `GET /api/board/health` diagnostic endpoint and unit test suite.
- [x] Created and registered the **Creative Innovator** sub-agent (`.agents/creative.md`).
- [x] Fixed LED Strip 2 serpentine index mapping (h8 -> h1 -> g1 -> g8 -> f8 -> f1 -> e1 -> e8) and added test suite `tests/test_led_helpers.py`.
- [x] Created and registered the **Code Explorer** sub-agent (`.agents/explorer.md`).
- [x] Implemented independent left (`a-d`) and right (`e-h`) row quadrant swap settings (`swap_row_quadrants_left` / `swap_row_quadrants_right`) across hardware driver, FastAPI backend, and React debug UI.

## Task Backlog
- [ ] Refine ESP32 matrix debouncing and serial packet framing (`.agents/hardware.md`).
- [ ] Enhance Playwright Chess.com session resilience and DOM event listening (`.agents/automation.md`).
- [ ] Integrate React frontend WebSocket state visualization with hardware debug controls (`.agents/dev.md`).

## Active Blockers
- None
