"""
app/endgame_db.py

Curriculum database and progress persistence manager for the Endgame Tablebase Trainer.
Contains the curated 12-drill core curriculum (Pawn, Rook, Minor Piece, Queen endgames)
and manages user progress, star ratings, mistakes, and custom user drills.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("smart-chess-app.endgame")

ENDGAME_PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "endgame_progress.json",
)


class EndgameCategory(str, Enum):
    PAWN = "pawn"
    PAWNS = "pawn"
    ROOK = "rook"
    ROOKS = "rook"
    MINOR = "minor"
    MINORS = "minor"
    QUEEN = "queen"
    QUEENS = "queen"
    CUSTOM = "custom"


@dataclass
class EndgameDrill:
    id: str
    category: EndgameCategory
    title: str
    fen: str
    player_color: str  # "white" | "black"
    target_goal: str   # "win" | "draw" | "mate"
    difficulty: int = 1    # 1 (Beginner), 2 (Intermediate), 3 (Master)
    description: str = ""
    key_concepts: list[str] = field(default_factory=list)
    hint: str = ""
    max_plies: int = 60
    target_moves_par: int = 15
    solution_line: list[str] = field(default_factory=list)
    solution_explanation: str = ""

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
            "target_moves_par": self.target_moves_par,
            "solution_line": self.solution_line,
            "solution_explanation": self.solution_explanation,
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
        solution_line=["1. Kd3 Kd5", "2. e3 Ke5", "3. e4 Ke6", "4. Kd4 Kd6", "5. e5+ Ke6", "6. Ke4 Ke7", "7. Kd5 Kd7", "8. e6+ Ke7", "9. Ke5 Ke8", "10. Kd6 Kd8", "11. e7+ Ke8", "12. Ke6"],
        solution_explanation="1. Take direct opposition with 1. Kd3!. 2. Step your King into key squares ahead of the pawn. 3. Advance the pawn only when your King firmly controls the path, avoiding stalemate on e6.",
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
        solution_line=["1... Kg4", "2. Kg2 Kh4", "3. h3 Kh5", "4. Kg3 Kg5", "5. h4+ Kh5", "6. Kh3 Kh6", "7. Kg4 Kg6", "8. h5+ Kh6", "9. Kh4 Kh7", "10. Kg5 Kg7", "11. h6+ Kh7", "12. Kh5 Kh8", "13. Kg6 Kg8", "14. h7+ Kh8", "15. Kh6"],
        solution_explanation="Cycle your King into the corner pocket (h8/g8). White is forced to either stalemate Black or give up the h-pawn.",
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
        solution_line=["1. a5 Kd2", "2. a6 Kc3", "3. a7 Kb4", "4. a8=Q"],
        solution_explanation="Push the a-pawn immediately! Because Black's King starts outside the square (a4-a8-e8-e4), Black cannot catch the pawn before it promotes on a8.",
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
        solution_line=["1. Rd1+ Ke7", "2. Rd4 Ra1", "3. Kc7 Rc1+", "4. Kb6 Rb1+", "5. Kc6 Rc1+", "6. Kb5 Rb1+", "7. Rb4"],
        solution_explanation="1. Cut off Black's King with 1. Rd1+ Ke7. 2. Build the bridge with 2. Rd4! (4th rank). 3. Step King out to c7. When Black checks from behind, retreat King to b5 and interpose with 7. Rb4!, ensuring the b-pawn promotes safely!",
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
        solution_line=["1... Re6", "2. Kf3 Rf6+", "3. Ke3 Re6", "4. Kd4 Rd6+", "5. Kc5 Re6", "6. Re1 Re5+", "7. Kd4 Ra5", "8. e5 Ra8"],
        solution_explanation="Hold your Rook on the 6th rank cutoff until White pushes e5. Once e5 is pushed, immediately drop to the 1st rank (Ra8/Re8) to deliver endless distance checks from behind!",
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
        solution_line=["1. Kd2 Re8", "2. Ra4 Kc5", "3. Kd3 Rd8+", "4. Kc3"],
        solution_explanation="Keep your King on the short side of the pawn while using your Rook to deliver flank checks from the long side at maximum checking distance.",
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
        solution_line=["1. Bb2 Kd3", "2. Kb1 Kd2", "3. Nf2 Ke3", "4. Nh3 Ke4", "5. Kc2"],
        solution_explanation="Drive the opposing King toward a corner matching your Bishop's square color using Delétang's shrinking triangles and the Knight 'W' coordinate pattern.",
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
        solution_line=["1. Bc2 Kd4", "2. Bb2+ Kc4", "3. Kb1 Kb4", "4. Kc1 Kc4", "5. Kd2"],
        solution_explanation="Place your pair of Bishops side by side on adjacent diagonals to build an impassable barrier, gradually herding the enemy King to the edge and corner.",
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
        solution_line=["1. Ng5 Ke2", "2. Nh3 Kf3", "3. h8=Q"],
        solution_explanation="Position the Knight to cover the promotion square or fork the King and newly promoted piece.",
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
        solution_line=["1... Qe5+", "2. Kd2 Qxc7", "3. Kd3 Kg2"],
        solution_explanation="Deliver zig-zag checks with your Queen to force White's King directly onto c8 in front of the pawn, then use the tempo to march your King forward.",
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
        solution_line=["1... Qa1+", "2. Ke2 Qxa7", "3. Kd3"],
        solution_explanation="Be careful: with a rook-pawn on the 7th, driving White into the corner (a8) results in stalemate if you block without check.",
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
        solution_line=["1. Qxd2+ Ke4", "2. Ke2 Kf5", "3. Qd4"],
        solution_explanation="Use triangulation checks with your Queen to separate the King and Rook, eventually forking the Rook or forcing a skewering check.",
    ),
]

CORE_ENDGAME_DRILLS = CORE_CURRICULUM


class EndgameProgressManager:
    """Manages persistent drill progress, stars, mistakes, and custom FEN drills."""

    def __init__(self, file_path: str = ENDGAME_PROGRESS_FILE, storage_path: str | None = None):
        self.file_path = storage_path or file_path
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
            with open(self.file_path, encoding="utf-8") as f:
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

    def get_progress(self, drill_id: str) -> dict[str, Any] | None:
        """Returns progress stats for a drill or None if not completed."""
        return self._data.get("completed_drills", {}).get(drill_id)

    def reset_progress(self) -> None:
        """Resets all drill completion records."""
        self._data["completed_drills"] = {}
        self.save()


# Singleton progress manager instance
progress_manager = EndgameProgressManager()
