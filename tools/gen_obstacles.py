#!/usr/bin/env python3
"""障害物生成器（生成パイプラインの縮小版。tools/beginner_stage.py のシミュコア上で動く）

盤面 = 特定のグラフ（グリッド生成 or JSON 読込）。生成器の動作は
「削除に相当する障害（岩）＋環境ピース（悪いこ・1回消滅の矢印）＋停止点（警告ノード）」の
配置のみ。配置後に全探索ソルバで「予算内に解ける／予算−1では解けない」を証明する。

使用ピース（ユーザー指定パレット）:
  AR/AL  右/左矢印     … その角で必ず曲がる。1回で消滅（塞がれていれば空振りで消える）
  GO     正しいこ      … 駅方向矢印どおりに案内（環境としても手札としても可）
  BA     悪いこ        … 必ず駅から遠ざかる方向を指す。1回騙されると以後無視、
                        人ピース(GO/COP)を同じ角に置けば無効化（D32）
  COP    警察          … 駅方向矢印どおりに案内（人ピース、悪いこのカウンタ兼用）
  岩     通せんぼ      … 辺を塞ぐ。停止ノードに隣接する岩は1手でどかせる
  広場   警告ノード    … 必ず停止（ピースの設置点・岩をどかす判断点）

使い方:
  python3 tools/gen_obstacles.py                      # 5x3 グリッド・seed複数試行で最良を表示
  python3 tools/gen_obstacles.py --seeds 50           # 試行数
  python3 tools/gen_obstacles.py --graph stage.json   # 特定グラフを入力
  python3 tools/gen_obstacles.py --play               # 生成した盤面を対局プレイ

グラフJSON: {"size":[W,H], "start":[x,y], "goal":[x,y], "edges":[[[x,y],[x,y]], ...]}
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from dataclasses import replace

from beginner_stage import (DELTA, DIRS, Board, DifficultyProfile, Engine, Piece,
                            PIECE_NAME, solve)

# ---------------------------------------------------------------- パレット
OBSTACLE_NODE_KINDS = ("BA", "AR", "AL", "GO", "COP")   # 環境ピースとして置く候補
HAND_PIECES = ("GO", "COP", "AR", "AL")                 # プレイヤー手札（配置=1手相当のKP消費）
GAUGE = 200                                           # 元気（生成盤はゆるめ固定）


def board_edges(size) -> list:
    """size=(W,H) の全格子辺"""
    W, H = size
    out = []
    for x in range(W):
        for y in range(H):
            if x + 1 < W:
                out.append(((x, y), (x + 1, y)))
            if y + 1 < H:
                out.append(((x, y), (x, y + 1)))
    return out


def base_profile(size, start, goal, edges, plazas=()) -> DifficultyProfile:
    return DifficultyProfile(
        no=0, name="生成盤", size=size, start=start, goal=goal,
        pieces=HAND_PIECES, kp=0, gauge=GAUGE, start_wait=True,
        plazas=tuple(plazas), edges=list(edges), free_place=True)


def evalu(prof: DifficultyProfile) -> tuple | None:
    """(最小手数, 解の一手数, ソルバ成功) を返す。解けなければ None"""
    cost, actions, _ = solve(prof, 24)
    if cost is None:
        return None
    return (cost, len(actions))


def candidates(prof: DifficultyProfile, rng: random.Random) -> list:
    """変更候補: ('rock',a,b) / ('env',node,kind) / ('plaza',node)。重複・既存は除外"""
    board = Board.build(prof)
    nodes = sorted(board.dist.keys() - {prof.start, prof.goal})
    env_nodes = {n for n, _ in prof.env_pieces} | set(prof.plazas)
    rock_keys = {frozenset(r) for r in prof.rocks}

    out = []
    # 岩候補: 現存辺で未設置、なおかつ辺削除しても start→goal が (board.dist 上で) つながるものだけ
    for e in sorted(board.edges):
        a, b = sorted(e)
        if frozenset((a, b)) in rock_keys:
            continue
        out.append(("rock", a, b))
    for n in nodes:
        for k in OBSTACLE_NODE_KINDS:
            if n in env_nodes:
                break  # 1スロット1環境ピース（BA だけでなく AR 等も占有）
        else:
            for k in OBSTACLE_NODE_KINDS:
                out.append(("env", n, k))
            out.append(("plaza", n))
    rng.shuffle(out)
    return out


def apply(prof: DifficultyProfile, cand) -> DifficultyProfile:
    op = cand[0]
    if op == "rock":
        return replace(prof, rocks=prof.rocks + ((cand[1], cand[2]),))
    if op == "env":
        return replace(prof, env_pieces=prof.env_pieces + ((cand[1], cand[2]),))
    if op == "plaza":
        return replace(prof, plazas=prof.plazas + (cand[1],))
    raise ValueError(cand)


def generate(seed: int, size=(5, 3), start=(0, 1), goal=(4, 1), edges=None,
             max_steps: int = 14, sample: int = 40) -> tuple[DifficultyProfile | None, list]:
    """seed で1ステージ生成。単調強化: 1回の変更で難度スコアが下がるものは棄却、
    上がる/変わらない中で最も良い1個を採用、を繰り返す。戻り値 (profile, 採用ログ)"""
    rng = random.Random(seed)
    edges = edges if edges is not None else board_edges(size)
    prof = base_profile(size, start, goal, edges)
    base = evalu(prof)
    if base is None:
        return None, []
    score = base
    log = []
    for _ in range(max_steps):
        cands = candidates(prof, rng)[:sample]
        best = None  # (score, cand, prof2)
        for c in cands:
            p2 = apply(prof, c)
            s2 = evalu(p2)
            if s2 is None:          # 詰む改変は禁止（削除単調性）
                continue
            if s2 < score:          # 難度が下がる改変も禁止
                continue
            if best is None or s2 > best[0]:
                best = (s2, c, p2)
        if best is None:
            break
        score, cand, prof = best
        log.append(cand)
        if score[0] >= 6:           # 最小手数6で十分（それ以上は長大化）
            break
    cost, actions, _ = solve(prof, 24)
    prof.kp = cost
    # 証明: 予算 kp で解け、kp-1 では解けない
    ok_min = solve(prof, prof.kp)[0] is not None
    ok_below = prof.kp == 0 or solve(prof, prof.kp - 1)[0] is None
    prof.note = f"seed={seed} 最小手数={cost}（予算内可・予算-1不可={ok_below}）"
    if not (ok_min and ok_below):
        prof.note += " ⚠証明不完全"
    return prof, log


def describe(prof: DifficultyProfile) -> None:
    from beginner_stage import print_board, replay2
    print(f"「{prof.name}」 {prof.note}")
    print(f"  size={prof.size} start={prof.start} goal={prof.goal} KP={prof.kp} 元気={prof.gauge}")
    print(f"  手札: {[PIECE_NAME[k] for k in prof.pieces]}")
    if prof.rocks:
        print(f"  岩: {[f'{a}-{b}' for a, b in prof.rocks]}")
    if prof.env_pieces:
        print(f"  環境: {[(n, PIECE_NAME[k]) for n, k in prof.env_pieces]}")
    if prof.plazas:
        print(f"  広場(停止点): {list(prof.plazas)}")
    print_board(prof, {})
    cost, actions, _ = solve(prof, prof.kp)
    print("  --- 最小手順 ---")
    for node, kind, d in actions:
        if kind == "ROCK":
            print(f"    {node} から {d} 方向の岩をどかす")
        else:
            print(f"    {node} に {PIECE_NAME[kind]}" + (f"（{d} 向き）" if d else ""))
    eng, info = replay2(prof, actions)
    print(f"  [{info}] 元気残り {eng.gauge}")


def load_graph(path: str):
    d = json.load(open(path))
    return (tuple(d["size"]), tuple(d["start"]), tuple(d["goal"]),
            [tuple(map(tuple, e)) for e in d["edges"]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24, help="試行シード数")
    ap.add_argument("--graph", help="盤面JSON（未指定なら5x3グリッド）")
    ap.add_argument("--size", default="5,3", help="グリッド W,H")
    ap.add_argument("--start", default="0,1")
    ap.add_argument("--goal", default="4,1")
    ap.add_argument("--play", action="store_true")
    args = ap.parse_args()

    if args.graph:
        size, start, goal, edges = load_graph(args.graph)
    else:
        size = tuple(map(int, args.size.split(",")))
        start = tuple(map(int, args.start.split(",")))
        goal = tuple(map(int, args.goal.split(",")))
        edges = board_edges(size)

    results = []
    for seed in range(args.seeds):
        prof, log = generate(seed, size, start, goal, edges)
        if prof is None:
            continue
        cost, actions, _ = solve(prof, prof.kp)
        results.append(((cost, len(actions), len(log)), seed, prof, log))

    results.sort(reverse=True)
    print(f"試行 {args.seeds} seeds → 証明つき {len(results)} 盤")
    print("上位3盤:")
    for (score, seed, prof, log) in results[:3]:
        print(f"  seed={seed} 最小手数={score[0]} 最小解の手順数={score[1]} 採用障害物={len(log)}")
    if results:
        print("\n=== 最良盤 ===")
        describe(results[0][2])
        if args.play:
            from beginner_stage import _play_stage
            _play_stage(results[0][2])
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
