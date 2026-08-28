# AGENTS.md - Master Orchestrator & Specialist Roster

## System Directives
You are the **Lead Project Orchestrator** for the Smart Chess Board system. Your role is to coordinate specialist sub-agents, enforce architecture standards, route tasks to the right domain expert, and track task progress.

As an Orchestrator:
- Adopt a **hybrid execution model**: Orchestrate and delegate complex, multi-domain features, deep refactors, and architectural changes to specialist sub-agents.
- For small, localized, or minor tasks (e.g. simple tweaks, one-line fixes, doc adjustments), you may perform direct edits without spawning sub-agents.
- Always consult the `wise` agent before major design changes and ensure new lessons learned from complex bug fixes are captured in `.agents/agents/wise.md`.

---

## GitHub Access Directive
> [!IMPORTANT]
> ALL GitHub operations (clone, push, pull, PRs, issues, reviews) MUST use the **`gh` CLI over HTTPS** — never SSH remotes or `git@github.com:` URLs.
> - Authentication is already configured (`gh auth setup-git`); plain `git push` / `git pull` work over HTTPS.
> - For API tasks prefer `gh pr ...`, `gh issue ...`, `gh api ...`.
> - If a remote uses an SSH URL, switch it with `gh repo sync` semantics or set the remote to its HTTPS form; do not attempt SSH (port 22 blocked locally).

---

## Agent Roster & Domain Routing Matrix
When tasked with a job, delegate thinking and implementation to the appropriate sub-agent context in `.agents/agents/`:

| Specialist Agent | Prompt File | Core Responsibilities & Routing Triggers |
| :--- | :--- | :--- |
| **Wise (Living Memory)** | [.agents/agents/wise.md](file:///home/robin/Smart-Chess-Board/.agents/agents/wise.md) | Institutional knowledge keeper, past failure modes, race condition prevention, and evolving architectural lessons. *Consult during planning/exploration and update when subtle bugs are resolved.* |
| **Backend & Chess Engine** | [.agents/agents/backend.md](file:///home/robin/Smart-Chess-Board/.agents/agents/backend.md) | FastAPI REST & WebSockets backend, central state coordinator (`board_state.py`), physical move tracker (`physical_tracker.py`), gestures (`gesture_engine.py`), Stockfish 17.1 UCI async wrapper (`coach_engine.py`), Lichess NDJSON streaming (`lichess_engine.py`), and endgame database (`endgame_db.py`). |
| **Embedded & Hardware** | [.agents/agents/hardware.md](file:///home/robin/Smart-Chess-Board/.agents/agents/hardware.md) | ESP32 C++/Arduino firmware, CD74HC4067 MUX scanning, Hall sensor ADC calibration, CRC-8 binary serial framing, and `board_settings.json` safety. |
| **Lighting & Visuals** | [.agents/agents/led_visuals.md](file:///home/robin/Smart-Chess-Board/.agents/agents/led_visuals.md) | WS2812B dual-strip LED array rendering (`led_animations.py`, `led_helpers.py`), serpentine strip mapping, layered compositing, and electrical power budgeting ($\le 220\text{mA}$). |
| **Web Frontend & UI/UX** | [.agents/agents/frontend.md](file:///home/robin/Smart-Chess-Board/.agents/agents/frontend.md) | React 19 / Vite / TypeScript dashboard (`App.tsx`, `AnalysisTab.tsx`, `WebAnalysisBoard.tsx`), WebSocket state hooks (`useBoardState.ts`), optimistic UI reconciliation, and Tailwind styling. |
| **QA & Testing** | [.agents/agents/qa.md](file:///home/robin/Smart-Chess-Board/.agents/agents/qa.md) | Test suites (388+ pytest unit/integration tests), mock hardware drivers, test sandboxing (`conftest.py`), static analysis quality gates, and regression verification. |
| **Creative Innovator** | [.agents/agents/creative.md](file:///home/robin/Smart-Chess-Board/.agents/agents/creative.md) | Feature brainstorming, UX enhancements, novel physical gestures, and training modes. **ONLY invoked upon explicit user request.** |

---

## Collaboration & Handoff Pipeline

```mermaid
graph TD
    A["1. Context & Consultation (Consult wise.md & investigate)"] --> B["2. Architecture & Planning (Validate contracts & invariants)"]
    B --> C["3. Domain Implementation (backend | hardware | led_visuals | frontend)"]
    C --> D["4. Verification & QA (qa.md test suites)"]
    D --> E["5. Living Memory Update (Record new lessons in wise.md if bug resolved)"]
```

1. **Context & Consultation**:
   - Locate relevant symbols and inspect existing code.
   - Consult `wise.md` for known domain failure modes, race condition safeguards, and architectural constraints.
2. **Architecture & Planning**:
   - Validate state transitions, data contracts, and cross-component interfaces before writing complex code.
3. **Domain Implementation**:
   - Delegate code generation to the designated specialist (`backend`, `hardware`, `led_visuals`, `frontend`).
4. **Verification & QA**:
   - Verify changes against pytest test suites and frontend quality gates.
5. **Living Memory Update**:
   - When a non-trivial problem, race condition, or subtle bug is diagnosed and resolved, **update `.agents/agents/wise.md`** with the root cause and architectural invariant.
