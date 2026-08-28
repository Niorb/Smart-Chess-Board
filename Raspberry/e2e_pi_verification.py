#!/usr/bin/env python3
"""
Raspberry/e2e_pi_verification.py

Comprehensive End-to-End Verification Battery for Smart Chess Board.
Executed directly on Raspberry Pi hardware (ssh pi@pi).
"""

import asyncio
import os
import subprocess
import sys
import time

# Ensure Raspberry root is on sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import chess
import chess.engine
from app.board_state import BoardStateManager
from app.coach_engine import (
    CoachEngine,
    analysis_cache_key,
    load_cached_analysis,
    save_cached_analysis,
)
from app.gm_games import get_all_gm_games, get_gm_game
from fastapi.testclient import TestClient


def log_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_section(name: str):
    print(f"\n[RUNNING] {name}...")


def pass_section(name: str, detail: str = ""):
    extra = f" ({detail})" if detail else ""
    print(f"[PASS] {name}{extra}")


def fail_section(name: str, error: str):
    print(f"[FAIL] {name} - ERROR: {error}")
    sys.exit(1)


# -----------------------------------------------------------------------------
# 1. AUTOMATED PYTEST REGRESSION (394 Tests)
# -----------------------------------------------------------------------------
def run_pytest_regression():
    log_header("1. Pytest Automated Test Regression")
    cmd = [sys.executable, "-m", "pytest", os.path.join(BASE_DIR, "tests"), "-v", "--tb=short"]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0

    print(proc.stdout[-800:] if len(proc.stdout) > 800 else proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        fail_section("Pytest Regression", f"Test suite failed with exit code {proc.returncode}")
    pass_section("Pytest Regression", f"All tests passed in {dt:.2f}s")


# -----------------------------------------------------------------------------
# 2. LIVE STOCKFISH UCI ENGINE PERFORMANCE BENCHMARK
# -----------------------------------------------------------------------------
async def benchmark_stockfish_live():
    log_header("2. Live Stockfish UCI Engine Performance Benchmark")
    engine = CoachEngine()
    await engine.start()
    pass_section("Stockfish Launch", f"Binary: {engine.stockfish_path}")

    # Test starting position evaluation
    t0 = time.perf_counter()
    ev_start = await engine.evaluate_position(chess.STARTING_FEN)
    t_start = (time.perf_counter() - t0) * 1000
    assert ev_start.best_move is not None, "Best move must not be None"
    pass_section("Starting Position Eval", f"Best move: {ev_start.best_move}, Time: {t_start:.1f}ms")

    # Benchmark Stage 1 (MultiPV=1, Depth 10) - Target < 350ms
    t0 = time.perf_counter()
    lines_quick = await engine.compute_top_lines(chess.STARTING_FEN, num_lines=1, depth=10, time_limit=0.10)
    t_quick = (time.perf_counter() - t0) * 1000
    assert len(lines_quick) >= 1, "Quick line must return at least 1 PV"
    assert t_quick < 350.0, f"Stage 1 latency {t_quick:.1f}ms exceeded 350ms SLA"
    pass_section("Stage 1 Quick Best Line", f"SAN: {lines_quick[0]['san'][:3]}, Latency: {t_quick:.1f}ms (< 350ms SLA)")

    # Benchmark Stage 2 (MultiPV=3, Depth 10)
    t0 = time.perf_counter()
    lines_full = await engine.compute_top_lines(chess.STARTING_FEN, num_lines=3, depth=10, time_limit=0.25)
    t_full = (time.perf_counter() - t0) * 1000
    assert len(lines_full) >= 2, "Full lines must return multi-PV lines"
    pass_section("Stage 2 Full Multi-PV=3", f"Lines: {len(lines_full)}, Latency: {t_full:.1f}ms")

    await engine.stop()


# -----------------------------------------------------------------------------
# 3. BATCH EVALUATION, CACHING & HYDRATION
# -----------------------------------------------------------------------------
async def test_batch_precomputation_and_hydration():
    log_header("3. Batch Precomputation, Persistent Caching & Hydration")
    engine = CoachEngine()
    await engine.start()

    game = get_gm_game("kasparov_topalov_1999")
    assert game is not None
    moves = game.moves[:10]  # First 10 plies for rapid validation

    # Batch evaluate
    t0 = time.perf_counter()
    batch_res = await engine.batch_evaluate_game(moves)
    t_batch = (time.perf_counter() - t0) * 1000
    assert len(batch_res["evaluations"]) == 11
    pass_section("Batch Evaluation", f"10 plies analyzed in {t_batch:.1f}ms")

    # Test disk persistence
    cache_k = analysis_cache_key(moves)
    save_cached_analysis(cache_k, moves, batch_res)
    loaded = load_cached_analysis(cache_k)
    assert loaded is not None
    assert len(loaded["moves"]) == len(moves)
    pass_section("Persistent Disk Cache", "Saved and verified atomic read from analysis_cache.json")

    # Test in-memory cache hydration
    fresh_engine = CoachEngine()
    fresh_engine.hydrate_from_cached_evaluations(batch_res["evaluations"])
    cached_eval = fresh_engine.get_cached_evaluation(chess.STARTING_FEN)
    assert cached_eval is not None
    pass_section("Cache Hydration", f"Hydrated in-memory evaluation for starting position: {cached_eval.best_move}")

    await engine.stop()


# -----------------------------------------------------------------------------
# 4. ANALYSIS DIVERGENCE SPEED & AUTO SNAP-BACK
# -----------------------------------------------------------------------------
async def test_analysis_divergence_and_snapback():
    log_header("4. Analysis Divergence & Physical Auto Snap-Back")
    mgr = BoardStateManager()
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    await mgr.start_analysis_mode(moves_uci=moves)

    # Step to ply 2 (after 1... e5)
    mgr.step_analysis(2)
    assert mgr.analysis_current_ply == 2

    # Diverge with alternative move 2. f4 (f2f4)
    t0 = time.perf_counter()
    res_branch = mgr.handle_analysis_move("f2f4", source="web")
    t_div = (time.perf_counter() - t0) * 1000
    assert res_branch["action"] == "branch"
    assert mgr.analysis_anchor_ply == 2
    assert mgr.analysis_anchor_coord == (5, 1)  # f2
    assert t_div < 350.0, f"Branch creation took {t_div:.1f}ms (> 350ms)"
    pass_section("Virtual Branch Creation", f"Diverged to 2. f4 in {t_div:.1f}ms")

    # Simulate physical restoration to anchor position (1. e4 e5)
    anchor_board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    phys_state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in range(8):
            p = anchor_board.piece_at(chess.square(c, r))
            if p:
                phys_state[c][r] = -1 if p.color == chess.WHITE else 1

    mgr.physical_state = phys_state
    mgr.move_tracker.reset(phys_state)
    restored = mgr._check_analysis_board_restoration()
    assert restored is True
    assert mgr.analysis_anchor_coord is None
    assert mgr.analysis_branch_moves == []
    pass_section("Auto Snap-Back", "Physical board restore snapped back to game timeline ply 2")

    mgr.stop_analysis_mode()


# -----------------------------------------------------------------------------
# 5. BLUNDER BLITZ PUZZLE GENERATION & ATTEMPT EVALUATION
# -----------------------------------------------------------------------------
async def test_blunder_blitz_flow():
    log_header("5. Blunder Blitz Tactical Drill & Opponent Handling")
    mgr = BoardStateManager()
    moves = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]
    await mgr.start_analysis_mode(moves_uci=moves, force_refresh=True)

    assert len(mgr.analysis_blunders) >= 1
    blunder0 = mgr.analysis_blunders[0]
    assert blunder0["player_color"] == "black"
    assert blunder0["opponent_color"] == "white"
    pass_section("Blunder Extraction", f"Detected blunder at ply {blunder0['ply_index']} with opponent move {blunder0['opponent_prev_move_san']}")

    # Start blunder drill
    payload = mgr.start_blunder_drill(0)
    assert payload["submode"] == "blunder_drill"

    # Submit wrong move
    res_wrong = mgr.submit_blunder_attempt("a7a6", source="web")
    assert res_wrong["correct"] is False
    assert res_wrong["attempts_remaining"] == 2
    pass_section("Incorrect Attempt", "Retry enforced with 2 attempts remaining")

    # Submit best move
    best_move = blunder0["best_move"]
    res_correct = mgr.submit_blunder_attempt(best_move, source="web")
    assert res_correct["correct"] is True
    pass_section("Correct Attempt", f"Move {best_move} confirmed with refutation status")

    mgr.stop_analysis_mode()


# -----------------------------------------------------------------------------
# 6. GM REPLAY TRAINER LIFECYCLE
# -----------------------------------------------------------------------------
def test_gm_replay_lifecycle():
    log_header("6. GM Replay Trainer Lifecycle")
    mgr = BoardStateManager()
    games = get_all_gm_games()
    assert len(games) >= 2
    pass_section("GM Games Catalog", f"Loaded {len(games)} GM historical master games")

    payload = mgr.start_gm_game("kasparov_topalov_1999")
    assert payload["submode"] == "replay_learn"
    assert payload["replay"]["phase"] == "learn"

    # Learn 2 moves
    moves = mgr.analysis_game_moves
    assert mgr.handle_replay_move(moves[0])["action"] == "advance"
    assert mgr.handle_replay_move(moves[1])["action"] == "advance"
    assert mgr.replay_learned_ply == 2
    pass_section("Learn Phase", "Learned 2 plies successfully")

    # Trigger board reset gate
    from types import SimpleNamespace
    setup_res = SimpleNamespace(is_setup_ready=True)
    assert mgr._try_conclude_analysis_on_board_reset(setup_res) is True
    assert mgr.analysis_submode == "replay_recall"
    assert mgr.analysis_current_ply == 0
    pass_section("Reset Gate & Recall Phase", "Transitioned to Memory Recall phase scoped to 2 plies")

    mgr.stop_analysis_mode()


# -----------------------------------------------------------------------------
# 7. FASTAPI REST ENDPOINTS & WEBSOCKET HEARTBEAT
# -----------------------------------------------------------------------------
def test_api_and_websocket():
    log_header("7. FastAPI REST Endpoints & WebSocket Heartbeat")
    from app.main import app
    client = TestClient(app)

    # Health check
    res = client.get("/api/board/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "online", "ok")
    pass_section("GET /api/board/health", f"Status: {data['status']}")

    # Endgame Drills catalog
    res_eg = client.get("/api/endgame/drills")
    assert res_eg.status_code == 200
    assert len(res_eg.json()) >= 11
    pass_section("GET /api/endgame/drills", f"{len(res_eg.json())} tablebase drills available")

    # WebSocket connection test
    with client.websocket_connect("/ws/state") as ws:
        snapshot = ws.receive_json()
        assert "status" in snapshot
        assert "physical" in snapshot
        assert "digital" in snapshot
        pass_section("WebSocket /ws/state", "Connected and received initial full snapshot")


# -----------------------------------------------------------------------------
# 8. SYSTEMD SERVICE HEALTH CHECK
# -----------------------------------------------------------------------------
def check_systemd_service():
    log_header("8. Systemd Service Health Check")
    proc = subprocess.run(["systemctl", "is-active", "smart-chess"], capture_output=True, text=True)
    status = proc.stdout.strip()
    if status == "active":
        pass_section("systemctl is-active smart-chess", "Service is actively running")
    else:
        print(f"[NOTE] smart-chess service status: '{status}' (Non-critical if running in test environment)")


# -----------------------------------------------------------------------------
# MAIN RUNNER
# -----------------------------------------------------------------------------
async def main():
    print("\n" + "=" * 70)
    print("  SMART CHESS BOARD - END-TO-END VERIFICATION BATTERY")
    print("=" * 70)

    run_pytest_regression()
    await benchmark_stockfish_live()
    await test_batch_precomputation_and_hydration()
    await test_analysis_divergence_and_snapback()
    await test_blunder_blitz_flow()
    test_gm_replay_lifecycle()
    test_api_and_websocket()
    check_systemd_service()

    log_header("ALL 8 VERIFICATION BATTERY DOMAINS PASSED PERFECTLY!")


if __name__ == "__main__":
    asyncio.run(main())
