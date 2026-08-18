"""
app/path_interpolator.py

Geometric and discrete path interpolation for chess piece movements.
Computes ordered sequences of board coordinates (file, rank) from origin to destination
for horizontal, vertical, diagonal, Knight (L-shape), and general moves.
"""

from typing import List, Tuple


def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    """
    Computes an 8-connected discrete line from (x0, y0) to (x1, y1) using Bresenham's algorithm.

    Args:
        x0: Start X/file coordinate.
        y0: Start Y/rank coordinate.
        x1: End X/file coordinate.
        y1: End Y/rank coordinate.

    Returns:
        List of (x, y) tuples from start to end inclusive.
    """
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    curr_x, curr_y = x0, y0

    while True:
        points.append((curr_x, curr_y))
        if curr_x == x1 and curr_y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            curr_x += sx
        if e2 <= dx:
            err += dx
            curr_y += sy

    return points


def interpolate_move_path(
    from_c: int, from_r: int, to_c: int, to_r: int
) -> List[Tuple[int, int]]:
    """
    Interpolates an ordered square path representing the movement trajectory between two squares.

    Coordinates are 0-indexed:
      - File c: 0..7 (a=0 .. h=7)
      - Rank r: 0..7 (Rank 1=0 .. Rank 8=7)

    Supported trajectories:
      - Stationary: [(from_c, from_r)]
      - Horizontal moves: Rook / Queen rank traversal
      - Vertical moves: Rook / Queen / Pawn file traversal
      - Diagonal moves: Bishop / Queen diagonal traversal
      - Knight moves: Proper discrete L-shape (2 steps along major axis, then 1 step perpendicular)
      - Arbitrary: Bresenham line fallback

    Args:
        from_c: Origin file index (0..7).
        from_r: Origin rank index (0..7).
        to_c: Destination file index (0..7).
        to_r: Destination rank index (0..7).

    Returns:
        Ordered list of (file, rank) tuples from origin to destination inclusive.
    """
    if from_c == to_c and from_r == to_r:
        return [(from_c, from_r)]

    dc = to_c - from_c
    dr = to_r - from_r
    abs_dc = abs(dc)
    abs_dr = abs(dr)

    # 1. Horizontal Move (same rank)
    if from_r == to_r:
        step_c = 1 if dc > 0 else -1
        return [(c, from_r) for c in range(from_c, to_c + step_c, step_c)]

    # 2. Vertical Move (same file)
    if from_c == to_c:
        step_r = 1 if dr > 0 else -1
        return [(from_c, r) for r in range(from_r, to_r + step_r, step_r)]

    # 3. Diagonal Move
    if abs_dc == abs_dr:
        step_c = 1 if dc > 0 else -1
        step_r = 1 if dr > 0 else -1
        return [
            (from_c + i * step_c, from_r + i * step_r)
            for i in range(abs_dc + 1)
        ]

    # 4. Knight Move (L-shape)
    if (abs_dc == 1 and abs_dr == 2) or (abs_dc == 2 and abs_dr == 1):
        step_c = 1 if dc > 0 else -1
        step_r = 1 if dr > 0 else -1

        if abs_dr == 2:
            # Vertical major: 2 steps vertically, then 1 step horizontally
            return [
                (from_c, from_r),
                (from_c, from_r + step_r),
                (from_c, from_r + 2 * step_r),
                (to_c, to_r),
            ]
        else:
            # Horizontal major: 2 steps horizontally, then 1 step vertically
            return [
                (from_c, from_r),
                (from_c + step_c, from_r),
                (from_c + 2 * step_c, from_r),
                (to_c, to_r),
            ]

    # 5. General Line Fallback (Bresenham)
    return bresenham_line(from_c, from_r, to_c, to_r)


def interpolate_uci_move(uci: str) -> List[Tuple[int, int]]:
    """
    Parses a UCI move string (e.g. 'e2e4', 'g1f3') and computes the interpolated path.

    Args:
        uci: UCI move string (4 or 5 characters).

    Returns:
        List of (file, rank) tuples from origin to destination.
    """
    uci = uci.strip().lower()
    if len(uci) < 4:
        return []

    try:
        from_c = ord(uci[0]) - ord("a")
        from_r = int(uci[1]) - 1
        to_c = ord(uci[2]) - ord("a")
        to_r = int(uci[3]) - 1
    except (ValueError, IndexError):
        return []

    if 0 <= from_c < 8 and 0 <= from_r < 8 and 0 <= to_c < 8 and 0 <= to_r < 8:
        return interpolate_move_path(from_c, from_r, to_c, to_r)
    return []
