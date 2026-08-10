#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de G-code Tetris bois - Version Gloutonne (rapide)

Usage :
    python generate_tetris_gcode.py
    python generate_tetris_gcode.py 8x12:4
    python generate_tetris_gcode.py 10x15:6
"""

import random
import math
import sys
from typing import List, Tuple, Dict, Optional
from collections import defaultdict

# ====================== PARAMÈTRES PAR DÉFAUT ======================
MODULE = 12.0
WIDTH_MODULES = 8
HEIGHT_MODULES = 12
MAX_SIZE = 4

THICKNESS = 1.0
PASS_DEPTH = 1.0
SAFE_Z = 5.0
FEED_RATE = 1000
PLUNGE_RATE = 100
SPINDLE_SPEED = 18000

MIN_SIZE = 1          # Mets 1 si tu veux autoriser les monominoes
OFFSET = 2
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

def generate_polyomino_in_free_space(grid: Grid, start: Tuple[int, int], size: int) -> Optional[List[Tuple[int, int]]]:
    """
    Génère un polyomino de 'size' cases qui :
    - Part de la case 'start'
    - Ne pousse que dans les cases encore libres
    """
    h, w = len(grid), len(grid[0])
    sx, sy = start

    if grid[sy][sx] != 0:
        return None

    cells = {(sx, sy)}
    
    while len(cells) < size:
        candidates = []
        for cx, cy in cells:
            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = cx + dx, cy + dy
                if (0 <= nx < w and 0 <= ny < h and 
                    grid[ny][nx] == 0 and (nx, ny) not in cells):
                    candidates.append((nx, ny))
        
        if not candidates:
            return None  # impossible d'atteindre la taille demandée
        
        cells.add(random.choice(candidates))
    
    # Normalisation relative
    min_x = min(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    shape = sorted([(x - min_x, y - min_y) for x, y in cells])
    origin = (min_x, min_y)
    return shape, origin

def find_next_empty(grid: Grid) -> Optional[Tuple[int, int]]:
    h, w = len(grid), len(grid[0])
    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                return (x, y)
    return None

def try_fill_greedy(max_attempts_per_cell: int = 120) -> Tuple[Grid, Dict[int, List[Tuple[int, int]]]]:
    w, h = WIDTH_MODULES, HEIGHT_MODULES
    total = w * h

    for global_try in range(1, 80):
        print(f"=== Essai global {global_try} ===")
        grid = create_empty_grid(w, h)
        pieces = {}
        pid = 1
        cells_filled = 0

        while cells_filled < total:
            pos = find_next_empty(grid)
            if pos is None:
                break

            remaining = total - cells_filled
            max_possible = min(MAX_SIZE, remaining)

            if max_possible < MIN_SIZE:
                break

            placed = False

            # On favorise les grandes pièces
            sizes_to_try = list(range(max_possible, MIN_SIZE - 1, -1))

            for size in sizes_to_try:
                for _ in range(max_attempts_per_cell // len(sizes_to_try) + 5):
                    result = generate_polyomino_in_free_space(grid, pos, size)
                    if result is None:
                        continue

                    shape, (ox, oy) = result

                    if can_place(grid, shape, ox, oy):
                        place(grid, shape, ox, oy, pid)
                        pieces[pid] = [(ox + dx, oy + dy) for dx, dy in shape]
                        cells_filled += size
                        pid += 1
                        placed = True
                        break
                if placed:
                    break

            if not placed:
                # On est bloqué
                print(f"  Bloqué à {cells_filled}/{total} cases")
                break

        if cells_filled == total:
            print(f"✅ Succès en essai {global_try} — {len(pieces)} pièces")
            return grid, pieces

    raise RuntimeError("Impossible de remplir la grille même avec la version améliorée.")

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
        f.write("; G-code Tetris bois - Version gloutonne\n")
        f.write(f"; {WIDTH_MODULES}x{HEIGHT_MODULES} | MAX_SIZE={MAX_SIZE} | Offset={OFFSET}mm\n")
        f.write("G21\nG90\nG94\n")
        f.write(f"G0 Z{SAFE_Z:.3f}\n")
        f.write(f"M3 S{SPINDLE_SPEED}\n")
        f.write("G0 X0 Y0\n\n")

        for p in range(1, num_passes + 1):
            z = -min(p * PASS_DEPTH, THICKNESS)
            f.write(f"; === PASSE {p}/{num_passes} Z={z:.3f} ===\n")
            for pid in sorted(contours.keys()):
                f.write(f"; Pièce {pid} : {len(pieces[pid])} cases\n")
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
        except Exception:
            print("Format attendu : 8x12:4  ou  10x15:6")
            sys.exit(1)

    print(f"Paramètres : {WIDTH_MODULES}x{HEIGHT_MODULES}  |  MAX_SIZE = {MAX_SIZE}")

    random.seed()
    grid, pieces = try_fill_greedy()

    filename = f"tetris_{WIDTH_MODULES}x{HEIGHT_MODULES}_max{MAX_SIZE}.nc"
    generate_gcode(pieces, filename)

    print("\nGrille :")
    for row in grid:
        print(" ".join(f"{c:2}" for c in row))