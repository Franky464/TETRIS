#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de G-code Tetris bois
- Découpe + Vcarve + Gravure des numéros
- Réduction des doublons de formes
- Choix Avalant / Opposition

Usage :
    python generate_tetris_gcode.py 8x12:4
    python generate_tetris_gcode.py 10x15:6
"""

import random
import math
import sys
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter

# ====================== PARAMÈTRES ======================
MODULE = 12.0
WIDTH_MODULES = 8
HEIGHT_MODULES = 12
MAX_SIZE = 4

THICKNESS = 3.5
PASS_DEPTH = 0.5
SAFE_Z = 5.0
FEED_RATE = 1000
PLUNGE_RATE = 100
SPINDLE_SPEED = 18000

MIN_SIZE = 2
OFFSET = 0.5
VCARVE_OFFSET = 1.0
VCARVE_DEPTH = -1.0

# Direction d'usinage
CLIMB_MILLING = False   # False = Opposition | True = Avalant

# Gravure des numéros
ENGRAVE_DEPTH = -0.5
ENGRAVE_HEIGHT = 3.0
ENGRAVE_FEED = 600
# ========================================================

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

def find_next_empty(grid: Grid) -> Optional[Tuple[int, int]]:
    h, w = len(grid), len(grid[0])
    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                return (x, y)
    return None

def generate_polyomino_in_free_space(grid: Grid, start: Tuple[int, int], size: int):
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
                if (0 <= nx < w and 0 <= ny < h and grid[ny][nx] == 0 and (nx, ny) not in cells):
                    candidates.append((nx, ny))
        if not candidates:
            return None
        cells.add(random.choice(candidates))

    min_x = min(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    shape = sorted([(x - min_x, y - min_y) for x, y in cells])
    origin = (min_x, min_y)
    return shape, origin

def normalize_shape(shape: List[Tuple[int, int]]) -> Tuple[Tuple[int, int], ...]:
    """Retourne une version canonique de la forme (toutes rotations)"""
    def get_rotations(s):
        rotations = []
        current = list(s)
        for _ in range(4):
            minx = min(p[0] for p in current)
            miny = min(p[1] for p in current)
            normalized = tuple(sorted((x - minx, y - miny) for x, y in current))
            rotations.append(normalized)
            # Rotation 90° horaire
            current = [(y, -x) for x, y in current]
        return rotations

    all_rots = get_rotations(shape)
    return min(all_rots)

def try_fill_greedy(max_attempts_per_cell: int = 200) -> Tuple[Grid, Dict[int, List[Tuple[int, int]]]]:
    w, h = WIDTH_MODULES, HEIGHT_MODULES
    total = w * h

    for global_try in range(1, 120):
        print(f"=== Essai global {global_try} ===")
        grid = create_empty_grid(w, h)
        pieces = {}
        pid = 1
        cells_filled = 0
        shape_usage = Counter()

        while cells_filled < total:
            pos = find_next_empty(grid)
            if pos is None:
                break

            remaining = total - cells_filled
            max_possible = min(MAX_SIZE, remaining)
            if max_possible < 1:
                break

            placed = False
            best_candidate = None
            best_score = float('inf')

            if max_possible >= MIN_SIZE:
                for _ in range(max_attempts_per_cell):
                    size = random.randint(MIN_SIZE, max_possible)
                    result = generate_polyomino_in_free_space(grid, pos, size)
                    if result is None:
                        continue

                    shape, (ox, oy) = result
                    if not can_place(grid, shape, ox, oy):
                        continue

                    norm = normalize_shape(shape)
                    score = shape_usage[norm]

                    if score < best_score:
                        best_score = score
                        best_candidate = (shape, ox, oy, size, norm)

                    if score == 0:  # Forme jamais vue → on prend
                        break

            if best_candidate is not None:
                shape, ox, oy, size, norm = best_candidate
                place(grid, shape, ox, oy, pid)
                pieces[pid] = [(ox + dx, oy + dy) for dx, dy in shape]
                shape_usage[norm] += 1
                cells_filled += size
                pid += 1
                placed = True

            # Dernier recours : pièce de 1 module
            if not placed:
                x, y = pos
                place(grid, [(0, 0)], x, y, pid)
                pieces[pid] = [(x, y)]
                cells_filled += 1
                pid += 1
                placed = True

            if not placed:
                print(f"  Bloqué à {cells_filled}/{total} cases")
                break

        if cells_filled == total:
            print(f"✅ Succès en essai {global_try} — {len(pieces)} pièces")
            unique = len(shape_usage)
            duplicates = sum(1 for v in shape_usage.values() if v > 1)
            print(f"   Formes uniques : {unique} | Formes en double ou plus : {duplicates}")
            return grid, pieces

    raise RuntimeError("Impossible de remplir la grille.")

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

    pts = contour[:-1] if contour[0] == contour[-1] else contour[:]
    n = len(pts)
    new_pts = []

    for i in range(n):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]

        dx1 = x1 - x0
        dy1 = y1 - y0
        dx2 = x2 - x1
        dy2 = y2 - y1

        if abs(dx1) > abs(dy1):
            nx1 = 0
            ny1 = 1 if dx1 > 0 else -1
        else:
            nx1 = -1 if dy1 > 0 else 1
            ny1 = 0

        if abs(dx2) > abs(dy2):
            nx2 = 0
            ny2 = 1 if dx2 > 0 else -1
        else:
            nx2 = -1 if dy2 > 0 else 1
            ny2 = 0

        nx = nx1 + nx2
        ny = ny1 + ny2
        length = math.hypot(nx, ny)
        if length > 1e-6:
            nx /= length
            ny /= length
        else:
            nx, ny = nx1, ny1

        new_pts.append((x1 + nx * offset, y1 + ny * offset))

    if new_pts:
        new_pts.append(new_pts[0])
    return new_pts

def reverse_contour(contour: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(contour) < 3:
        return contour
    if contour[0] == contour[-1]:
        pts = contour[:-1]
    else:
        pts = contour[:]
    reversed_pts = pts[::-1]
    reversed_pts.append(reversed_pts[0])
    return reversed_pts

# ====================== POLICE BÂTON ======================
DIGIT_STROKES = {
    '0': [(0.2,0.1, 0.8,0.1), (0.8,0.1, 0.8,0.9), (0.8,0.9, 0.2,0.9), (0.2,0.9, 0.2,0.1)],
    '1': [(0.5,0.1, 0.5,0.9), (0.3,0.75, 0.5,0.9)],
    '2': [(0.2,0.9, 0.8,0.9), (0.8,0.9, 0.8,0.55), (0.8,0.55, 0.2,0.55), (0.2,0.55, 0.2,0.1), (0.2,0.1, 0.8,0.1)],
    '3': [(0.2,0.9, 0.8,0.9), (0.8,0.9, 0.8,0.1), (0.8,0.1, 0.2,0.1), (0.3,0.55, 0.8,0.55)],
    '4': [(0.2,0.9, 0.2,0.55), (0.2,0.55, 0.8,0.55), (0.7,0.9, 0.7,0.1)],
    '5': [(0.8,0.9, 0.2,0.9), (0.2,0.9, 0.2,0.55), (0.2,0.55, 0.8,0.55), (0.8,0.55, 0.8,0.1), (0.8,0.1, 0.2,0.1)],
    '6': [(0.8,0.9, 0.2,0.9), (0.2,0.9, 0.2,0.1), (0.2,0.1, 0.8,0.1), (0.8,0.1, 0.8,0.55), (0.8,0.55, 0.2,0.55)],
    '7': [(0.2,0.9, 0.8,0.9), (0.8,0.9, 0.4,0.1)],
    '8': [(0.2,0.1, 0.8,0.1), (0.8,0.1, 0.8,0.9), (0.8,0.9, 0.2,0.9), (0.2,0.9, 0.2,0.1), (0.2,0.55, 0.8,0.55)],
    '9': [(0.2,0.1, 0.8,0.1), (0.8,0.1, 0.8,0.9), (0.8,0.9, 0.2,0.9), (0.2,0.9, 0.2,0.55), (0.2,0.55, 0.8,0.55)],
}

def get_number_strokes(number: int, height: float) -> List[List[Tuple[float, float]]]:
    text = str(number)
    digit_width = height * 0.7
    spacing = height * 0.15
    total_width = len(text) * digit_width + (len(text) - 1) * spacing

    strokes = []
    x_offset = -total_width / 2

    for char in text:
        if char not in DIGIT_STROKES:
            continue
        for x1, y1, x2, y2 in DIGIT_STROKES[char]:
            px1 = x_offset + x1 * digit_width
            py1 = y1 * height
            px2 = x_offset + x2 * digit_width
            py2 = y2 * height
            strokes.append([(px1, py1), (px2, py2)])
        x_offset += digit_width + spacing
    return strokes

def generate_gcode(pieces: Dict[int, List[Tuple[int, int]]], base_filename: str):
    num_passes = math.ceil(THICKNESS / PASS_DEPTH)

    contours_cut = {}
    contours_vcarve = {}
    engrave_positions = {}
    all_x, all_y = [], []

    for pid, cells in pieces.items():
        raw = get_perfect_contour(cells)
        if len(raw) >= 3:
            cut_contour = offset_contour_inward(raw, OFFSET)
            vcarve_contour = offset_contour_inward(raw, VCARVE_OFFSET)

            if CLIMB_MILLING:
                cut_contour = reverse_contour(cut_contour)
                vcarve_contour = reverse_contour(vcarve_contour)

            contours_cut[pid] = cut_contour
            contours_vcarve[pid] = vcarve_contour

            for x, y in cut_contour + vcarve_contour:
                all_x.append(x)
                all_y.append(y)

        best = max(cells, key=lambda c: (c[0], -c[1]))
        cx = (best[0] + 0.5) * MODULE
        cy = (best[1] + 0.5) * MODULE
        engrave_positions[pid] = (cx, cy)
        all_x.append(cx)
        all_y.append(cy)

    xmin = min(all_x) if all_x else 0
    xmax = max(all_x) if all_x else 0
    ymin = min(all_y) if all_y else 0
    ymax = max(all_y) if all_y else 0

    mode_str = "Avalant (climb)" if CLIMB_MILLING else "Opposition (conventional)"

    # ----- 1. Découpe -----
    with open(f"{base_filename}.nc", "w", encoding="utf-8") as f:
        f.write("; =============================================\n")
        f.write("; G-code Tetris bois - Découpe\n")
        f.write(f"; {WIDTH_MODULES}x{HEIGHT_MODULES} | MAX_SIZE={MAX_SIZE}\n")
        f.write(f"; Offset = {OFFSET} mm | Mode = {mode_str}\n")
        f.write(f"; Xmin={xmin:.3f} Xmax={xmax:.3f} Ymin={ymin:.3f} Ymax={ymax:.3f}\n")
        f.write(f"; Zmin={-THICKNESS:.3f} Zmax={SAFE_Z:.3f}\n")
        f.write("; =============================================\n\n")
        f.write("G21\nG90\nG94\n")
        f.write(f"G0 Z{SAFE_Z:.3f}\nM3 S{SPINDLE_SPEED}\nG0 X0 Y0\n\n")

        for p in range(1, num_passes + 1):
            z = -min(p * PASS_DEPTH, THICKNESS)
            f.write(f"; === PASSE {p}/{num_passes} Z={z:.3f} ===\n")
            for pid in sorted(contours_cut):
                contour = contours_cut[pid]
                f.write(f"; Pièce {pid}\n")
                f.write(f"G0 X{contour[0][0]:.3f} Y{contour[0][1]:.3f}\n")
                f.write(f"G1 Z{z:.3f} F{PLUNGE_RATE}\n")
                for x, y in contour[1:]:
                    f.write(f"G1 X{x:.3f} Y{y:.3f} F{FEED_RATE}\n")
                f.write(f"G0 Z{SAFE_Z:.3f}\n")
            f.write("\n")
        f.write("M5\nG0 Z10\nG0 X0 Y0\nM30\n")
    print(f"✅ Découpe     : {base_filename}.nc")

    # ----- 2. Vcarve -----
    with open(f"{base_filename}_vcarve.nc", "w", encoding="utf-8") as f:
        f.write("; =============================================\n")
        f.write("; G-code Tetris bois - Vcarve\n")
        f.write(f"; Offset Vcarve = {VCARVE_OFFSET} mm | Mode = {mode_str}\n")
        f.write(f"; Xmin={xmin:.3f} Xmax={xmax:.3f} Ymin={ymin:.3f} Ymax={ymax:.3f}\n")
        f.write("; =============================================\n\n")
        f.write("G21\nG90\nG94\n")
        f.write(f"G0 Z{SAFE_Z:.3f}\nM3 S{SPINDLE_SPEED}\nG0 X0 Y0\n\n")

        for pid in sorted(contours_vcarve):
            contour = contours_vcarve[pid]
            f.write(f"; Pièce {pid}\n")
            f.write(f"G0 X{contour[0][0]:.3f} Y{contour[0][1]:.3f}\n")
            f.write(f"G1 Z{VCARVE_DEPTH:.3f} F{PLUNGE_RATE}\n")
            for x, y in contour[1:]:
                f.write(f"G1 X{x:.3f} Y{y:.3f} F{FEED_RATE}\n")
            f.write(f"G0 Z{SAFE_Z:.3f}\n")
        f.write("\nM5\nG0 Z10\nG0 X0 Y0\nM30\n")
    print(f"✅ Vcarve      : {base_filename}_vcarve.nc")

    # ----- 3. Numéros -----
    with open(f"{base_filename}_numbers.nc", "w", encoding="utf-8") as f:
        f.write("; =============================================\n")
        f.write("; G-code Tetris bois - Gravure des numéros\n")
        f.write(f"; Hauteur={ENGRAVE_HEIGHT}mm | Profondeur={ENGRAVE_DEPTH}mm\n")
        f.write("; =============================================\n\n")
        f.write("G21\nG90\nG94\n")
        f.write(f"G0 Z{SAFE_Z:.3f}\nM3 S{SPINDLE_SPEED}\nG0 X0 Y0\n\n")

        for pid in sorted(engrave_positions):
            cx, cy = engrave_positions[pid]
            strokes = get_number_strokes(pid, ENGRAVE_HEIGHT)
            f.write(f"; ---------- Numéro {pid} ----------\n")

            first = True
            last_end = None
            for stroke in strokes:
                x1, y1 = stroke[0]
                x2, y2 = stroke[1]
                abs_x1, abs_y1 = cx + x1, cy + y1
                abs_x2, abs_y2 = cx + x2, cy + y2

                need_retract = True
                if last_end is not None:
                    if math.hypot(abs_x1 - last_end[0], abs_y1 - last_end[1]) < 0.3:
                        need_retract = False

                if need_retract:
                    if not first:
                        f.write(f"G0 Z{SAFE_Z:.3f}\n")
                    f.write(f"G0 X{abs_x1:.3f} Y{abs_y1:.3f}\n")
                    f.write(f"G1 Z{ENGRAVE_DEPTH:.3f} F{PLUNGE_RATE}\n")
                else:
                    f.write(f"G1 X{abs_x1:.3f} Y{abs_y1:.3f} F{ENGRAVE_FEED}\n")

                f.write(f"G1 X{abs_x2:.3f} Y{abs_y2:.3f} F{ENGRAVE_FEED}\n")
                last_end = (abs_x2, abs_y2)
                first = False

            f.write(f"G0 Z{SAFE_Z:.3f}\n\n")
        f.write("M5\nG0 Z10\nG0 X0 Y0\nM30\n")
    print(f"✅ Numéros     : {base_filename}_numbers.nc")

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
            print("Format attendu : 10x15:6")
            sys.exit(1)

    print(f"Paramètres : {WIDTH_MODULES}x{HEIGHT_MODULES} | MAX_SIZE={MAX_SIZE}")
    print(f"Mode d'usinage : {'Avalant (climb)' if CLIMB_MILLING else 'Opposition (conventional)'}")

    random.seed()
    grid, pieces = try_fill_greedy()

    sizes = [len(c) for c in pieces.values()]
    print("\nRépartition des tailles :")
    for s, cnt in sorted(Counter(sizes).items()):
        print(f"  {s} modules : {cnt} pièce(s)")

    base = f"tetris_{WIDTH_MODULES}x{HEIGHT_MODULES}_max{MAX_SIZE}"
    generate_gcode(pieces, base)

    print("\nGrille :")
    for row in grid:
        print(" ".join(f"{c:2}" for c in row))