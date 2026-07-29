#!/usr/bin/env python3
"""Trace a high-contrast raster logo into closed, simplified SVG paths."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageFilter


def rdp(points, epsilon):
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    denom = math.hypot(dx, dy)
    best_index = 0
    best_distance = 0.0
    for index, point in enumerate(points[1:-1], 1):
        if denom:
            distance = abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / denom
        else:
            distance = math.dist(point, start)
        if distance > best_distance:
            best_index, best_distance = index, distance
    if best_distance <= epsilon:
        return [start, end]
    left = rdp(points[: best_index + 1], epsilon)
    right = rdp(points[best_index:], epsilon)
    return left[:-1] + right


def remove_small_components(mask, width, height, minimum):
    seen = set()
    kept = set()
    for cell in mask:
        if cell in seen:
            continue
        queue = deque([cell])
        seen.add(cell)
        component = []
        while queue:
            x, y = queue.popleft()
            component.append((x, y))
            for candidate in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if candidate in mask and candidate not in seen:
                    seen.add(candidate)
                    queue.append(candidate)
        if len(component) >= minimum:
            kept.update(component)
    return kept


def boundary_loops(mask):
    edges = []
    for x, y in mask:
        if (x, y - 1) not in mask:
            edges.append(((x, y), (x + 1, y)))
        if (x + 1, y) not in mask:
            edges.append(((x + 1, y), (x + 1, y + 1)))
        if (x, y + 1) not in mask:
            edges.append(((x + 1, y + 1), (x, y + 1)))
        if (x - 1, y) not in mask:
            edges.append(((x, y + 1), (x, y)))
    outgoing = defaultdict(list)
    for start, end in edges:
        outgoing[start].append(end)
    unused = set(edges)
    loops = []
    while unused:
        start, current = next(iter(unused))
        loop = [start, current]
        unused.remove((start, current))
        while current != start:
            choices = [end for end in outgoing[current] if (current, end) in unused]
            if not choices:
                break
            nxt = choices[0]
            unused.remove((current, nxt))
            current = nxt
            loop.append(current)
        if len(loop) >= 5 and loop[-1] == start:
            loops.append(loop[:-1])
    return loops


def polygon_area(points):
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--minimum-component", type=int, default=18)
    parser.add_argument("--simplify", type=float, default=1.1)
    args = parser.parse_args()

    image = Image.open(args.source).convert("L")
    bbox = Image.eval(image, lambda value: 255 if value < 235 else 0).getbbox()
    if bbox is None:
        raise SystemExit("No dark artwork found")
    image = image.crop(bbox)
    height = round(image.height * args.width / image.width)
    image = image.resize((args.width, height), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.MedianFilter(3))
    mask = {
        (x, y)
        for y in range(height)
        for x in range(args.width)
        if image.getpixel((x, y)) < args.threshold
    }
    mask = remove_small_components(mask, args.width, height, args.minimum_component)
    loops = []
    for loop in boundary_loops(mask):
        closed = loop + [loop[0]]
        simplified = rdp(closed, args.simplify)[:-1]
        if len(simplified) >= 3 and abs(polygon_area(simplified)) >= args.minimum_component:
            loops.append(simplified)
    paths = []
    for loop in loops:
        commands = [f"M {loop[0][0]:.2f} {loop[0][1]:.2f}"]
        commands.extend(f"L {x:.2f} {y:.2f}" for x, y in loop[1:])
        commands.append("Z")
        paths.append(f'  <path d="{" ".join(commands)}" fill="#000000"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {args.width} {height}">\n'
        + "\n".join(paths)
        + "\n</svg>\n"
    )
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(svg, encoding="utf-8")
    print(f"paths={len(paths)} viewBox={args.width}x{height}")


if __name__ == "__main__":
    main()
