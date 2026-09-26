#!/usr/bin/env python3
"""Interpret the Marunouchi corridor as a walkable graph, straight from
udx/tran CityGML (no Unity import needed).

Feeds docs/puzzle-generation.md S1 (corridor selection / k-shortest paths)
and S4 (難化ポテンシャル) with a real board graph before the Unity-side
network generation exists.

Construction (v1, topology-first):
  node  - 車道交差部 (TrafficArea function 1020) polygons. One real
          intersection is often split into several non-touching pieces, so
          pieces merge with a wider tolerance (max(tol, 10 m)) than the
          street-level touch tolerance.
  edge  - 車道部 (1000/1010) polygons -> "strips". A strip's centerline is
          approximated by its farthest-vertex pair. Strip ends touching
          other strips / intersections become junctions, so edges come out
          as intersection-to-intersection segments, with dead ends and
          mid-block branches as pseudo nodes.
  attrs - 歩道部 (2000/2020) polygons touching a strip -> sidewalk count /
          area per edge; street name from Road gml:name.
  CRS   - input is EPSG:6697 (lat, lon, z per the axis order in the files);
          treated as WGS84 and projected to local meters around Marunouchi.

Known v1 limitations (by design, revisit when the Unity pipeline lands):
  - centerlines are diameter approximations (straight; curved streets come
    out angular), interior rings are ignored
  - touches are detected via vertex-to-segment proximity
  - one-way streets / signals are not modelled (盤面側の D25 で扱う)

Output (default artifacts/city_graph/):
  graph.geojson    nodes + edges (WGS84 lon/lat, lengths in meters)
  stats.json       counts, degree histogram, connectivity, demo paths
  city-graph.svg   debug render (graph over road polygons)
  city-graph.png   same, via headless Chrome when available

Usage:
  python3 tools/gen_city_graph.py 53394611 53394620 53394621 53394610 \
      --root vendor/citygml --bbox marunouchi
  python3 tools/gen_city_graph.py --selftest
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

TRAN = "http://www.opengis.net/citygml/transportation/2.0"
GML = "http://www.opengis.net/gml"
GMLID = f"{{{GML}}}id"

EARTH_R = 6378137.0

INTERSECTION_CODES = {"1020"}  # 車道交差部
ROADWAY_CODES = {"1000", "1010"}  # 車道部 / 車線
SIDEWALK_CODES = {"2000", "2020"}  # 歩道部 / 歩道

SIMPLIFY_EPS = 0.5  # meters, ring simplification before proximity work

# 皇居東御苑 〜 東京駅 (lon_min, lat_min, lon_max, lat_max)
MARUNOUCHI_BBOX = (139.7490, 35.6770, 139.7725, 35.6900)
# local-meter projection origin (丸の内 center-ish, deterministic)
ORIGIN = (35.6825, 139.7605)

# 注意: PLATEAU道路データは皇居東側の内堀通り(139.750-139.758付近)を
# 含まないため、開始点はデータ上の西端(内堀通り・皇居東側)に置く。
# 大手門そのものは盤面側で手配置する前提。
DEFAULT_START = (35.6857, 139.7609)
DEFAULT_GOAL = (35.6815, 139.7650)  # 東京駅 丸の内駅前広場 付近

INF = float("inf")


# ---------------------------------------------------------------- geometry

def make_projector(lat0, lon0):
    kx = math.cos(math.radians(lat0)) * EARTH_R * math.pi / 180.0
    ky = EARTH_R * math.pi / 180.0

    def proj(lat, lon):
        return ((lon - lon0) * kx, (lat - lat0) * ky)

    def unproj(x, y):
        return (lat0 + y / ky, lon0 + x / kx)

    return proj, unproj


def point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - ax, py - ay), (ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy), (qx, qy)


def simplify_ring(pts, eps):
    """Douglas-Peucker on a closed ring (split at the vertex farthest from
    pts[0]); keeps the ring within ~eps of the original."""
    if len(pts) < 5:
        return pts
    k = max(range(1, len(pts)),
            key=lambda i: (pts[i][0] - pts[0][0]) ** 2
            + (pts[i][1] - pts[0][1]) ** 2)

    def dp(seg):
        if len(seg) < 3:
            return seg
        ax, ay = seg[0]
        bx, by = seg[-1]
        dmax, imax = -1.0, -1
        for i in range(1, len(seg) - 1):
            d, _ = point_seg_dist(seg[i][0], seg[i][1], ax, ay, bx, by)
            if d > dmax:
                dmax, imax = d, i
        if dmax <= eps:
            return [seg[0], seg[-1]]
        left = dp(seg[:imax + 1])
        right = dp(seg[imax:])
        return left[:-1] + right

    out = dp(pts[:k + 1])[:-1] + dp(pts[k:])[:-1]
    return out if len(out) >= 3 else pts


def poly_area_centroid(pts):
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cr = x1 * y2 - x2 * y1
        a += cr
        cx += (x1 + x2) * cr
        cy += (y1 + y2) * cr
    a *= 0.5
    if abs(a) < 1e-9:
        return 0.0, (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    return abs(a), (cx / (6 * a), cy / (6 * a))


class Poly:
    __slots__ = ("pts", "bbox", "area", "centroid", "meta")

    def __init__(self, pts, meta=None):
        self.pts = pts
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        self.area, self.centroid = poly_area_centroid(pts)
        self.meta = meta or {}


def bbox_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def polyline_length(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0],
                          pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def nearest_on_polyline(pts, p):
    """(dist_along, dist, point) of the closest point on polyline pts to p."""
    best = (0.0, INF, None)
    acc = 0.0
    for i in range(len(pts) - 1):
        d, q = point_seg_dist(p[0], p[1], pts[i][0], pts[i][1],
                              pts[i + 1][0], pts[i + 1][1])
        if d < best[1]:
            best = (acc + math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]),
                    d, q)
        acc += math.hypot(pts[i + 1][0] - pts[i][0],
                          pts[i + 1][1] - pts[i][1])
    return best


class SegGrid:
    """Bucket polygon segments into a coarse grid for proximity queries."""

    def __init__(self, polys, cell):
        self.cell = cell
        self.grid = defaultdict(list)
        for i, poly in enumerate(polys):
            pts = poly.pts
            n = len(pts)
            for k in range(n):
                ax, ay = pts[k]
                bx, by = pts[(k + 1) % n]
                gx0 = int(math.floor(min(ax, bx) / cell)) - 1
                gx1 = int(math.floor(max(ax, bx) / cell)) + 1
                gy0 = int(math.floor(min(ay, by) / cell)) - 1
                gy1 = int(math.floor(max(ay, by) / cell)) + 1
                seg = (ax, ay, bx, by)
                for gx in range(gx0, gx1 + 1):
                    for gy in range(gy0, gy1 + 1):
                        self.grid[(gx, gy)].append((i, seg))

    def near(self, x, y):
        cx = int(math.floor(x / self.cell))
        cy = int(math.floor(y / self.cell))
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.extend(self.grid.get((cx + dx, cy + dy), ()))
        return out


def touch_pairs(polys_a, polys_b, tol, grid_a=None, grid_b=None):
    """Min distance between polygon boundaries via vertex-vs-segment
    proximity (both directions). Returns {(ia, ib): (dist, pt_a, pt_b)}."""
    if grid_a is None:
        grid_a = SegGrid(polys_a, max(2.0, tol * 4))
    if grid_b is None:
        grid_b = SegGrid(polys_b, max(2.0, tol * 4))
    res = {}

    def probe(vertices, grid, self_key, flip):
        for v in vertices:
            vx, vy = v
            for j, seg in grid.near(vx, vy):
                ax, ay, bx, by = seg
                if (vx < min(ax, bx) - tol or vx > max(ax, bx) + tol
                        or vy < min(ay, by) - tol or vy > max(ay, by) + tol):
                    continue
                d, q = point_seg_dist(vx, vy, ax, ay, bx, by)
                key = (self_key, j) if not flip else (j, self_key)
                cur = res.get(key)
                if cur is None or d < cur[0]:
                    res[key] = (d, v, q) if not flip else (d, q, v)

    for i, p in enumerate(polys_a):
        probe(p.pts, grid_b, i, False)
    for j, p in enumerate(polys_b):
        probe(p.pts, grid_a, j, True)
    return {k: v for k, v in res.items() if v[0] <= tol}


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self):
        out = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return out


# ------------------------------------------------------------ CityGML input

def parse_poslist(elem, proj):
    """gml:posList -> list of (x, y) local meters (exterior ring, unclosed)."""
    if elem.text is None:
        return None
    vals = elem.text.split()
    if len(vals) < 6:
        return None
    dim = int(elem.get("srsDimension") or 3)
    if len(vals) % dim:
        return None
    f = [float(v) for v in vals]
    pts = [proj(f[i], f[i + 1]) for i in range(0, len(f), dim)]  # (lat, lon)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    pts = simplify_ring(pts, SIMPLIFY_EPS)
    return pts or None


def load_city_polys(meshes, root, proj, bbox):
    """Stream udx/tran meshes -> class-bucketed polys + counters."""
    files = []
    for m in meshes:
        files += sorted((root / "udx" / "tran").glob(f"{m}_*.gml"))
    if not files:
        sys.exit(f"error: no tran files for meshes {meshes} under {root}")

    data = {"intersection": [], "roadway": [], "sidewalk": []}
    counts = Counter()
    named_streets = set()

    # lat/lon bbox in projected meters for the road-level clip test
    if bbox is not None:
        b0 = proj(bbox[1], bbox[0])
        b1 = proj(bbox[3], bbox[2])
        clip = (min(b0[0], b1[0]), min(b0[1], b1[1]),
                max(b0[0], b1[0]), max(b0[1], b1[1]))
    else:
        clip = None

    for path in files:
        root_el = None
        for ev, el in ET.iterparse(str(path), events=("start", "end")):
            if ev == "start":
                if root_el is None:
                    root_el = el
                continue
            if el.tag != f"{{{TRAN}}}Road":
                continue
            name = el.findtext(f"{{{GML}}}name")
            road_id = el.get(GMLID, "")
            if name:
                named_streets.add(name)
            buckets = {"intersection": [], "roadway": [], "sidewalk": []}
            for ta in el.iter(f"{{{TRAN}}}TrafficArea"):
                fn = (ta.findtext(f"{{{TRAN}}}function") or "").strip()
                surf = ta.find(f"{{{TRAN}}}lod2MultiSurface")
                if surf is None:
                    surf = ta.find(f"{{{TRAN}}}lod0MultiSurface")
                if surf is None:
                    continue
                kind = ("intersection" if fn in INTERSECTION_CODES
                        else "roadway" if fn in ROADWAY_CODES
                        else "sidewalk" if fn in SIDEWALK_CODES else None)
                if kind is None:
                    counts[f"ta_other_{fn or '?'}"] += 1
                    continue
                for poly in surf.iter(f"{{{GML}}}Polygon"):
                    ext = poly.find(f"{{{GML}}}exterior/{{{GML}}}LinearRing/"
                                    f"{{{GML}}}posList")
                    pts = parse_poslist(ext, proj) if ext is not None else None
                    if pts and len(pts) >= 3:
                        buckets[kind].append(
                            Poly(pts, {"road_id": road_id, "name": name}))
            if clip is not None and not any(
                    clip[0] <= p.centroid[0] <= clip[2]
                    and clip[1] <= p.centroid[1] <= clip[3]
                    for ps in buckets.values() for p in ps):
                el.clear()
                root_el.clear()
                continue
            for kind, polys in buckets.items():
                data[kind].extend(polys)
                counts[kind] += len(polys)
            counts["roads"] += 1
            counts["ata"] += sum(1 for _ in
                                 el.iter(f"{{{TRAN}}}AuxiliaryTrafficArea"))
            el.clear()
            root_el.clear()

    counts["named_streets"] = len(named_streets)
    return data, counts


# ------------------------------------------------------------ graph build

def build_graph(data, tol, min_edge, end_frac=0.2):
    inters = data["intersection"]
    strips = data["roadway"]
    walks = data["sidewalk"]
    notes = Counter()

    grid_inter = SegGrid(inters, max(2.0, max(tol, 10.0) * 4)) if inters else None
    grid_strip = SegGrid(strips, max(2.0, tol * 4)) if strips else None
    grid_walk = SegGrid(walks, max(2.0, tol * 4)) if walks else None

    # --- 1. merge touching intersection polygons into nodes (wide tol: one
    # real intersection is often several non-touching pieces)
    tol_inter = max(tol, 10.0)
    uf_i = UnionFind()
    for i in range(len(inters)):
        uf_i.find(i)
    if inters:
        for (i, j) in touch_pairs(inters, inters, tol_inter,
                                  grid_inter, grid_inter):
            uf_i.union(i, j)
    inter_nodes = []
    poly_to_inode = {}
    for ni, grp in enumerate(sorted(uf_i.groups().values(),
                                    key=lambda g: min(g))):
        area = sum(inters[i].area for i in grp)
        if area > 0:
            pos = (sum(inters[i].centroid[0] * inters[i].area for i in grp) / area,
                   sum(inters[i].centroid[1] * inters[i].area for i in grp) / area)
        else:
            pos = inters[grp[0]].centroid
        inter_nodes.append({"pos": pos, "area": area})
        for i in grp:
            poly_to_inode[i] = ni

    # --- 2. strips: diameter-pair endpoints approximate the centerline
    strip_ends = []
    for p in strips:
        c = p.centroid
        a = max(p.pts, key=lambda q: (q[0] - c[0]) ** 2 + (q[1] - c[1]) ** 2)
        b = max((q for q in p.pts if q != a),
                key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
        strip_ends.append((a, b))

    def diam(i):
        a, b = strip_ends[i]
        return math.hypot(b[0] - a[0], b[1] - a[1])

    def end_zone(i):
        return max(6.0, end_frac * diam(i))

    events = defaultdict(list)  # strip idx -> [(t, node_key, pos, kind)]
    node_pos = {}
    node_kind = {}

    def add_event(si, t, key, pos, kind):
        L = diam(si)
        events[si].append((max(0.0, min(L, t)), key, pos, kind))
        node_pos.setdefault(key, pos)
        node_kind.setdefault(key, kind)

    # --- 3. strip <-> intersection attaches
    if strips and inters:
        for (si, ii), (d, ps, pi) in touch_pairs(strips, inters, tol,
                                                 grid_strip, grid_inter).items():
            ni = poly_to_inode.get(ii)
            if ni is None:
                continue
            a, b = strip_ends[si]
            m = ((ps[0] + pi[0]) / 2, (ps[1] + pi[1]) / 2)
            t_along, _, _ = nearest_on_polyline([a, b], m)
            if math.hypot(m[0] - a[0], m[1] - a[1]) <= end_zone(si):
                t_along = 0.0
            elif math.hypot(m[0] - b[0], m[1] - b[1]) <= end_zone(si):
                t_along = diam(si)
            add_event(si, t_along, ("inter", ni), inter_nodes[ni]["pos"],
                      "intersection")

    # --- 4. strip <-> strip touches
    if strips:
        for (si, oi), (d, ps, po) in touch_pairs(strips, strips, tol,
                                                 grid_strip, grid_strip).items():
            if si == oi:
                continue
            m = ((ps[0] + po[0]) / 2, (ps[1] + po[1]) / 2)
            a_s, b_s = strip_ends[si]
            a_o, b_o = strip_ends[oi]
            e_s = 0 if math.hypot(m[0] - a_s[0], m[1] - a_s[1]) \
                <= math.hypot(m[0] - b_s[0], m[1] - b_s[1]) else 1
            e_o = 0 if math.hypot(m[0] - a_o[0], m[1] - a_o[1]) \
                <= math.hypot(m[0] - b_o[0], m[1] - b_o[1]) else 1
            near_s = math.hypot(m[0] - (a_s, b_s)[e_s][0],
                                m[1] - (a_s, b_s)[e_s][1]) <= end_zone(si)
            near_o = math.hypot(m[0] - (a_o, b_o)[e_o][0],
                                m[1] - (a_o, b_o)[e_o][1]) <= end_zone(oi)
            if near_s and near_o:
                # end-to-end: single junction at the midpoint of the two ends
                key = ("mutual", min(si, oi), max(si, oi))
                pos = (((a_s, b_s)[e_s][0] + (a_o, b_o)[e_o][0]) / 2,
                       ((a_s, b_s)[e_s][1] + (a_o, b_o)[e_o][1]) / 2)
                add_event(si, 0.0 if e_s == 0 else diam(si), key, pos,
                          "junction")
                add_event(oi, 0.0 if e_o == 0 else diam(oi), key, pos,
                          "junction")
            elif near_s:
                # si's end touches oi's side: junction on oi's centerline
                t_o, _, q = nearest_on_polyline([a_o, b_o], m)
                key = ("branch", si, oi)
                add_event(si, 0.0 if e_s == 0 else diam(si), key, q,
                          "junction")
                add_event(oi, t_o, key, q, "junction")
            elif near_o:
                t_s, _, q = nearest_on_polyline([a_s, b_s], m)
                key = ("branch", oi, si)
                add_event(oi, 0.0 if e_o == 0 else diam(oi), key, q,
                          "junction")
                add_event(si, t_s, key, q, "junction")
            else:
                notes["parallel_touches_ignored"] += 1

    # --- 5. per strip -> node sequence + edges
    nodes = []
    node_idx = {}

    def get_node(key, pos, kind):
        if key not in node_idx:
            node_idx[key] = len(nodes)
            nodes.append({"id": len(nodes), "pos": pos, "kind": kind})
        return node_idx[key]

    edges = []
    strip_of_edge = []
    for si, p in enumerate(strips):
        a, b = strip_ends[si]
        L = diam(si)
        evs = sorted(events.get(si, ()), key=lambda e: e[0])
        eps = 1e-6
        start = next((e for e in evs if e[0] <= eps), None)
        end = next((e for e in reversed(evs) if e[0] >= L - eps), None)
        mids = [e for e in evs if eps < e[0] < L - eps]
        na = get_node(start[1], start[2], start[3]) if start \
            else get_node(("dead", si, 0), a, "dead_end")
        nb = get_node(end[1], end[2], end[3]) if end \
            else get_node(("dead", si, 1), b, "dead_end")
        if na == nb:
            notes["self_loops_dropped"] += 1
            continue
        chain_pts = [a] + [e[2] for e in mids] + [b]
        seq = [na] + [get_node(e[1], e[2], e[3]) for e in mids] + [nb]
        anchors = [nodes[na]["pos"]] + [e[2] for e in mids] \
            + [nodes[nb]["pos"]]
        for k in range(len(seq) - 1):
            pts = [anchors[k], chain_pts[k], chain_pts[k + 1], anchors[k + 1]]
            dedup = [pts[0]]
            for q in pts[1:]:
                if math.hypot(q[0] - dedup[-1][0], q[1] - dedup[-1][1]) > 0.05:
                    dedup.append(q)
            if len(dedup) < 2:
                continue
            ln = polyline_length(dedup)
            if ln < 0.1:
                notes["zero_len_edges_dropped"] += 1
                continue
            edges.append({"a": na if k == 0 else seq[k],
                          "b": nb if k == len(seq) - 2 else seq[k + 1],
                          "pts": dedup, "length": ln, "strip": si})
    for e in edges:
        p = strips[e["strip"]]
        e["name"] = p.meta.get("name")
        e["road_ids"] = [p.meta.get("road_id")]

    # --- 6. sidewalk attribution
    strip_sid_area = Counter()
    strip_sid_count = Counter()
    if strips and walks:
        for (si, wi), _ in touch_pairs(strips, walks, tol,
                                       grid_strip, grid_walk).items():
            strip_sid_area[si] += walks[wi].area
            strip_sid_count[si] += 1
    for e in edges:
        e["sidewalk_area"] = strip_sid_area.get(e["strip"], 0.0)
        e["sidewalk_polys"] = strip_sid_count.get(e["strip"], 0)

    # --- 7. merge nodes closer than 3 m (junction duplication cleanup);
    # kind priority: intersection > junction > dead_end
    merge_tol = 3.0
    uf_n = UnionFind()
    for n in nodes:
        uf_n.find(n["id"])
    cellg = defaultdict(list)
    for n in nodes:
        cellg[(int(n["pos"][0] // merge_tol),
               int(n["pos"][1] // merge_tol))].append(n["id"])
    for key, ids in cellg.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                other = cellg.get((key[0] + dx, key[1] + dy), ())
                for nid in ids:
                    for oid in other:
                        if nid == oid:
                            continue
                        p1 = nodes[nid]["pos"]
                        p2 = nodes[oid]["pos"]
                        if math.hypot(p1[0] - p2[0], p1[1] - p2[1]) <= merge_tol:
                            uf_n.union(nid, oid)
    prio = {"intersection": 0, "junction": 1, "dead_end": 2}
    final_nodes = []
    remap_id = {}
    for root, ids in sorted(uf_n.groups().items(), key=lambda kv: kv[1][0]):
        keep = min((nodes[i] for i in ids),
                   key=lambda m: prio[m["kind"]])
        nid = len(final_nodes)
        final_nodes.append({"id": nid, "pos": keep["pos"],
                            "kind": keep["kind"]})
        for i in ids:
            remap_id[i] = nid
    for e in edges:
        e["a"] = remap_id[e["a"]]
        e["b"] = remap_id[e["b"]]

    # --- 8. min-edge filter + drop nodes left isolated
    kept = []
    for e in edges:
        if e["length"] < min_edge:
            notes["short_edges_dropped"] += 1
            continue
        kept.append(e)
    edges = kept
    used = sorted({e["a"] for e in edges} | {e["b"] for e in edges})
    notes["isolated_nodes_dropped"] = len(final_nodes) - len(used)
    remap = {old: new for new, old in enumerate(used)}
    final_nodes = [final_nodes[old] for old in used]
    for n in final_nodes:
        n["id"] = remap[n["id"]]
    for e in edges:
        e["a"] = remap[e["a"]]
        e["b"] = remap[e["b"]]

    # --- 9. components + degrees
    adj = defaultdict(list)
    for e in edges:
        adj[e["a"]].append(e["b"])
        adj[e["b"]].append(e["a"])
    deg = Counter()
    for e in edges:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    comp = {}
    cid = 0
    for n in final_nodes:
        if n["id"] in comp:
            continue
        stack = [n["id"]]
        while stack:
            u = stack.pop()
            if u in comp:
                continue
            comp[u] = cid
            stack.extend(v for v in adj.get(u, ()) if v not in comp)
        cid += 1
    for n in final_nodes:
        n["degree"] = deg.get(n["id"], 0)
        n["component"] = comp[n["id"]]
    for e in edges:
        e["component"] = comp[e["a"]]

    return {"nodes": final_nodes, "edges": edges, "notes": dict(notes),
            "inter_nodes": len(inter_nodes)}


# ------------------------------------------------------------ graph analysis

def dijkstra(adj, src, dst=None):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, INF):
            continue
        if u == dst:
            break
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def path_len(adj, path):
    tot = 0.0
    for i in range(len(path) - 1):
        tot += min(w for v, w in adj[path[i]] if v == path[i + 1])
    return tot


def yen_k_shortest(adj, src, dst, k):
    """Yen's algorithm on simple node paths (parallel edges collapse to the
    cheapest one per node pair when counting spur costs)."""
    dist, prev = dijkstra(adj, src, dst)
    if dst not in dist:
        return []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    A = [(list(reversed(path)), dist[dst])]
    B = []

    def seen(p):
        return any(p == a for a, _ in A) or any(p == c for _, c in B)

    for _ in range(1, k):
        root_path = A[-1][0]
        for i in range(len(root_path) - 1):
            spur = root_path[i]
            root = root_path[:i + 1]
            adj2 = {u: list(vs) for u, vs in adj.items()}
            for p in [a for a, _ in A] + [c for _, c in B]:
                if len(p) > i + 1 and p[:i + 1] == root:
                    adj2[p[i]] = [e for e in adj2.get(p[i], ())
                                  if e[0] != p[i + 1]]
            for u in root[:-1]:
                adj2[u] = []
            d2, prev2 = dijkstra(adj2, spur, dst)
            if dst in d2:
                sp = [dst]
                while sp[-1] != spur:
                    sp.append(prev2[sp[-1]])
                sp.reverse()
                cand = root[:-1] + sp
                if not seen(cand):
                    heapq.heappush(B, (path_len(adj, root) + d2[dst], cand))
        if not B:
            break
        while B:
            cost, cand = heapq.heappop(B)
            if not any(cand == a for a, _ in A):
                A.append((cand, cost))
                break
        else:
            break
    return A


def snap_node(nodes, xy, max_dist=300.0):
    """Nearest node, preferring intersections (dead ends are often clip
    artifacts at the bbox edge)."""
    best, bd = None, INF
    best_i, bd_i = None, INF
    for n in nodes:
        d = math.hypot(n["pos"][0] - xy[0], n["pos"][1] - xy[1])
        if d < bd:
            best, bd = n, d
        if n["kind"] == "intersection" and d < bd_i:
            best_i, bd_i = n, d
    pick, pd = (best_i, bd_i) if best_i is not None else (best, bd)
    if pick is None or pd > max_dist:
        return None, (pd if pick is not None else INF)
    return pick, pd


# ------------------------------------------------------------ output

def to_geojson(nodes, edges, unproj, meta):
    feats = []
    for n in nodes:
        lat, lon = unproj(*n["pos"])
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(lon, 8), round(lat, 8)]},
            "properties": {k: n[k] for k in
                           ("id", "kind", "degree", "component")}})
    for i, e in enumerate(edges):
        coords = []
        for p in e["pts"]:
            lat, lon = unproj(*p)
            coords.append([round(lon, 8), round(lat, 8)])
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "id": f"e{i}", "from": e["a"], "to": e["b"],
                "length_m": round(e["length"], 1),
                "street_name": e.get("name"),
                "sidewalk_area_m2": round(e.get("sidewalk_area", 0.0), 1),
                "sidewalk_polys": e.get("sidewalk_polys", 0),
                "walkable": True,
                "component": e["component"],
                "road_gml_ids": e["road_ids"][:3]}})
    return {"type": "FeatureCollection", "features": feats,
            "metadata": meta}


SVG_COLORS = {
    "bg": "#eef0e9",
    "sidewalk": "#e9e2cf",
    "road": "#565360",
    "edge": "#ffc72e",
    "edge_alt": "#8a8494",
    "node": "#2e2b36",
    "dead": "#6d6878",
    "start": "#2f9e44",
    "goal": "#d9480f",
    "path": ["#e8590c", "#1971c2", "#2f9e44", "#9c36b5", "#f08c00"],
}


def render_svg(nodes, edges, polys_by_kind, out_path, stats_line, paths=None,
               start=None, goal=None):
    all_polys = (polys_by_kind["sidewalk"] + polys_by_kind["roadway"]
                 + polys_by_kind["intersection"])
    xs = [p[0] for poly in all_polys for p in poly.pts]
    ys = [p[1] for poly in all_polys for p in poly.pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    margin = 50
    W, H = x1 - x0, y1 - y0
    scale = min(2200.0 / W, 1300.0 / H, 1.0)
    CW = int(W * scale + 2 * margin)
    CH = int(H * scale + 2 * margin + 30)

    def tx(p):
        return (margin + (p[0] - x0) * scale,
                CH - margin - 30 - (p[1] - y0) * scale)

    def path_d(pts):
        d = [f"M{tx(pts[0])[0]:.1f} {tx(pts[0])[1]:.1f}"]
        for q in pts[1:]:
            x, y = tx(q)
            d.append(f"L{x:.1f} {y:.1f}")
        return " ".join(d)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}"'
         f' viewBox="0 0 {CW} {CH}" font-family="\'Hiragino Kaku Gothic ProN\','
         f'sans-serif">',
         f'<rect width="{CW}" height="{CH}" fill="{SVG_COLORS["bg"]}"/>']

    # backdrop: sidewalks under roadways (intersections drawn as roadway)
    for kind, fill in (("sidewalk", SVG_COLORS["sidewalk"]),
                       ("roadway", SVG_COLORS["road"]),
                       ("intersection", SVG_COLORS["road"])):
        for poly in polys_by_kind[kind]:
            o.append(f'<path d="{path_d(poly.pts)}Z" fill="{fill}"/>')

    # edges: main component solid yellow, others dashed gray
    main = Counter(e["component"] for e in edges).most_common(1)
    main = main[0][0] if main else -1
    for e in edges:
        if e["component"] == main:
            o.append(f'<path d="{path_d(e["pts"])}" fill="none" '
                     f'stroke="{SVG_COLORS["edge"]}" stroke-width="4" '
                     f'stroke-linecap="round"/>')
        else:
            o.append(f'<path d="{path_d(e["pts"])}" fill="none" '
                     f'stroke="{SVG_COLORS["edge_alt"]}" stroke-width="3" '
                     f'stroke-dasharray="8 6"/>')

    # demo paths as node-to-node polylines
    by_id = {n["id"]: n["pos"] for n in nodes}
    for pi, (p, _cost) in enumerate(paths or []):
        pts = [by_id[nid] for nid in p]
        col = SVG_COLORS["path"][pi % len(SVG_COLORS["path"])]
        o.append(f'<path d="{path_d(pts)}" fill="none" stroke="{col}" '
                 f'stroke-width="3" opacity="0.95"/>')

    # nodes
    for n in nodes:
        x, y = tx(n["pos"])
        if n["kind"] == "dead_end":
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="none" '
                     f'stroke="{SVG_COLORS["dead"]}" stroke-width="1.5"/>')
        else:
            r = 5 if n["kind"] == "intersection" else 3.5
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" '
                     f'fill="{SVG_COLORS["node"]}"/>')

    for pt, col, label in ((start, SVG_COLORS["start"], "開始"),
                           (goal, SVG_COLORS["goal"], "駅")):
        if pt:
            x, y = tx(pt)
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="none" '
                     f'stroke="{col}" stroke-width="3"/>')
            o.append(f'<text x="{x + 13:.1f}" y="{y + 7:.1f}" font-size="20" '
                     f'fill="{col}" font-weight="bold">{label}</text>')

    o.append(f'<text x="{margin}" y="34" font-size="24" font-weight="bold" '
             f'fill="{SVG_COLORS["node"]}">丸の内回廊 歩行グラフ'
             f'（CityGML 生成）</text>')
    o.append(f'<text x="{margin}" y="58" font-size="15" fill="#5a5666">'
             f'{stats_line}</text>')
    lx, ly = margin, CH - 16
    legend = [("rect", SVG_COLORS["road"], "車道部"),
              ("rect", SVG_COLORS["sidewalk"], "歩道部"),
              ("circle", SVG_COLORS["node"], "交差点ノード"),
              ("line", SVG_COLORS["edge"], "主グラフ辺"),
              ("line", SVG_COLORS["edge_alt"], "他の連結成分")]
    for kind, col, label in legend:
        if kind == "rect":
            o.append(f'<rect x="{lx}" y="{ly - 12}" width="18" height="12" '
                     f'fill="{col}"/>')
        elif kind == "circle":
            o.append(f'<circle cx="{lx + 9}" cy="{ly - 6}" r="5" '
                     f'fill="{col}"/>')
        else:
            o.append(f'<line x1="{lx}" y1="{ly - 6}" x2="{lx + 18}" '
                     f'y2="{ly - 6}" stroke="{col}" stroke-width="4"/>')
        o.append(f'<text x="{lx + 24}" y="{ly - 2}" font-size="14" '
                 f'fill="{SVG_COLORS["node"]}">{label}</text>')
        lx += 24 + len(label) * 14 + 18
    bar_x0 = CW - margin - 100 * scale - 60
    bar_y = ly - 6
    o.append(f'<text x="{bar_x0 + 100 * scale + 8}" y="{bar_y + 4}" '
             f'font-size="13" fill="{SVG_COLORS["node"]}">100 m</text>')
    o.append(f'<line x1="{bar_x0}" y1="{bar_y}" x2="{bar_x0 + 100 * scale}" '
             f'y2="{bar_y}" stroke="{SVG_COLORS["node"]}" stroke-width="2"/>')
    o.append("</svg>")
    out_path.write_text("\n".join(o), encoding="utf-8")
    return CW, CH


def svg_to_png(svg_path, png_path, w, h):
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    chrome = next((c for c in candidates if c and Path(c).exists()), None)
    if chrome is None:
        return False
    r = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--screenshot={png_path}", f"--window-size={w},{h}",
         svg_path.resolve().as_uri()],
        capture_output=True, timeout=180)
    return r.returncode == 0 and Path(png_path).exists()


# ------------------------------------------------------------ selftest

def _poly_rect(x0, y0, x1, y1):
    return Poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def selftest():
    # I: start intersection; J: goal intersection; I2a+I2b: merged pair;
    # A,B: street I->J via mutual junction; D: dead-end street; F: tiny
    data = {
        "intersection": [_poly_rect(0, 0, 10, 10),
                         _poly_rect(0, 21, 10, 31),
                         _poly_rect(10, 21, 20, 31),
                         _poly_rect(48, 0, 58, 10)],
        "roadway": [_poly_rect(10, 4, 30, 6),
                    _poly_rect(30, 4, 48, 6),
                    _poly_rect(60, 4, 70, 6),
                    _poly_rect(70, 30, 72, 32)],
        "sidewalk": [_poly_rect(10, 6, 30, 8)],
    }
    g = build_graph(data, tol=1.0, min_edge=3.0)

    kinds = Counter(n["kind"] for n in g["nodes"])
    assert kinds["intersection"] == 2, kinds   # I and merged I2 pair
    assert kinds["junction"] == 1, kinds       # A-B mutual midpoint
    assert kinds["dead_end"] == 2, kinds       # street D's two ends
    assert len(g["edges"]) == 3, g["edges"]
    comps = Counter(n["component"] for n in g["nodes"])
    assert sorted(comps.values()) == [2, 3], comps  # I-J street + dead end

    def near_kind(kind, x, y):
        return min((n for n in g["nodes"] if n["kind"] == kind),
                   key=lambda n: math.hypot(n["pos"][0] - x,
                                            n["pos"][1] - y))["id"]

    src = near_kind("intersection", 5, 5)      # I
    dst = near_kind("intersection", 53, 5)     # J
    adj = defaultdict(list)
    for e in g["edges"]:
        adj[e["a"]].append((e["b"], e["length"]))
        adj[e["b"]].append((e["a"], e["length"]))
    dist, _ = dijkstra(adj, src, dst)
    assert 45.0 < dist[dst] < 55.0, dist[dst]  # expected ~49.3 m

    e_im = min(g["edges"], key=lambda e: abs(e["length"] - 25.0))
    assert e_im["sidewalk_area"] > 0, e_im     # sidewalk attributed to A

    paths = yen_k_shortest(adj, src, dst, 3)
    assert len(paths) == 1, paths              # only one route exists

    print(f"selftest OK (nodes={len(g['nodes'])} edges={len(g['edges'])} "
          f"I->J={dist[dst]:.1f}m)")
    return True


# ------------------------------------------------------------ main

def parse_latlon(s):
    la, lo = (float(v) for v in s.split(","))
    return la, lo


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meshes", nargs="*", help="3rd-mesh codes, e.g. 53394611")
    ap.add_argument("--root", default="vendor/citygml")
    ap.add_argument("--out", default="artifacts/city_graph")
    ap.add_argument("--bbox", default=None,
                    help="'marunouchi' preset or lon0,lat0,lon1,lat1")
    ap.add_argument("--tol", type=float, default=1.0,
                    help="street-level touch tolerance in meters")
    ap.add_argument("--min-edge", type=float, default=3.0)
    ap.add_argument("--end-frac", type=float, default=0.2)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--start", default=f"{DEFAULT_START[0]},{DEFAULT_START[1]}",
                    help="lat,lon of the walk origin (default 皇居大手門)")
    ap.add_argument("--goal", default=f"{DEFAULT_GOAL[0]},{DEFAULT_GOAL[1]}",
                    help="lat,lon of the goal (default 東京駅丸の内駅前)")
    ap.add_argument("--snap", type=float, default=300.0)
    ap.add_argument("--no-svg", action="store_true")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if not args.meshes:
        ap.error("provide mesh codes or --selftest")

    if args.bbox == "marunouchi":
        bbox = MARUNOUCHI_BBOX
    elif args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split(","))
    else:
        bbox = None

    proj, unproj = make_projector(*ORIGIN)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"parsing {len(args.meshes)} meshes ...")
    data, counts = load_city_polys(args.meshes, Path(args.root), proj, bbox)
    print(f"  roads={counts['roads']} 交差部={counts['intersection']} "
          f"車道部={counts['roadway']} 歩道部={counts['sidewalk']} "
          f"ATA={counts['ata']}")
    if counts["roads"] == 0:
        print("  !! no roads kept — check --bbox / mesh codes")

    print("building graph ...")
    g = build_graph(data, tol=args.tol, min_edge=args.min_edge,
                    end_frac=args.end_frac)
    nodes, edges = g["nodes"], g["edges"]
    total_len = sum(e["length"] for e in edges)
    deg_hist = Counter(n["degree"] for n in nodes)
    comps = Counter(n["component"] for n in nodes)

    # --- corridor demo: 開始 -> 駅, k shortest paths
    start_ll, goal_ll = parse_latlon(args.start), parse_latlon(args.goal)
    sn, sd = snap_node(nodes, proj(*start_ll), args.snap)
    gn, gd = snap_node(nodes, proj(*goal_ll), args.snap)
    paths, demo = [], None
    if sn and gn:
        adj = defaultdict(list)
        for e in edges:
            adj[e["a"]].append((e["b"], e["length"]))
            adj[e["b"]].append((e["a"], e["length"]))
        paths = yen_k_shortest(adj, sn["id"], gn["id"], args.k)
        demo = {"start_latlon": start_ll, "goal_latlon": goal_ll,
                "start_snap_m": round(sd, 1), "goal_snap_m": round(gd, 1),
                "paths": [{"rank": i + 1, "length_m": round(c, 1),
                           "nodes": len(p),
                           "streets": _street_names(edges, p)}
                          for i, (p, c) in enumerate(paths)]}
    else:
        print(f"  !! start/goal snap failed (start {sd:.0f} m, "
              f"goal {gd:.0f} m from nearest node)")

    # --- outputs
    meta = {
        "generated": date.today().isoformat(),
        "generator": "tools/gen_city_graph.py v1",
        "source": "PLATEAU 千代田区 2025 CityGML (EPSG::6697, treated as WGS84)",
        "meshes": args.meshes,
        "bbox_lonlat": bbox,
        "params": {"tol_m": args.tol, "min_edge_m": args.min_edge,
                   "end_frac": args.end_frac, "origin_latlon": ORIGIN},
    }
    (out / "graph.geojson").write_text(
        json.dumps(to_geojson(nodes, edges, unproj, meta),
                   ensure_ascii=False), encoding="utf-8")

    stats = {
        "params": meta["params"], "meshes": args.meshes,
        "bbox_lonlat": bbox, "inputs": dict(counts),
        "construction_notes": g["notes"],
        "intersections_merged": g["inter_nodes"],
        "graph": {
            "nodes": len(nodes),
            "node_kinds": dict(Counter(n["kind"] for n in nodes)),
            "edges": len(edges),
            "total_length_km": round(total_len / 1000, 2),
            "degree_histogram": {str(k): v
                                 for k, v in sorted(deg_hist.items())},
            "components": {str(k): v for k, v in
                           sorted(comps.items(), key=lambda kv: -kv[1])[:10]},
            "longest_named_edges": _top_named(edges),
        },
        "corridor_demo": demo,
    }
    (out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    if not args.no_svg:
        line = (f"nodes {len(nodes)} / edges {len(edges)} / "
                f"{total_len / 1000:.1f} km / 連結成分 {len(comps)}")
        if paths:
            line += f" / 開始→駅 最短 {paths[0][1] / 1000:.2f} km"
        svg = out / "city-graph.svg"
        w, h = render_svg(nodes, edges, data, svg, line, paths=paths,
                          start=sn["pos"] if sn else None,
                          goal=gn["pos"] if gn else None)
        print(f"  svg: {svg} ({w}x{h})")
        if not args.no_png:
            png = out / "city-graph.png"
            if svg_to_png(svg, png, w, h):
                print(f"  png: {png}")
            else:
                print("  png: skipped (no headless Chrome found)")

    # --- console summary
    print(f"\ngraph: {len(nodes)} nodes / {len(edges)} edges / "
          f"{total_len / 1000:.1f} km")
    print(f"  kinds: {dict(Counter(n['kind'] for n in nodes))}")
    print(f"  degree: {dict(sorted(deg_hist.items()))}")
    print(f"  notes: {g['notes']}")
    if demo:
        for p in demo["paths"]:
            print(f"  path {p['rank']}: {p['length_m'] / 1000:.2f} km, "
                  f"{p['nodes']} nodes, {', '.join(p['streets'][:8])}")
    print(f"\nwrote {out}/(graph.geojson|stats.json|city-graph.svg)")


def _street_names(edges, node_path):
    by_pair = defaultdict(list)
    for e in edges:
        by_pair[(e["a"], e["b"])].append(e)
        by_pair[(e["b"], e["a"])].append(e)
    names = []
    for a, b in zip(node_path[:-1], node_path[1:]):
        es = by_pair.get((a, b)) or by_pair.get((b, a)) or []
        names.append(next((e["name"] for e in es if e.get("name")),
                          "無名区間"))
    return names


def _top_named(edges, n=10):
    named = sorted((e for e in edges if e.get("name")),
                   key=lambda e: -e["length"])[:n]
    return [{"name": e["name"], "length_m": round(e["length"])}
            for e in named]


if __name__ == "__main__":
    main()
