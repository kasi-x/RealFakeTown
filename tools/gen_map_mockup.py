#!/usr/bin/env python3
"""リアルフェイクタウン 概念マップ生成スクリプト
Traffic Escape 風の俯瞰パズルボード。出力: docs/concepts/map-mockup.svg
レンダリング: Chrome headless で PNG 化する。
"""
import math
import random

random.seed(7)

W, H = 1536, 2048
FONT = "'Hiragino Maru Gothic ProN','Hiragino Kaku Gothic ProN','Hiragino Sans',sans-serif"
INK = "#2e2b36"
GRASS = "#7fc85c"
GRASS_D = "#66b048"
SIDE = "#e9e2cf"
SIDE_D = "#d8d0ba"
ROAD = "#565360"
DASH = "#f2f0e9"
YEL = "#ffc72e"
SKIN = "#f6d3ae"
GLASS = "#a8cbe8"
OUT = []

def add(s):
    OUT.append(s)

def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")

def rect(x, y, w, h, fill, rx=0, stroke=None, sw=0, opacity=None, rot=None,
         cx=None, cy=None, extra=""):
    s = ""
    if rot is not None:
        gx = cx if cx is not None else x + w / 2
        gy = cy if cy is not None else y + h / 2
        s += f'<g transform="rotate({f(rot)} {f(gx)} {f(gy)})">'
    s += f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(rx)}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{f(sw)}"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    if extra:
        s += f" {extra}"
    s += "/>"
    if rot is not None:
        s += "</g>"
    add(s)

def circ(cx, cy, r, fill, stroke=None, sw=0, opacity=None, extra=""):
    s = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{f(sw)}"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    if extra:
        s += f" {extra}"
    add(s + "/>")

def ell(cx, cy, rx, ry, fill, stroke=None, sw=0, opacity=None, rot=None):
    s = f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(ry)}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{f(sw)}"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    if rot is not None:
        s += f' transform="rotate({f(rot)} {f(cx)} {f(cy)})"'
    add(s + "/>")

def line(x1, y1, x2, y2, stroke, sw, opacity=None, dash=None, cap="round"):
    s = f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" stroke="{stroke}" stroke-width="{f(sw)}" stroke-linecap="{cap}"'
    if dash:
        s += f' stroke-dasharray="{dash}"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    add(s + "/>")

def path(d, fill="none", stroke=None, sw=0, opacity=None, dash=None, cap="round"):
    s = f'<path d="{d}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{f(sw)}" stroke-linecap="{cap}" stroke-linejoin="round"'
    if dash:
        s += f' stroke-dasharray="{dash}"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    add(s + "/>")

def poly(pts, fill, stroke=None, sw=0, opacity=None, rot=None, cx=0, cy=0):
    p = " ".join(f"{f(x)},{f(y)}" for x, y in pts)
    s = f'<polygon points="{p}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    if opacity is not None:
        s += f' opacity="{opacity}"'
    if rot is not None:
        s += f' transform="rotate({f(rot)} {f(cx)} {f(cy)})"'
    add(s + "/>")

def text(x, y, s, size=20, fill=INK, anchor="middle", weight="bold",
         rot=None, stroke=None, sw=0, opacity=None, spacing=None):
    t = f'<text x="{f(x)}" y="{f(y)}" font-family="{FONT}" font-size="{f(size)}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"'
    if stroke:
        t += f' stroke="{stroke}" stroke-width="{f(sw)}" paint-order="stroke" stroke-linejoin="round"'
    if rot is not None:
        t += f' transform="rotate({f(rot)} {f(x)} {f(y)})"'
    if opacity is not None:
        t += f' opacity="{opacity}"'
    if spacing:
        t += f' letter-spacing="{spacing}"'
    add(t + f">{s}</text>")

# ---------- 街の部品 ----------

def tree(x, y, r=18):
    circ(x + 4, y + 6, r, "#000000", opacity=0.14)
    circ(x, y, r, "#3f8f3f", stroke=INK, sw=3)
    circ(x - r * 0.3, y - r * 0.3, r * 0.55, "#5cab50")

def shadow_box(x, y, w, h, rx=0):
    rect(x + 7, y + 13, w, h, "#000000", rx=rx, opacity=0.15)

def house(x, y, w, h, rot=0, roof="#f2a93b", wall="#f8eed6"):
    shadow_box(x, y, w, h, 8)
    rect(x, y, w, h, wall, rx=8, stroke=INK, sw=4, rot=rot)
    rect(x + 9, y + 9, w - 18, h - 18, roof, rx=5, stroke=INK, sw=3, rot=rot)
    # 棟線
    if rot is None:
        line(x + 9, y + h / 2, x + w - 9, y + h / 2, "#ffffff", 3, opacity=0.45)

def shop(x, y, w, h, rot=0, wall="#f7eed6", awn="#d96a5a"):
    shadow_box(x, y, w, h, 8)
    rect(x, y, w, h, wall, rx=8, stroke=INK, sw=4, rot=rot)
    # 南側のひさし（看板兼）
    n = max(3, int(w // 26))
    sw_ = w / n
    for i in range(n):
        c = awn if i % 2 == 0 else "#ffffff"
        rect(x + i * sw_, y + h - 4, sw_, 22, c, stroke=INK, sw=2.5, rot=rot)

def office_box(x, y, w, h):
    shadow_box(x, y, w, h, 8)
    rect(x, y, w, h, "#9db3c8", rx=8, stroke=INK, sw=4)
    cols, rows = max(2, int(w // 44)), max(2, int(h // 40))
    for i in range(cols):
        for j in range(rows):
            rect(x + 12 + i * (w - 20) / cols + 4, y + 12 + j * (h - 20) / rows + 3,
                 (w - 20) / cols - 12, (h - 20) / rows - 12, "#3a4353", rx=3)

def flat(x, y, w, h, base="#e9e4d4"):
    shadow_box(x, y, w, h, 10)
    rect(x, y, w, h, base, rx=10, stroke=INK, sw=4)
    yy = y + 16
    while yy < y + h - 10:
        line(x + 12, yy, x + w - 12, yy, "#ffffff", 4, opacity=0.5)
        yy += 18
    for i in range(int(w // 60)):
        rect(x + 22 + i * 60, y + h / 2 - 6, 22, 14, "#b9b2a0", rx=3, stroke=INK, sw=2)

def ac_units(x, y, w, h):
    for i in range(3):
        rect(x + 14 + i * (w / 3), y + h - 22, 20, 14, "#b9b2a0", rx=3, stroke=INK, sw=2)

def bent_tower(cx, top_y):
    """前傾に曲がった変形高層ビル"""
    boxes = [(cx - 52, top_y + 190, 104, 100, 0), (cx - 44, top_y + 96, 92, 96, 10),
             (cx - 36, top_y, 82, 92, 22)]
    for i, (x, y, w, h, r) in enumerate(boxes):
        rect(x + 6, y + 12, w, h, "#000000", rx=12, opacity=0.14, rot=r)
        rect(x, y, w, h, GLASS, rx=12, stroke=INK, sw=4, rot=r)
        for j in range(1, 5):
            line(x + 8, y + j * h / 5, x + w - 8, y + j * h / 5, "#ffffff", 3,
                 opacity=0.65)
    # アンテナ
    line(cx + 12, top_y + 6, cx + 12, top_y - 26, INK, 4)
    circ(cx + 12, top_y - 30, 5, "#e0473c", stroke=INK, sw=2.5)

def coffee_cup(cx, cy):
    # 受皿・本体・取っ手・湯気
    ell(cx + 6, cy + 44, 48, 13, "#ffffff", stroke=INK, sw=3.5)
    circ(cx + 6, cy + 44, 30, "#000000", opacity=0.10)
    rect(cx - 36, cy - 20, 78, 62, rx=14, fill="#ffffff", stroke=INK, sw=4)
    rect(cx - 36, cy + 2, 78, 14, "#d94f43", stroke=INK, sw=2.5)
    # 取っ手
    circ(cx + 44, cy + 10, 15, fill="none", stroke="#ffffff", sw=11)
    circ(cx + 44, cy + 10, 20, fill="none", stroke=INK, sw=3)
    # 湯気
    for dx in (-14, 12):
        path(f"M {cx+dx} {cy-26} q -8 -12 0 -24 q 8 -12 0 -22", stroke="#ffffff", sw=6, opacity=0.9)
        path(f"M {cx+dx} {cy-26} q -8 -12 0 -24 q 8 -12 0 -22", stroke=INK, sw=1.5, opacity=0.35)

def donut(cx, cy, r=52):
    circ(cx + 5, cy + 10, r, "#000000", opacity=0.16)
    circ(cx, cy, r, "#f2a0b5", stroke=INK, sw=4)
    circ(cx, cy, r, fill="none", stroke="#ffffff", sw=7, opacity=0.5, extra='stroke-dasharray="40 60"')
    circ(cx, cy, r * 0.34, "#e8dcc4", stroke=INK, sw=4)
    cols = ["#ffffff", "#5ac8fa", "#ffd60a", "#ff9f0a", "#7ed957"]
    for i in range(12):
        a = i * math.pi / 6 + 0.3
        rr = r * (0.55 + 0.25 * ((i * 7) % 3) / 2)
        sx, sy = cx + rr * math.cos(a), cy + rr * math.sin(a)
        rect(sx - 4, sy - 1.5, 9, 3.5, cols[i % 5], rx=1.5, rot=random.uniform(0, 180), cx=sx, cy=sy)

def sign_board(x, y, ang=0):
    g = f'<g transform="rotate({f(ang)} {f(x)} {f(y)})">'
    add(g)
    rect(x - 3, y + 12, 6, 22, "#8a7a5f", stroke=INK, sw=2.5)
    rect(x + 6, y + 12, 6, 22, "#8a7a5f", stroke=INK, sw=2.5)
    rect(x - 26, y - 22, 58, 42, "#ffffff", rx=6, stroke=INK, sw=4)
    # ミニマップ
    rect(x - 19, y - 15, 44, 30, "#cfe6c2", rx=3)
    rect(x - 12, y - 15, 6, 30, ROAD)
    rect(x - 19, y - 2, 44, 6, ROAD)
    rect(x + 8, y - 12, 12, 10, "#f2a93b")
    circ(x + 14, y + 6, 3.5, "#d94f43")
    rect(x - 26, y - 28, 58, 9, "#4f7fd9", rx=3, stroke=INK, sw=2.5)
    add("</g>")

def konbini(x, y, w=120, h=112):
    shadow_box(x, y, w, h, 8)
    rect(x, y, w, h, "#f7eed6", rx=8, stroke=INK, sw=4)
    rect(x, y, w, 24, "#0aa14e", rx=8, stroke=INK, sw=3.5)
    rect(x + 14, y + 30, w - 28, 30, "#cfe8f5", rx=4, stroke=INK, sw=2.5)
    n = max(3, int(w // 26))
    sw_ = w / n
    for i in range(n):
        c = "#0aa14e" if i % 2 == 0 else "#ffffff"
        rect(x + i * sw_, y + h - 4, sw_, 22, c, stroke=INK, sw=2.5)
    # おにぎり（回復アイコン）
    tx, ty = x + w / 2, y + h + 20
    circ(tx + 3, ty + 5, 16, "#000000", opacity=0.14)
    poly([(tx - 15, ty + 8), (tx, ty - 14), (tx + 15, ty + 8)], "#ffffff", stroke=INK, sw=3.5, opacity=None)
    rect(tx - 6, ty + 1, 12, 10, "#2e4a2e", rx=2)

def police_box(x, y):
    shadow_box(x, y, 86, 64, 8)
    rect(x, y, 86, 64, "#f7eed6", rx=8, stroke=INK, sw=4)
    rect(x, y, 86, 20, "#3d5a80", rx=8, stroke=INK, sw=3)
    line(x + 70, y + 78, x + 70, y + 96, INK, 4)
    circ(x + 70, y + 84, 7, "#e0473c", stroke=INK, sw=2.5)

def school(x, y, w=134, h=130):
    shadow_box(x, y, w, h, 8)
    rect(x, y, w, h, "#f6efdb", rx=8, stroke=INK, sw=4)
    rect(x + 8, y + 8, w - 16, 18, "#e4643b", stroke=INK, sw=2.5)
    for i in range(4):
        rect(x + 14 + i * (w - 28) / 4, y + 40, 18, 30, "#cfe8f5", rx=3, stroke=INK, sw=2)
    line(x - 14, y + h + 26, x - 14, y + h - 6, INK, 4)
    poly([(x - 14, y + h - 6), (x + 16, y + h + 1), (x - 14, y + h + 8)], "#e0473c", stroke=INK, sw=2)

def shrine(x, y):
    ell(x + 55, y + 60, 75, 95, "#dfe8c8", opacity=0.9)
    tree(x + 8, y + 12, 22)
    tree(x + 108, y + 20, 20)
    shadow_box(x + 18, y + 78, 110, 76, 8)
    rect(x + 18, y + 78, 110, 76, "#f7eed6", rx=8, stroke=INK, sw=4)
    rect(x + 18, y + 78, 110, 22, "#6b5340", rx=8, stroke=INK, sw=3)
    # 鳥居
    tx, ty = x + 55, y + 176
    rect(tx - 30, ty - 6, 9, 44, "#d94f43", stroke=INK, sw=3)
    rect(tx + 21, ty - 6, 9, 44, "#d94f43", stroke=INK, sw=3)
    rect(tx - 38, ty - 14, 76, 9, "#d94f43", rx=4, stroke=INK, sw=3)
    rect(tx - 30, ty + 2, 60, 6, "#d94f43", rx=3, stroke=INK, sw=2.5)

def station():
    # 駅舎
    shadow_box(820, 1760, 520, 98, 14)
    rect(820, 1760, 520, 98, "#f4f1e6", rx=14, stroke=INK, sw=4.5)
    rect(820, 1760, 520, 26, "#4f7fd9", rx=14, stroke=INK, sw=3.5)
    text(1060, 1828, "えき STATION", size=32, fill=INK)
    circ(1288, 1808, 16, "#ffffff", stroke=INK, sw=3.5)
    line(1288, 1808, 1288, 1797, INK, 2.5)
    line(1288, 1808, 1296, 1812, INK, 2.5)
    # 改札
    for i in range(3):
        gx = 1050 + i * 44
        rect(gx, 1700, 36, 20, INK, rx=5)
        circ(gx + 18, 1710, 4, "#7ed957")
    # 路線・電車
    rect(48, 1878, 1440, 74, "#4b4854")
    xx = 62
    while xx < 1478:
        rect(xx, 1886, 12, 58, "#5d5a68")
        xx += 26
    rect(48, 1902, 1440, 7, "#9a97a6")
    rect(48, 1930, 1440, 7, "#9a97a6")
    # 電車
    rect(650, 1892, 400, 56, "#000000", rx=26, opacity=0.2)
    rect(640, 1886, 400, 58, "#f4f6f9", rx=24, stroke=INK, sw=4.5)
    rect(640, 1886, 40, 58, "#4f7fd9", rx=24, stroke=INK, sw=4)
    for i in range(5):
        rect(706 + i * 58, 1902, 38, 24, "#5b87c9", rx=6, stroke=INK, sw=2)

# ---------- キャラ ----------

def person(x, y, ang, top, hair, hat=None, glasses=False, cane=False,
           long_hair=False, cap_color=None, skirt=None, blush=False, buff=False):
    add(f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)}) scale(1.6)">')
    ell(0, 18, 13, 5.5, "#000000", opacity=0.16)
    if buff:
        rect(-13, -3, 26, 24, top, rx=10, stroke=INK, sw=2.5)
        line(-13, 8, 13, 8, "#ffffff", 2.5, opacity=0.5)
    else:
        rect(-10, -2, 20, 21, top, rx=8, stroke=INK, sw=2.5)
    if skirt:
        rect(-10, 9, 20, 10, skirt, rx=5, stroke=INK, sw=2)
    if long_hair:
        circ(0, -11, 12.5, hair, stroke=INK, sw=2.5)
    # 顔
    circ(0, -11, 9.5, SKIN, stroke=INK, sw=2.5)
    path("M -9.5 -11 A 9.5 9.5 0 0 1 9.5 -11 Z", fill=hair, stroke=INK, sw=2.5)
    circ(-3.4, -7.5, 1.5, INK)
    circ(3.4, -7.5, 1.5, INK)
    if blush:
        circ(-6, -4.5, 2, "#f2a0b5")
        circ(6, -4.5, 2, "#f2a0b5")
    if glasses:
        rect(-7, -10.5, 14, 4.5, INK, rx=2)
    if hat:
        circ(0, -16, 8.6, hat, stroke=INK, sw=2.5)
        ell(0, -10.5, 8.6, 3.4, hat, stroke=INK, sw=2)
    if cap_color:
        circ(0, -17, 8, cap_color, stroke=INK, sw=2.5)
        ell(0, -11, 8.4, 3.2, cap_color, stroke=INK, sw=2)
        circ(0, -20, 2, "#ffd60a")
    if cane:
        line(9, 6, 17, 26, "#f2efe4", 3.5)
        circ(17, 27, 2.5, "#f2efe4")
    add("</g>")

def dog(x, y, ang, color="#e6b54c", harness=False):
    add(f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)}) scale(1.5)">')
    ell(0, 12, 15, 5, "#000000", opacity=0.16)
    path("M -14 -2 q -9 -7 -4 -14", stroke=color, sw=6, cap="round")
    ell(0, 0, 14, 9, color, stroke=INK, sw=2.5)
    circ(13, -5, 7.5, color, stroke=INK, sw=2.5)
    circ(10, -11, 3.2, "#8a6a3a", stroke=INK, sw=1.5)
    circ(18, -4, 1.6, INK)
    if harness:
        line(-7, -5, 7, -5, "#3d5a80", 4)
        path("M -4 -5 q 4 -9 8 0", stroke="#3d5a80", sw=3.5)
    add("</g>")

def cat(x, y, ang=0, color="#9aa0a8"):
    add(f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)}) scale(1.5)">')
    ell(0, 9, 11, 4, "#000000", opacity=0.16)
    path("M -10 0 q -8 -8 -2 -13", stroke=color, sw=4.5, cap="round")
    ell(0, 0, 10, 6.5, color, stroke=INK, sw=2.5)
    circ(9, -3, 5.5, color, stroke=INK, sw=2.5)
    poly([(5, -7), (6, -13), (10, -8)], color, stroke=INK, sw=2)
    poly([(12, -8), (14, -13), (16, -7)], color, stroke=INK, sw=2)
    add("</g>")

def taxi(x, y, ang, color="#ffd23f"):
    add(f'<g transform="rotate({f(ang)} {f(x)} {f(y)})">')
    for wx in (-28, 16):
        for wy in (-23, 16):
            rect(x + wx, y + wy, 14, 8, INK, rx=3)
    rect(x + 4, y + 15, 74, 40, "#000000", rx=11, opacity=0.18)
    rect(x - 38, y - 20, 76, 40, color, rx=10, stroke=INK, sw=3.5)
    rect(x + 6, y - 15, 9, 30, "#cfe8f5", rx=3)
    rect(x - 24, y - 13, 7, 26, "#cfe8f5", rx=3)
    rect(x - 14, y - 11, 19, 22, color, rx=5, stroke=INK, sw=2.5)
    rect(x - 7, y - 5, 11, 10, "#ffffff", rx=3, stroke=INK, sw=2)
    circ(x + 35, y - 11, 3, "#fff7d6")
    circ(x + 35, y + 11, 3, "#fff7d6")
    add("</g>")

def car(x, y, ang, color="#f2f2f2"):
    add(f'<g transform="rotate({f(ang)} {f(x)} {f(y)})">')
    for wx in (-26, 14):
        for wy in (-21, 14):
            rect(x + wx, y + wy, 13, 7, INK, rx=3)
    rect(x + 4, y + 14, 68, 36, "#000000", rx=10, opacity=0.18)
    rect(x - 34, y - 18, 68, 36, color, rx=9, stroke=INK, sw=3.5)
    rect(x + 4, y - 13, 8, 26, "#cfe8f5", rx=3)
    rect(x - 20, y - 11, 6, 22, "#cfe8f5", rx=3)
    rect(x - 12, y - 10, 15, 20, color, rx=4, stroke=INK, sw=2)
    add("</g>")

def bus(x, y, ang, color="#4f9e8f"):
    add(f'<g transform="rotate({f(ang)} {f(x)} {f(y)})">')
    for wx in (-46, 26):
        for wy in (-23, 16):
            rect(x + wx, y + wy, 18, 8, INK, rx=3)
    rect(x + 5, y + 16, 122, 40, "#000000", rx=12, opacity=0.18)
    rect(x - 62, y - 20, 124, 40, color, rx=11, stroke=INK, sw=3.5)
    for i in range(4):
        rect(x - 48 + i * 24, y - 14, 16, 28, "#cfe8f5", rx=3)
    rect(x + 36, y - 14, 16, 28, "#cfe8f5", rx=3)
    rect(x + 8, y - 8, 18, 16, "#ffffff", rx=4, stroke=INK, sw=2)
    add("</g>")

def road_arrow(cx, cy, ang):
    add(f'<g transform="rotate({f(ang)} {f(cx)} {f(cy)})">')
    poly([(cx - 15, cy - 8), (cx + 3, cy - 8), (cx + 3, cy - 16), (cx + 19, cy),
          (cx + 3, cy + 16), (cx + 3, cy + 8), (cx - 15, cy + 8)],
         "#f2f0e9", opacity=0.95)
    add("</g>")

# ---------- 道路・ブロック ----------

def zebra_v(cx, cy, road_w=96):
    """縦方向道路を横断（歩行者は東西）"""
    n = int(road_w // 22)
    x0 = cx - (n * 22) / 2 + 4
    for i in range(n):
        rect(x0 + i * 22, cy - road_w / 2 + 4, 14, road_w - 8, "#f2f0e9", rx=5, opacity=0.85)

def zebra_h(cx, cy, road_w=96):
    """横方向道路を横断（歩行者は南北）"""
    n = int(road_w // 22)
    y0 = cy - (n * 22) / 2 + 4
    for i in range(n):
        rect(cx - road_w / 2 + 4, y0 + i * 22, road_w - 8, 14, "#f2f0e9", rx=5, opacity=0.85)

def bars_h(x0, x1, y, step=12):
    """東西に歩く直線ブロック（棒は縦）"""
    xx = x0
    while xx <= x1:
        rect(xx, y - 11, 4.5, 22, YEL, rx=2)
        xx += step

def bars_v(x, y0, y1, step=12):
    """南北に歩く直線ブロック（棒は横）"""
    yy = y0
    while yy <= y1:
        rect(x - 11, yy, 22, 4.5, YEL, rx=2)
        yy += step

def warn(cx, cy, w=46, h=26):
    rect(cx - w / 2, cy - h / 2, w, h, "#000000", rx=6, opacity=0.06)
    step = 9.5
    yy = cy - h / 2 + 4
    while yy <= cy + h / 2 - 2:
        xx = cx - w / 2 + 4
        while xx <= cx + w / 2 - 2:
            circ(xx, yy, 3, YEL)
            xx += step
        yy += step

def signal(x, y):
    rect(x - 7, y - 17, 14, 34, INK, rx=5)
    circ(x, y - 9, 3.2, "#ff5a5a")
    circ(x, y, 3.2, "#ffd60a")
    circ(x, y + 9, 3.2, "#34c759")

def star(cx, cy, r=11, fill="#ffd60a"):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    poly(pts, fill, stroke=INK, sw=2.5)

def cone(x, y):
    circ(x, y + 8, 7, "#000000", opacity=0.14)
    poly([(x - 6, y + 6), (x + 6, y + 6), (x, y - 10)], "#ff7f27", stroke=INK, sw=2.5)
    rect(x - 4, y - 2, 8, 4, "#ffffff")
    line(x - 8, y + 7, x + 8, y + 7, INK, 2.5)

def barrier(x, y, ang=0, w=110):
    add(f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)})">')
    rect(-w / 2, -9, w, 26, "#000000", rx=6, opacity=0.16)
    rect(-w / 2, -13, w, 26, "url(#hazard)", rx=5, stroke=INK, sw=3.5)
    for fx in (-w / 2 + 12, w / 2 - 12):
        rect(fx - 3, 13, 6, 10, "#8a8794", stroke=INK, sw=2)
    add("</g>")

def work_sign(x, y):
    circ(x, y + 22, 10, "#000000", opacity=0.14)
    line(x - 13, y + 32, x - 5, y - 14, "#8a7a5f", 4)
    line(x + 13, y + 32, x + 5, y - 14, "#8a7a5f", 4)
    rect(x - 30, y - 16, 60, 32, "#ffffff", rx=5, stroke=INK, sw=3)
    rect(x - 26, y - 12, 52, 24, "none", rx=3, stroke="#ff7f27", sw=3.5)
    text(x, y + 6, "工事中", size=15)

def construction(cx, cy, big=False):
    """横断歩道がなく渡れない点の通行止め表現"""
    if big:
        rect(cx - 70, cy - 35, 140, 70, "#67636f", rx=14, stroke="#4c4954", sw=3)
        ell(cx + 52, cy - 18, 24, 13, "#a9793f", stroke=INK, sw=2.5)
        ell(cx - 40, cy + 22, 18, 10, "#a9793f", stroke=INK, sw=2.5)
        cone(cx - 82, cy - 52)
        cone(cx + 78, cy + 48)
        cone(cx + 40, cy + 62)
        barrier(cx + 92, cy - 58, -12)
        barrier(cx - 100, cy + 62, 8)
        work_sign(cx - 108, cy - 40)
    else:
        barrier(cx, cy - 56, 0)
        barrier(cx, cy + 56, 0)
        cone(cx - 34, cy - 40)
        cone(cx + 34, cy + 40)
        work_sign(cx - 84, cy + 80)

def komainu(x, y, flip=1):
    """石段の狛犬さん（固定ピース）"""
    circ(x, y + 6, 10, "#000000", opacity=0.14)
    rect(x - 11, y - 4, 22, 14, "#cfcabb", rx=3, stroke=INK, sw=2.5)
    ell(x, y - 10, 9, 7, "#b8b3a3", stroke=INK, sw=2.5)
    circ(x + 4 * flip, y - 19, 6.5, "#b8b3a3", stroke=INK, sw=2.5)
    circ(x + 4 * flip, y - 26, 2, "#b8b3a3", stroke=INK, sw=1.5)
    path(f"M {x - 8 * flip} {y - 12} q -5 -4 -2 -9", stroke="#b8b3a3", sw=4, cap="round")
    circ(x + 4 * flip, y - 18, 1.2, INK)

def bus_stop(x, y):
    """バス停のベンチ（固定ピース）"""
    circ(x + 32, y + 14, 12, "#000000", opacity=0.12)
    rect(x - 32, y + 2, 64, 12, "#8a6a4a", rx=6, stroke=INK, sw=2.5)
    rect(x - 26, y + 14, 7, 8, "#8a6a4a", stroke=INK, sw=2)
    rect(x + 19, y + 14, 7, 8, "#8a6a4a", stroke=INK, sw=2)
    line(x + 54, y + 6, x + 54, y - 36, INK, 3.5)
    rect(x + 42, y - 58, 24, 22, "#3f7cd9", rx=5, stroke=INK, sw=2.5)
    rect(x + 47, y - 52, 14, 8, "#ffffff", rx=3)

def chip(cx, cy, s, size=19, fill="#ffffff", tc=None):
    w = size * len(s) * 0.95 + 22
    h = size + 15
    rect(cx - w / 2, cy - h / 2, w, h, fill, rx=h / 2, stroke=INK, sw=2.5, opacity=0.95)
    text(cx, cy + size * 0.36, s, size=size, fill=tc or INK)

def leader(x1, y1, x2, y2):
    line(x1, y1, x2, y2, INK, 2, opacity=0.55, dash="2 5")

def bubble(cx, cy, s, size=17):
    w = size * len(s) * 0.95 + 26
    h = size + 18
    poly([(cx - 6, cy + h / 2 - 2), (cx + 8, cy + h / 2 - 2), (cx - 2, cy + h / 2 + 14)],
         "#ffffff", stroke=INK, sw=2.5)
    rect(cx - w / 2, cy - h / 2, w, h, "#ffffff", rx=h / 2, stroke=INK, sw=3)
    text(cx, cy + size * 0.36, s, size=size)

# ============================================================
# 描画
# ============================================================

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add('<defs><pattern id="hazard" width="28" height="28" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    '<rect width="28" height="28" fill="#ff7f27"/><rect width="14" height="28" fill="#ffffff"/></pattern>'
    '<pattern id="hazardY" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    '<rect width="16" height="16" fill="none"/><rect width="7" height="16" fill="#ffd60a"/></pattern></defs>')
add(f'<rect width="{W}" height="{H}" fill="{GRASS}"/>')
# 草地のムラ
for i in range(16):
    gx = random.uniform(0, W)
    gy = random.uniform(0, H)
    ell(gx, gy, random.uniform(40, 110), random.uniform(24, 60), GRASS_D, opacity=0.45, rot=random.uniform(0, 180))
for i in range(12):
    circ(random.uniform(20, W - 20), random.uniform(20, H - 20), 2.5, "#ffffff", opacity=0.8)

# ---------- 道路 ----------
# 基本は歩道：全道路の両側に歩道を敷く
SIDEWAYS = [
    (74, 380, 1462, 380, 96), (74, 880, 1462, 880, 88), (74, 1500, 1462, 1500, 96),
    (300, 74, 300, 1450, 80), (1080, 74, 1080, 1450, 96),
    (1307, 77, 327, 836, 72),
]
for x1, y1, x2, y2, w in SIDEWAYS:
    line(x1, y1, x2, y2, SIDE, w + 44)
ROADS = [
    (48, 380, 1488, 380, 96),    # H1
    (48, 880, 1488, 880, 88),    # H2
    (48, 1500, 1488, 1500, 96),  # H3
    (300, 48, 300, 1500, 80),    # V1
    (1080, 48, 1080, 1500, 96),  # V2
]
for x1, y1, x2, y2, w in ROADS:
    line(x1, y1, x2, y2, ROAD, w)
line(1330, 48, 300, 857, ROAD, 72)  # 斜め道路 D

# ---------- 歩道リボンと点字ブロック ----------
# （歩道は全道路に敷設済み。ここからは点字ブロック網のみ）
rect(600, 1548, 730, 208, SIDE, rx=24, stroke=SIDE_D, sw=3)  # 駅前広場
# 郵便ポスト（郵便屋さんの出現地点）
circ(880, 1592, 12, "#000000", opacity=0.14)
rect(866, 1560, 28, 34, "#d94f43", rx=8, stroke=INK, sw=3)
rect(870, 1566, 20, 6, "#7a2e28", rx=2)
text(880, 1588, "〒", size=13, fill="#ffffff")

# ---------- 誘導レーン（道路中央の点字ブロック） ----------
bars_h(580, 1010, 380)          # H1中央
bars_v(1080, 470, 800)          # V2中央（工事中の手前まで）
warn(1080, 820, 26, 40)         # 工事中の手前の警告ブロック
bars_v(1080, 950, 1400)         # 工事中の向こう側
bars_v(1080, 1560, 1668)        # 駅前広場
warn(1080, 1690, 26, 20)        # 改札手前の警告ブロック
# 通学路（破線のルート）
xx = 96
while xx <= 240:
    rect(xx, 826, 20, 7, YEL, rx=3)
    xx += 34
# バス停のベンチ（固定ピース）
bus_stop(398, 824)

# ---------- 街の配置 ----------
# 上段
house(150, 160, 105, 98, rot=-6, roof="#e4643b")
tree(92, 262, 16)
tree(208, 250, 18)
# V2とまがりビルのあいだ（斜め道路の西側のみ）
house(1170, 240, 100, 88, rot=-4, roof="#c9803c")
tree(1300, 318, 16)
# 公園（スタート）
tree(430, 132, 22)
tree(662, 122, 20)
tree(422, 262, 18)
tree(580, 110, 16)
ell(606, 226, 54, 36, "#7fb6d9", stroke="#5d93b8", sw=3)
rect(528, 292, 10, 16, "#8a7a5f", stroke=INK, sw=2)
rect(552, 292, 10, 16, "#8a7a5f", stroke=INK, sw=2)
# ラジオ体操クラブ（朝のみの固定ピース）
rect(450, 158, 24, 20, "#6b5340", rx=4, stroke=INK, sw=2.5)
circ(457, 168, 3, "#ffffff")
circ(467, 168, 3, "#ffffff")
line(474, 158, 482, 144, INK, 2.5)
text(566, 148, "♪", size=18, fill="#3f7cd9")
text(438, 138, "♪", size=13, fill="#3f7cd9")
person(498, 178, 120, "#4f9e8f", "#4a3b2c")
person(536, 198, 240, "#e05a4e", "#2b2b31")
person(506, 216, 0, "#f2a93b", "#6b4a2f")
house(760, 118, 100, 88, rot=4, roof="#f2a93b")
house(762, 230, 100, 88, rot=-3, roof="#c9803c")
tree(892, 182, 18)
# まがりビル
bent_tower(1400, 62)
# 駅伝倉庫（南西）
rect(80, 1060, 158, 300, SIDE, rx=18)
rect(96, 1082, 140, 140, "#4fa3a5", rx=10, stroke=INK, sw=4)
rect(96, 1082, 140, 26, "#ffffff", rx=10, opacity=0.55)
ac_units(96, 1082, 140, 140)
car(112, 1292, 90)
car(184, 1292, 90, color="#d96a5a")

# 中段
# 小学校
rect(86, 446, 166, 360, SIDE, rx=18)
school(104, 470)
ell(172, 738, 58, 52, "#e8d9a8", stroke=SIDE_D, sw=3)
tree(236, 560, 16)
# 斜め道路沿いの家々
house(400, 470, 120, 100, rot=-4, roof="#e4643b")
shop(310, 540, 110, 100, awn="#d96a5a")
tree(560, 530, 15)
# 喫茶ライオン
add('<polygon points="855,470 1032,470 1032,808 430,808" fill="#e9e2cf" opacity="0.97"/>')
shop(860, 540, 150, 130, wall="#f7eed6", awn="#8a5a3b")
coffee_cup(920, 500)
circ(876, 748, 11, "#ffffff", stroke=INK, sw=2.5)
circ(906, 762, 9, "#ffffff", stroke=INK, sw=2.5)
# ドーナツやさん
rect(1150, 456, 310, 220, SIDE, rx=18)
shop(1190, 520, 230, 95, wall="#f7eed6", awn="#e88bb0")
donut(1305, 502, 48)
office_box(1190, 690, 230, 118)
# 南段
house(110, 950, 120, 100, rot=3, roof="#c9803c")
tree(100, 1408, 16)
# 団地
rect(380, 952, 330, 474, SIDE, rx=18)
flat(400, 976, 290, 118)
flat(400, 1160, 290, 118, base="#ded8c6")
tree(432, 1350, 20)
tree(662, 1342, 18)
# 交番
rect(900, 952, 110, 108, SIDE, rx=12)
police_box(912, 964)
# 民家
house(760, 1080, 110, 95, rot=4, roof="#f2a93b")
house(772, 1220, 110, 95, rot=-3, roof="#e4643b")
tree(912, 1300, 18)
# コンビニ
konbini(1160, 952)
# タクシー会社
office_box(1300, 952, 150, 115)
# 神社
shrine(1180, 1130)
# 石段の狛犬さん（固定ピース）
komainu(1180, 1300, 1)
komainu(1292, 1300, -1)
# 駅前西の民家
house(120, 1600, 120, 100, rot=-4, roof="#e4643b")
house(142, 1758, 110, 95, rot=3, roof="#c9803c")
tree(258, 1700, 18)
tree(452, 1720, 20)
tree(488, 1820, 16)

# 駅（広場・改札・駅舎・線路）
station()
# 駅前タクシー
taxi(648, 1596, 0)
taxi(648, 1668, 0)

# ---------- 工事中（物理的な通行止め） ----------
construction(1080, 880, big=True)   # V2×H2 交差点
# ---------- 事故多発地点（横断歩道なし=事故メタファー） ----------
rect(254, 1466, 92, 68, "url(#hazardY)", rx=6, opacity=0.9)
line(218, 1418, 218, 1462, INK, 4)
rect(206, 1396, 26, 26, YEL, rx=4, stroke=INK, sw=3, rot=45, cx=219, cy=1409)
text(219, 1415, "！", size=17)
# 引っ越しのマッチョたち（重ね置きで人数スタック→担送）
person(975, 845, 0, "#d9d3c8", "#2b2b31", buff=True)
person(968, 892, 0, "#e07b39", "#4a3b2c", buff=True)

# ---------- キャラ ----------
# お爺さん（スタート・道の中央を東へ歩く）
person(585, 380, 90, "#3f6f74", "#d9dade", cane=True)
bubble(650, 316, "えきは…？")
# みち案内板
sign_board(522, 306, -8)
# あがり症の女子高生
person(762, 318, -90, "#ef8fb0", "#6b4a2f", long_hair=True, skirt="#5a6474", blush=True)
# わがまま誘導犬ハチ
circ(1146, 480, 95, "none", stroke="#ffffff", sw=3.5, opacity=0.85, extra='stroke-dasharray="10 9"')
dog(1146, 480, 90, harness=True)
# お巡りさん
person(955, 1105, 180, "#3d5a80", "#4a3b2c", cap_color="#3d5a80")
# 犬の散歩マダム
person(502, 942, 90, "#c26a9a", "#b8b8bd")
dog(536, 940, 90, color="#f2f2f2")
# 小学生隊列
for i, c in enumerate(["#e05a4e", "#4f9e4f", "#4f7fd9"]):
    person(110 + i * 36, 828, 90, c, "#4a3b2c", hat="#ffd60a")
# 野良猫
cat(1240, 648, 0)
# 嘘つきお兄さん
person(830, 762, -45, "#7a4f9e", "#2b2b31", glasses=True)
bubble(940, 720, "こっちだよ✗")
# 警備員さん
person(1318, 372, 180, "#2f2f38", "#3a3a42", cap_color="#2f2f38")
# 駅員さん
person(1198, 1712, 180, "#3d5a80", "#4a3b2c", cap_color="#f2f2f2")

# コンボのきらきら
star(880, 330)
star(1010, 430, r=9)
star(1128, 620, r=10)

# ---------- ラベル ----------
chip(585, 240, "スタート")
leader(585, 258, 585, 348)
chip(470, 252, "みち案内板")
leader(490, 270, 516, 292)
chip(1240, 586, "わがまま誘導犬ハチ")
leader(1210, 596, 1164, 508)
chip(955, 892, "交番")
leader(958, 908, 950, 946)
chip(1080, 742, "工事中・わたれない")
leader(1080, 762, 1080, 820)
chip(150, 1420, "事故多発地点")
leader(190, 1432, 214, 1412)
chip(760, 800, "引っ越しのマッチョ（重ね置き）")
leader(820, 820, 930, 850)
chip(1420, 1330, "狛犬さん（固定）")
leader(1398, 1332, 1300, 1308)
chip(430, 742, "バス停のベンチ（固定）")
leader(430, 762, 430, 804)
chip(169, 442, "小学校")
leader(169, 458, 171, 468)
chip(842, 424, "喫茶ライオン")
leader(868, 442, 896, 470)
chip(1310, 384, "ドーナツやさん")
leader(1310, 402, 1308, 428)
chip(1405, 118, "まがりビル")
chip(1218, 908, "コンビニ・元気回復")
leader(1218, 926, 1218, 948)
chip(990, 790, "嘘つきお兄さん")
chip(1410, 420, "警備員さん（動く壁）")
leader(1394, 436, 1330, 382)
chip(1144, 1656, "ゴール", size=21)
# ゴール矢印
rect(660, 1604, 70, 26, YEL, rx=8, stroke=INK, sw=3.5)
poly([(730, 1588), (768, 1617), (730, 1646)], YEL, stroke=INK, sw=3.5)

# ---------- HUD ----------
# 親切コンボ
rect(598, 30, 340, 62, "#ffffff", rx=31, stroke=INK, sw=3.5)
star(638, 61, r=13)
star(898, 61, r=13)
text(768, 74, "親切 ×3 連鎖！", size=33)
# 元気ゲージ
rect(598, 100, 340, 46, "#ffffff", rx=23, stroke=INK, sw=3, opacity=0.96)
text(642, 131, "元気", size=21)
rect(682, 112, 226, 22, "#d9d2bd", rx=11)
rect(682, 112, 164, 22, "#7ed957", rx=11)
# 親切ポイント（配置通貨）
rect(598, 154, 340, 40, "#ffffff", rx=20, stroke=INK, sw=3, opacity=0.96)
star(626, 174, 12)
text(652, 182, "KP 12", size=21, anchor="start")
text(914, 181, "あと 2 ピース", size=15, anchor="end")
# タイトル
rect(56, 44, 262, 42, INK, rx=21, opacity=0.82)
text(187, 72, "リアルフェイクタウン（仮）", size=18, fill="#ffffff")
rect(56, 94, 118, 26, "#ffffff", rx=13, opacity=0.85)
text(115, 112, "※企画イメージ", size=13, fill=INK)

# リボン
poly([(1052, 1950), (1484, 1908), (1496, 1966), (1064, 2008)], "#3f7cd9", stroke="#ffffff", sw=5)
text(1262, 1984, "えきまでエスコート！", size=36, fill="#ffd60a", rot=-5, stroke=INK, sw=6)

add("</svg>")

import os
os.makedirs("docs/concepts", exist_ok=True)
with open("docs/concepts/map-mockup.svg", "w") as fp:
    fp.write("\n".join(OUT))
print(f"written: docs/concepts/map-mockup.svg ({len(OUT)} elements)")
