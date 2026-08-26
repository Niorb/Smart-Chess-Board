"""
app/endgame_db.py

Curriculum database and progress persistence manager for the Endgame Tablebase Trainer.
Contains the curated 12-drill core curriculum (Pawn, Rook, Minor Piece, Queen endgames)
and manages user progress, star ratings, mistakes, and custom user drills.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import time
from typing import Any

import chess

logger = logging.getLogger("smart-chess-app.endgame")

ENDGAME_PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "endgame_progress.json",
)


class EndgameCategory(str, Enum):
    PAWN = "pawn"
    ROOK = "rook"
    MINOR = "minor"
    QUEEN = "queen"
    CUSTOM = "custom"


@dataclass
class EndgameDrill:
    id: str
    category: EndgameCategory
    title: str
    fen: str
    player_color: str  # "white" | "black"
    target_goal: str   # "win" | "draw" | "mate"
    difficulty: int    # 1 (Beginner), 2 (Intermediate), 3 (Master)
    description: str
    key_concepts: list[str]
    hint: str
    max_plies: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "title": self.title,
            "fen": self.fen,
            "player_color": self.player_color,
            "target_goal": self.target_goal,
            "difficulty": self.difficulty,
            "description": self.description,
            "key_concepts": self.key_concepts,
            "hint": self.hint,
            "max_plies": self.max_plies,
        }


# =============================================================================
# CURATED 12-DRILL CORE CURRICULUM
# =============================================================================

CORE_CURRICULUM: list[EndgameDrill] = [
    # 1. Pawn Endgames
    EndgameDrill(
        id="pawn_opposition",
        category=EndgameCategory.PAWN,
        title="King & Pawn vs King: Direct Opposition",
        fen="8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=1,
        description="Take the direct opposition with your King and shepherd your passed pawn to promotion without giving up key squares.",
        key_concepts=["Direct Opposition", "Key Squares", "Shouldering"],
        hint="Step your King directly in front of the enemy King or onto key squares before advancing the pawn.",
    ),
    EndgameDrill(
        id="pawn_rook_pawn_draw",
        category=EndgameCategory.PAWN,
        title="Rook Pawn Stalemate Trap (Defend)",
        fen="8/8/8/8/8/7k/7P/7K b - - 0 1",
        player_color="black",
        target_goal="draw",
        difficulty=1,
        description="Defend with Black against White's h-pawn. Lock your King into the corner or maintain stalemate barriers.",
        key_concepts=["Corner Stalemate", "Rook Pawn Inherent Draw", "King Confinement"],
        hint="Keep your King cycling between h8 and g8 (or corner squares) so White cannot deliver checkmate without stalemate.",
    ),
    EndgameDrill(
        id="pawn_square",
        category=EndgameCategory.PAWN,
        title="The Square of the Pawn: Passed Pawn Chase",
        fen="8/8/8/8/P7/8/8/4k1K1 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=1,
        description="Calculate the rule of the square and sprint your passed pawn directly to promotion before Black's King can intercept.",
        key_concepts=["Rule of the Square", "Pawn Race", "Promotion Outpost"],
        hint="Push the a-pawn immediately! Black's King is outside the square of the pawn and cannot catch it.",
    ),

    # 2. Rook Endgames
    EndgameDrill(
        id="rook_lucena",
        category=EndgameCategory.ROOK,
        title="The Lucena Position: Building the Bridge",
        fen="1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=2,
        description="The cornerstone of all Rook endgames. Build a rook bridge on the 4th rank to shield your King from vertical checks and promote.",
        key_concepts=["Building the Bridge", "4th Rank Rook Shield", "King Escape"],
        hint="Activate your Rook to the 4th rank (Rc4), step your King out, and use the Rook on c4 to block Black's checking Rook.",
    ),
    EndgameDrill(
        id="rook_philidor",
        category=EndgameCategory.ROOK,
        title="The Philidor Defense: Third-Rank Cutoff",
        fen="8/4k3/8/4r3/4P3/8/4K3/1R6 b - - 0 1",
        player_color="black",
        target_goal="draw",
        difficulty=2,
        description="The fundamental defensive technique. Hold your Rook on the 6th rank (or 3rd rank from defender's side) until White pushes the pawn, then drop back for perpetual checks.",
        key_concepts=["6th-Rank Cutoff", "Rear Checking Distance", "Passive Defense Transition"],
        hint="Keep your Rook along the 6th rank (e6/a6) preventing White's King from advancing. When White pushes e5, drop your Rook to the 1st rank and deliver endless back checks!",
    ),
    EndgameDrill(
        id="rook_short_side",
        category=EndgameCategory.ROOK,
        title="Short Side Defense: Checking from Distance",
        fen="8/8/8/3k4/8/R7/4K3/4r3 w - - 0 1",
        player_color="white",
        target_goal="draw",
        difficulty=2,
        description="Keep your King on the short side of the pawn while checking the enemy King from the long side with maximum distance.",
        key_concepts=["Short Side King", "Long Side Rook Distance", "Flank Checks"],
        hint="Step your King towards the short side and deliver horizontal flank checks with maximum checking distance.",
    ),

    # 3. Minor Piece Endgames
    EndgameDrill(
        id="minor_kbnk",
        category=EndgameCategory.MINOR,
        title="Bishop & Knight Checkmate: The 'W' Maneuver",
        fen="8/8/8/8/8/4k3/8/K1BN4 w - - 0 1",
        player_color="white",
        target_goal="mate",
        difficulty=3,
        description="Drive the enemy King to a corner matching the color of your Bishop using Delétang's triangles and the Knight 'W' coordinate maneuver.",
        key_concepts=["Delétang's Triangles", "W-Maneuver", "Color of Bishop's Corner"],
        hint="Coordinate your King, Bishop, and Knight together. Restrict the enemy King into shrinking triangles and herd him toward a1 or h8.",
    ),
    EndgameDrill(
        id="minor_kbbk",
        category=EndgameCategory.MINOR,
        title="Two Bishops Checkmate: Dual Laser Fence",
        fen="8/8/8/8/8/4k3/8/K1BB4 w - - 0 1",
        player_color="white",
        target_goal="mate",
        difficulty=2,
        description="Use the pair of Bishops side-by-side to construct an impenetrable diagonal wall, pushing the King into the corner for mate.",
        key_concepts=["Adjacent Diagonals", "King Confinement", "Corner Mate"],
        hint="Place your Bishops side by side on adjacent diagonals to slice off ranks and files until the King is trapped on the rim.",
    ),
    EndgameDrill(
        id="minor_knight_vs_pawn",
        category=EndgameCategory.MINOR,
        title="Knight vs 7th-Rank Pawn: Drawing the Passer",
        fen="8/7P/8/8/8/5N2/8/4k1K1 w - - 0 1",
        player_color="white",
        target_goal="draw",
        difficulty=2,
        description="Use your Knight's jumping agility to blockade or eliminate the advanced enemy passer before it queens.",
        key_concepts=["Knight Blockade", "Forking Promotion Square", "Time Distance"],
        hint="Position your Knight where it directly covers the promotion square (h8) or can deliver a check that captures the queen.",
    ),

    # 4. Queen Endgames
    EndgameDrill(
        id="queen_vs_pawn_7th_c",
        category=EndgameCategory.QUEEN,
        title="Queen vs Bishop/Central Pawn on the 7th",
        fen="8/2P5/8/8/8/8/1q6/4K2k b - - 0 1",
        player_color="black",
        target_goal="win",
        difficulty=2,
        description="Drive the White King in front of the c-pawn with checking zig-zags, then bring your own King forward in the tempo gained.",
        key_concepts=["King Stepping In Front", "Tempo Zig-Zag", "King March"],
        hint="Deliver Queen checks to force the enemy King directly onto c8 in front of his pawn, then march your King closer on each tempo!",
    ),
    EndgameDrill(
        id="queen_vs_pawn_7th_a",
        category=EndgameCategory.QUEEN,
        title="Queen vs Rook Pawn on the 7th (Draw Trap)",
        fen="8/P7/8/8/8/8/1q6/4K2k b - - 0 1",
        player_color="black",
        target_goal="draw",
        difficulty=2,
        description="Unlike central pawns, a rook-pawn or bishop-pawn on the 7th offers a stalemate haven for the defending King.",
        key_concepts=["Corner Stalemate Defense", "Inherent Rook-Pawn Draw", "Perpetual Threat"],
        hint="When Black pushes White's King to a8, taking the pawn results in stalemate!",
    ),
    EndgameDrill(
        id="queen_vs_rook_philidor",
        category=EndgameCategory.QUEEN,
        title="Queen vs Rook: Philidor's Classic Cross",
        fen="8/8/8/3k4/8/8/3r4/3QK3 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=3,
        description="Win the Rook through zugzwang, fork tactics, and driving the King-Rook battery apart with Queen triangulations.",
        key_concepts=["Queen Forks", "Zugzwang", "Separating King and Rook"],
        hint="Use triangulating Queen checks to separate the Black King and Rook, then deliver a double attack fork to win the Rook.",
    ),
]


class EndgameProgressManager:
    """Manages persistent drill progress, stars, mistakes, and custom FEN drills."""

    def __init__(self, file_path: str = ENDGAME_PROGRESS_FILE):
        self.file_path = file_path
        self._data: dict[str, Any] = {
            "completed_drills": {},
            "custom_drills": [],
        }
        self.load()

    def load(self) -> None:
        """Loads progress from persistent storage."""
        if not os.path.exists(self.file_path):
            self._save_raw()
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as e:
            logger.warning("Failed to load endgame progress from %s: %s", self.file_path, e)
            self._data = {"completed_drills": {}, "custom_drills": []}

    def save(self) -> None:
        """Persists progress to disk."""
        self._save_raw()

    def _save_raw(self) -> None:
        try:
            temp_path = f"{self.file_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(temp_path, self.file_path)
        except Exception as e:
            logger.error("Failed to write endgame progress to %s: %s", self.file_path, e)

    def record_completion(
        self,
        drill_id: str,
        mistakes: int,
        moves_count: int,
        accuracy: float,
    ) -> int:
        """
        Records a completed drill attempt and calculates star rating (1 to 3 stars).

        Returns:
            Calculated star rating for this run.
        """
        if mistakes == 0:
            stars = 3
        elif mistakes <= 2:
            stars = 2
        else:
            stars = 1

        completed_map = self._data.setdefault("completed_drills", {})
        existing = completed_map.get(drill_id, {})
        current_best_stars = existing.get("stars", 0)

        completed_map[drill_id] = {
            "completed_at": time.time(),
            "attempts": existing.get("attempts", 0) + 1,
            "mistakes": mistakes,
            "moves_count": moves_count,
            "accuracy": round(accuracy, 1),
            "stars": max(stars, current_best_stars),
        }
        self.save()
        return stars

    def add_custom_drill(
        self,
        title: str,
        fen: str,
        player_color: str = "white",
        target_goal: str = "win",
        difficulty: int = 2,
        description: str = "",
        hint: str = "",
    ) -> EndgameDrill:
        """Adds and persists a user custom FEN drill."""
        drill_id = f"custom_{int(time.time())}"
        custom_drill = EndgameDrill(
            id=drill_id,
            category=EndgameCategory.CUSTOM,
            title=title or "Custom Endgame Position",
            fen=fen,
            player_color=player_color,
            target_goal=target_goal,
            difficulty=difficulty,
            description=description or "Custom endgame position created by user.",
            key_concepts=["Custom Practice"],
            hint=hint or "Find the best path to achieve the target goal.",
        )
        custom_list = self._data.setdefault("custom_drills", [])
        custom_list.append(custom_drill.to_dict())
        self.save()
        return custom_drill

    def get_all_drills(self) -> list[dict[str, Any]]:
        """Returns all core curriculum + custom drills merged with user progress stats."""
        result: list[dict[str, Any]] = []
        completed_map = self._data.get("completed_drills", {})

        # Core curriculum
        for drill in CORE_CURRICULUM:
            drill_dict = drill.to_dict()
            progress = completed_map.get(drill.id)
            drill_dict["progress"] = progress
            result.append(drill_dict)

        # Custom drills
        for custom_dict in self._data.get("custom_drills", []):
            custom_copy = dict(custom_dict)
            progress = completed_map.get(custom_dict.get("id", ""))
            custom_copy["progress"] = progress
            result.append(custom_copy)

        return result

    def get_drill_by_id(self, drill_id: str) -> EndgameDrill | None:
        """Finds drill by ID from core or custom drills."""
        for drill in CORE_CURRICULUM:
            if drill.id == drill_id:
                return drill
        for custom_dict in self._data.get("custom_drills", []):
            if custom_dict.get("id") == drill_id:
                return EndgameDrill(
                    id=custom_dict["id"],
                    category=EndgameCategory.CUSTOM,
                    title=custom_dict.get("title", "Custom"),
                    fen=custom_dict["fen"],
                    player_color=custom_dict.get("player_color", "white"),
                    target_goal=custom_dict.get("target_goal", "win"),
                    difficulty=custom_dict.get("difficulty", 2),
                    description=custom_dict.get("description", ""),
                    key_concepts=custom_dict.get("key_concepts", []),
                    hint=custom_dict.get("hint", ""),
                    max_plies=custom_dict.get("max_plies", 60),
                )
        return None

    def reset_progress(self) -> None:
        """Resets all drill completion records."""
        self._data["completed_drills"] = {}
        self.save()


# Singleton progress manager instance
progress_manager = EndgameProgressManager()
