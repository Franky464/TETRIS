#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de G-code Tetris bois

Usage :
    python generate_tetris_gcode.py
    python generate_tetris_gcode.py 8x12:4
    python generate_tetris_gcode.py 10x15:6
    python generate_tetris_gcode.py 12x16
"""

import random
import math
import sys
import time
from typing import List, Tuple, Dict, Set, Optional
from collections import defaultdict

# ====================== PARAMÈTRES PAR DÉFAUT ======================
MODULE = 12.0
WIDTH_MODULES = 8
HEIGHT_MODULES = 12
MAX_SIZE = 4

THICKNESS = 6.0
PASS_DEPTH = 1.0
SAFE_Z = 5.0
FEED_RATE = 1000
PLUNGE_RATE = 100
SPINDLE_SPEED = 18000

MIN_SIZE = 1
OFFSET = 0.5

DEBUG = True
MAX_TIME_SECONDS = 45
# ===================================================================

Grid = List[List[int]]

def create_empty_grid(w: int, h: int) -> Grid:
    return [[0 for _ in range(w)] for _ in range(h)]

def can_place(grid: Grid, shape: List[Tuple[int, int]], x: int, y: int) -> bool:
    h, w = len(grid), len(grid[0])
    for dx, dy in shape:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h) or grid[ny][nx] != 0:
            return False
    return True

def place(grid: Grid, shape: List[Tuple[int, int]], x: int, y: int, pid: int):
    for dx, dy in shape:
        grid[y + dy][x + dx] = pid

def remove(grid: Grid, shape: List[Tuple[int, int]], x: int, y: int):
    for dx, dy in shape:
        grid[y + dy][x + dx] = 0

def generate_polyominoes(size: int, count: int = 20) -> List[List[Tuple[int, int]]]:
    shapes = []
    seen = set()
    for _ in range(count * 3):
        cells = {(0, 0)}
        while len(cells) < size:
            candidates = []
            for cx, cy in cells:
                for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) not in cells:
                        candidates.append((nx, ny))
            if not candidates:
                break
            cells.add(random.choice(candidates))
        
        min_x = min(c[0] for c in cells)
        min_y = min(c[1] for c in cells)
        base = tuple(sorted([(x - min_x, y - min_y) for x, y in cells]))
        
        shape = list(base)
        for rot in range(4):
            if rot > 0:
                shape = [(dy, -dx) for dx, dy in shape]
                minx = min(p[0] for p in shape)
                miny = min(p[1] for p in shape)
                shape = sorted([(p[0]-minx, p[1]-miny) for p in shape])
            
            tshape = tuple(shape)
            if tshape not in seen:
                seen.add(tshape)
                shapes.append(shape)
                if len(shapes) >= count:
                    return shapes
    return shapes

def find_next_empty(grid: Grid) -> Optional[Tuple[int, int]]:
    h, w = len(grid), len(grid[0])
    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                return (x, y)
    return None

def try_fill_recursive(grid: Grid, pieces: Dict, pid: int, cells_left: int,
                       start_time: float, stats: Dict) -> bool:
    if time.time() - start_time > MAX_TIME_SECONDS:
        return False

    stats["calls"] += 1

    if cells_left == 0:
        return True

    pos = find_next_empty(grid)
    if pos is None:
        return cells_left == 0

    x, y = pos

    if DEBUG and stats["calls"] % 5000 == 0:
        elapsed = time.time() - start_time
        print(f"  ... appels: {stats['calls']:6d} | pièces: {pid-1:3d} | "
              f"restant: {cells_left:3d} | temps: {elapsed:.1f}s")

    sizes = list(range(min(MAX_SIZE, cells_left), MIN_SIZE - 1, -1))

    for size in sizes:
        shapes = generate_polyominoes(size, count=10)

        for shape in shapes:
            for dx, dy in shape:
                px = x - dx
                py = y - dy
                if can_place(grid, shape, px, py):
                    place(grid, shape, px, py, pid)
                    pieces[pid] = [(px + sx, py + sy) for sx, sy in shape]

                    if try_fill_recursive(grid, pieces, pid + 1, cells_left - size,
                                          start_time, stats):
                        return True

                    remove(grid, shape, px, py)
                    del pieces[pid]
    return False

def try_fill_grid() -> Tuple[Grid, Dict[int, List[Tuple[int, int]]]]:
    w, h = WIDTH_MODULES, HEIGHT_MODULES
    total = w * h
    print(f"\nTentative de remplissage {w}×{h} = {total} cases  (MAX_SIZE={MAX_SIZE})")
    print(f"Timeout par essai = {MAX_TIME_SECONDS}s\n")

    for attempt in range(1, 31):
        print(f"=== Essai {attempt} ===")
        grid = create_empty_grid(w, h)
        pieces = {}
        stats = {"calls": 0}
        start_time = time.time()

        success = try_fill_recursive(grid, pieces, 1, total, start_time, stats)

        elapsed = time.time() - start_time
        print(f"  → appels : {stats['calls']}  |  temps : {elapsed:.2f}s")

        if success:
            print(f"\n✅ Tiling réussi en essai {attempt} — {len(pieces)} pièces")
            return grid, pieces
        else:
            print(f"  ❌ Échec\n")

    raise RuntimeError("Impossible de trouver un tiling dans le temps imparti.")

def get_perfect_contour(cells: List[Tuple[int, int]]) -> List[Tuple[float, float]]:
    if not cells:
        return []

    cell_set = set(cells)
    edges = []

    for x, y in cells:
        if (x, y - 1) not in cell_set:
            edges.append(((x, y), (x + 1, y)))
        if (x + 1, y) not in cell_set:
            edges.append(((x + 1, y), (x + 1, y + 1)))
        if (x, y + 1) not in cell_set:
            edges.append(((x + 1, y + 1), (x, y + 1)))
        if (x - 1, y) not in cell_set:
            edges.append(((x, y + 1), (x, y)))

    if not edges:
        return []

    next_point = defaultdict(list)
    for a, b in edges:
        next_point[a].append(b)

    start = min(next_point.keys(), key=lambda p: (p[1], p[0]))
    contour = [start]
    current = start
    visited = set()

    while True:
        found = False
        for cand in next_point.get(current, []):
            edge = (current, cand)
            if edge not in visited:
                visited.add(edge)
                contour.append(cand)
                current = cand
                found = True
                break
        if not found or (current == start and len(contour) > 1):
            break
        if len(contour) > len(edges) + 5:
            break

    points = [(x * MODULE, y * MODULE) for x, y in contour]

    cleaned = []
    for i, p in enumerate(points):
        if i == 0 or i == len(points) - 1:
            cleaned.append(p)
            continue
        prev, nxt = points[i-1], points[i+1]
        cross = (p[0]-prev[0])*(nxt[1]-p[1]) - (p[1]-prev[1])*(nxt[0]-p[0])
        if abs(cross) > 1e-6:
            cleaned.append(p)

    if cleaned and cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    return cleaned

def offset_contour_inward(contour: List[Tuple[float, float]], offset: float) -> List[Tuple[float, float]]:
    if len(contour) < 4 or offset <= 0:
        return contour

    result = []
    n = len(contour) - 1
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx =  dy / length
        ny = -dx / length
        result.append((x1 + nx * offset, y1 + ny * offset))

    if result:
        result.append(result[0])
    return result

def generate_gcode(pieces: Dict[int, List[Tuple[int, int]]], filename: str):
    num_passes = math.ceil(THICKNESS / PASS_DEPTH)

    contours = {}
    for pid, cells in pieces.items():
        raw = get_perfect_contour(cells)
        if len(raw) >= 3:
            contours[pid] = offset_contour_inward(raw, OFFSET)

    with open(filename, "w", encoding="utf-8") as f:
        f.write("; G-code Tetris bois\n")
        f.write(f"; {WIDTH_MODULES}x{HEIGHT_MODULES} | MAX_SIZE={MAX_SIZE} | Offset={OFFSET}mm\n")
        f.write("G21\nG90\nG94\n")
        f.write(f"G0 Z{SAFE_Z:.3f}\n")
        f.write(f"M3 S{SPINDLE_SPEED}\n")
        f.write("G0 X0 Y0\n\n")

        for p in range(1, num_passes + 1):
            z = -min(p * PASS_DEPTH, THICKNESS)
            f.write(f"; === PASSE {p}/{num_passes} Z={z:.3f} ===\n")
            for pid in sorted(contours.keys()):
                contour = contours[pid]
                f.write(f"G0 X{contour[0][0]:.3f} Y{contour[0][1]:.3f}\n")
                f.write(f"G1 Z{z:.3f} F{PLUNGE_RATE}\n")
                for x, y in contour[1:]:
                    f.write(f"G1 X{x:.3f} Y{y:.3f} F{FEED_RATE}\n")
                f.write(f"G0 Z{SAFE_Z:.3f}\n")
            f.write("\n")

        f.write("M5\nG0 Z10\nG0 X0 Y0\nM30\n")

    print(f"\nG-code généré : {filename}")

if __name__ == "__main__":
    # ---------- Parsing de l'argument ----------
    # Formats acceptés :
    #   8x12:4
    #   10x15:6
    #   12x16
    if len(sys.argv) > 1:
        try:
            arg = sys.argv[1].lower().replace(" ", "")
            
            if ":" in arg:
                size_part, max_part = arg.split(":")
                MAX_SIZE = int(max_part)
            else:
                size_part = arg

            w_str, h_str = size_part.split("x")
            WIDTH_MODULES = int(w_str)
            HEIGHT_MODULES = int(h_str)

        except Exception as e:
            print("Erreur de format d'argument.")
            print("Exemples valides :")
            print("  python generate_tetris_gcode.py 8x12:4")
            print("  python generate_tetris_gcode.py 10x15:6")
            print("  python generate_tetris_gcode.py 12x16")
            sys.exit(1)

    print(f"Paramètres : {WIDTH_MODULES}x{HEIGHT_MODULES}  |  MAX_SIZE = {MAX_SIZE}")

    random.seed()
    grid, pieces = try_fill_grid()

    filename = f"tetris_{WIDTH_MODULES}x{HEIGHT_MODULES}_max{MAX_SIZE}.nc"
    generate_gcode(pieces, filename)

    print("\nGrille :")
    for row in grid:
        print(" ".join(f"{c:2}" for c in row))