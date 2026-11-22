#!/usr/bin/env python3
"""リアルフェイクタウン 初級ステージ プロトタイプ（決定論シミュコア 参照実装）

難易度プロファイル（DifficultyProfile）で 交差点の数 / 搭載ピース / 強制配置 /
KP / 元気 を変えてステージを組み立てる。導入カリキュラム（game-design §5）の初級3本。

使い方:
  python3 tools/beginner_stage.py --profiles      # プロファイル一覧
  python3 tools/beginner_stage.py --demo          # 3ステージ全部をソルバで解いて自動プレイ
  python3 tools/beginner_stage.py --solve 1       # ステージ1の最小手数を証明（ソルバQA）
  python3 tools/beginner_stage.py --stage 1       # ステージ1を対局プレイ

決定論: 乱数不使用。乱数は演出のみ（未実装）。参照仕様: docs/game-design.md §3-§5, docs/puzzle-generation.md
"""
from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass, field, replace

# ---------------------------------------------------------------- 基本座標
DIRS = ("E", "S", "W", "N")  # 右回り（画面座標 y下向き）。同距離タイブレークもこの順
DELTA = {"E": (1, 0), "S": (0, 1), "W": (-1, 0), "N": (0, -1)}


def right_of(d: str) -> str:
    return DIRS[(DIRS.index(d) + 1) % 4]


def left_of(d: str) -> str:
    return DIRS[(DIRS.index(d) - 1) % 4]


# ---------------------------------------------------------------- ピース
@dataclass(frozen=True)
class Piece:
    kind: str          # "JK" 女子高生 / "COP" お巡りさん / "GO" 正しいこ / "BA" 悪いこ / "AR","AL" 矢印 / "BIKE" 自転車
    direction: str | None = None  # JK のみ（宣言型方向・D23）


PIECE_COST = {"JK": 1, "COP": 3, "BIKE": 1, "FR": 1, "FL": 1,
              "GO": 1, "BA": 1, "AR": 1, "AL": 1}
PIECE_NAME = {"JK": "あがり症の女子高生", "COP": "交番のお巡りさん", "BIKE": "置き自転車",
              "FR": "強制右指示", "FL": "強制左指示",
              "GO": "正しいこ", "BA": "悪いこ", "AR": "右矢印", "AL": "左矢印"}
# 環境（生成器・シナリオが置く障害物）として使える種。人ピース同角で悪いこは無効化される（D32）
ENV_KINDS = ("BA", "AR", "AL", "BIKE")


# ---------------------------------------------------------------- ステージ定義
@dataclass
class DifficultyProfile:
    """難易度パラメータ: 交差点数・搭載ピース・強制配置・KP・元気でステージを組み立てる"""
    no: int
    name: str
    size: tuple[int, int]                  # 交差点の数 (W, H)
    start: tuple[int, int]
    goal: tuple[int, int]
    pieces: tuple[str, ...]                # 搭載キャラ（手持ち）
    kp: int                                # 親切ポイント
    gauge: int                             # 元気（移動1/停止2で消費）
    forced_autocross: tuple[int, int] | None = None   # 強制配置: 点字つき交差点
    forced_hachi: tuple[int, int] | None = None       # 強制配置: わがまま誘導犬ハチ
    forced_bikes: tuple[tuple[int, int], ...] = ()    # 強制配置: 置き自転車（その場の点字を無効化・D30）
    forced_map: tuple[int, int] | None = None         # 強制配置: みち案内板（触れると2交差点ワープ）
    cracked_crosses: tuple[tuple[int, int], ...] = () # 亀裂十字路: 直進優先が適用されない（必ず曲がる）
    rocks: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = ()   # 通せんぼの岩（停止中に1手でどかせる）
    fissures: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = ()  # 地割れ（マッチョ仕様・生成器では不使用）
    env_pieces: tuple[tuple[tuple[int, int], str], ...] = ()  # 環境ピース (node, kind): 悪いこ・矢印など
    start_wait: bool = True                           # D18 開始指示待ち（Falseなら即歩き出す）
    plazas: tuple[tuple[int, int], ...] = ()          # 警告ノード（広場・改札前）: 必ず停止（§3）
    free_place: bool = False                          # Trueなら停止中に盤面の任意ノードへ配置可（1手/個）
    node_names: dict | None = None                    # 実在場所の名前（表示用）
    edges: list[tuple] | None = None       # None なら全交差点を格子状に接続
    note: str = ""


STAGES: dict[int, DifficultyProfile] = {
    1: DifficultyProfile(
        no=1, name="まっすぐ道を渡って", size=(3, 3), start=(0, 0), goal=(2, 2),
        pieces=("JK",), kp=3, gauge=30,
        note="導入1: 女子高生のみ。開始は指示待ち（D18）。最初の一声で歩き出す。",
    ),
    2: DifficultyProfile(
        no=2, name="おまわりさんのいる交差点", size=(4, 3), start=(0, 0), goal=(3, 2),
        pieces=("JK", "COP"), kp=6, gauge=40,
        forced_autocross=(1, 1),
        note="導入2: 方向指定できないピース（お巡りさん）＋点字つき交差点（D24）。駅方向矢印（D23）を読む。",
    ),
    3: DifficultyProfile(
        no=3, name="ハチの右", size=(4, 4), start=(0, 0), goal=(2, 2),
        pieces=("JK",), kp=4, gauge=50,
        forced_hachi=(1, 1),
        edges=[((0, 0), (1, 0)), ((0, 0), (0, 1)), ((1, 0), (1, 1)), ((0, 1), (1, 1)),
               ((1, 1), (2, 1)), ((1, 1), (1, 2)), ((2, 1), (3, 1)), ((1, 2), (1, 3)),
               ((2, 1), (2, 2))],
        note="導入3: 強制イベント（ハチの必ず右・D26）の読み。ハチは全ルートの最短方向にエスコートする。",
    ),
}

# ---------------------------------------------------------------- 丸の内ブック（実在街路の手組み盤・§10.3）
# 座標は実街路の相対配置の手組み（近似）。PLATEAU取り込み後は歩道抽出データに置き換わる。
# x: 東向き / y: 南向き。行幸通り = 和田倉門（皇居側）→ 東京駅（行幸通りは実際は西から東へ駅に至る）
_MARUNOUCHI_NAMES = {
    (0, 0): "お堀端（皇居東御苑・北）", (1, 0): "永代通り×日比谷通り", (2, 0): "永代通り×仲通り（新丸ビル前）",
    (3, 0): "東京駅丸の内北口", (0, 1): "和田倉門前（皇居東御苑）", (1, 1): "行幸通り×日比谷通り",
    (2, 1): "行幸通り×仲通り", (3, 1): "丸の内駅前広場", (4, 1): "東京駅丸の内駅舎（駅員さん）",
    (1, 2): "晴海通り（有楽町方面）", (2, 2): "晴海通り×仲通り（明治生命館前）", (3, 2): "東京駅丸の内南口",
}
MARUNOUCHI_EDGES = [
    ((0, 0), (0, 1)),                                   # お堀端
    ((0, 1), (1, 1)), ((1, 1), (2, 1)), ((2, 1), (3, 1)), ((3, 1), (4, 1)),  # 行幸通り
    ((1, 0), (1, 1)), ((1, 1), (1, 2)),                 # 日比谷通り
    ((2, 0), (2, 1)), ((2, 1), (2, 2)),                 # 丸の内仲通り
    ((1, 0), (2, 0)), ((2, 0), (3, 0)),                 # 永代通り
    ((3, 0), (3, 1)), ((3, 1), (3, 2)),                 # 駅前（北口・南口）
    ((1, 2), (2, 2)), ((2, 2), (3, 2)),                 # 晴海通り
]
MARUNOUCHI_STAGES: dict[int, DifficultyProfile] = {
    1: DifficultyProfile(
        no=1, name="和田倉門から行幸通りを駅へ", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=(), kp=0, gauge=40, start_wait=False,
        node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入1: ピースなし。点字ブロックがあれば、お爺ちゃんはまっすぐ進む（直進優先・基本ルール②）。",
    ),
    2: DifficultyProfile(
        no=2, name="行幸通り×仲通りのお巡りさん", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "COP"), kp=6, gauge=50,
        forced_autocross=(2, 1), plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入2: 行幸通り×仲通りに点字つき交差点（実際の行幸通りに点字ブロック整備あり）。丸の内警察署のお巡りさんも登場。",
    ),
    3: DifficultyProfile(
        no=3, name="ハチは行幸通りがお好き", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK",), kp=5, gauge=60,
        forced_hachi=(2, 1), plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入3: 仲通りの交差点でハチに抱き着かれる。駅方向へエスコートされたあとの「必ず右」で南口へ放り出される——駅前広場から建て直せるか。",
    ),
    4: DifficultyProfile(
        no=4, name="点字をつぶす置き自転車", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "COP", "BIKE"), kp=6, gauge=50,
        forced_autocross=(2, 1), forced_bikes=((2, 1),), plazas=((3, 1),),
        node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入4: 置き自転車（D30）で行幸通り×仲通りの点字が読めない。自律に頼らず、人の案内で駅へ。",
    ),
    5: DifficultyProfile(
        no=5, name="みち案内板のワープ", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK",), kp=3, gauge=60,
        forced_map=(2, 1), plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入5: みち案内板（D36）に触れると2交差点分、駅方向矢印どおりにワープ。中間のイベントは全部スキップ。",
    ),
    6: DifficultyProfile(
        no=6, name="亀裂の入った十字路", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "COP"), kp=5, gauge=70,
        cracked_crosses=((2, 1),), plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="丸の内導入6: 行幸通り×仲通りの亀裂十字路。直進できず必ず曲がる。横断歩道のない交差点の事故メタファー（§3）。",
    ),
}

BOOKS = {"intro": STAGES, "marunouchi": MARUNOUCHI_STAGES}

# ---------------------------------------------------------------- クイズブック（実装済みメカニクスの総合テスト）
QUIZ_STAGES: dict[int, DifficultyProfile] = {
    1: DifficultyProfile(
        no=1, name="Q1: まっすぐ進む", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=(), kp=0, gauge=50, start_wait=False,
        node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="[易] ピースなし。点字ブロックがあればまっすぐ進む。直進優先の基本。",
    ),
    2: DifficultyProfile(
        no=2, name="Q2: 広場でお巡りさん", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("COP",), kp=3, gauge=60, start_wait=False,
        plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="[易] 駅前広場で停止したら、お巡りさんを置いて矢印どおりに案内してもらう。",
    ),
    3: DifficultyProfile(
        no=3, name="Q3: ハチの右を受け止める", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "COP"), kp=5, gauge=70, start_wait=False,
        forced_hachi=(1, 1), plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="[中] ハチの右で放り出される先を読んで、強制左指示を受けておく。先読みの学習。",
    ),
    4: DifficultyProfile(
        no=4, name="Q4: 人の案内で駅へ", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "COP"), kp=4, gauge=70, start_wait=False,
        plazas=((3, 1),), node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="[中] 広場で停止したら、人の案内で正しい方向へ導く。COPとJKの使い分け。",
    ),
    5: DifficultyProfile(
        no=5, name="Q5: ハチと亀裂と広場", size=(5, 3), start=(0, 1), goal=(4, 1),
        pieces=("JK", "FR", "FL"), kp=6, gauge=80, start_wait=False,
        forced_hachi=(1, 1), cracked_crosses=((2, 1),), plazas=((3, 1),),
        node_names=_MARUNOUCHI_NAMES, edges=MARUNOUCHI_EDGES,
        note="[高] ハチの右＋亀裂十字路＋広場が絡む。強制右/左指示を配置して導く。",
    ),
}

BOOKS = {"intro": STAGES, "marunouchi": MARUNOUCHI_STAGES, "quiz": QUIZ_STAGES}


# ---------------------------------------------------------------- 盤面
@dataclass
class Board:
    size: tuple[int, int]
    rocks: set                         # 通せんぼの岩がある辺 frozenset({a,b})
    fissures: set                      # 地割れがある辺 frozenset({a,b})
    edges: set[frozenset]
    dist: dict[tuple[int, int], int]   # 駅方向矢印（D23）: ゴールからの最短距離

    @classmethod
    def build(cls, prof: DifficultyProfile) -> "Board":
        W, H = prof.size
        edges: set[frozenset] = set()
        if prof.edges is None:
            for x in range(W):
                for y in range(H):
                    if x + 1 < W:
                        edges.add(frozenset(((x, y), (x + 1, y))))
                    if y + 1 < H:
                        edges.add(frozenset(((x, y), (x, y + 1))))
        else:
            for a, b in prof.edges:
                edges.add(frozenset((a, b)))
        board = cls(size=prof.size, edges=edges, dist={},
                    rocks={frozenset(r) for r in prof.rocks},
                    fissures={frozenset(f) for f in prof.fissures})
        # 駅方向矢印 = ゴールからの BFS 最短距離（同距離は DIRS 順で決定論的）
        dist = {prof.goal: 0}
        queue = [prof.goal]
        while queue:
            n = queue.pop(0)
            for d in DIRS:
                dx, dy = DELTA[d]
                m = (n[0] + dx, n[1] + dy)
                if m in dist or not board.has_edge(n, m):
                    continue
                dist[m] = dist[n] + 1
                queue.append(m)
        board.dist = dist
        return board

    def has_edge(self, a, b) -> bool:
        return frozenset((a, b)) in self.edges

    def is_passable(self, a, b, macho: int = 0, moved_rocks: set | None = None) -> bool:
        """岩（移動済みなら通れる）・地割れ（マッチョがあれば通れる）を含めた通過判定"""
        key = frozenset((a, b))
        if not self.has_edge(a, b):
            return False
        if key in self.rocks and (moved_rocks is None or key not in moved_rocks):
            return False
        if key in self.fissures and macho <= 0:
            return False
        return True

    def in_bounds(self, n) -> bool:
        W, H = self.size
        return 0 <= n[0] < W and 0 <= n[1] < H

    def neighbor_dirs(self, n) -> list[str]:
        out = []
        for d in DIRS:
            dx, dy = DELTA[d]
            m = (n[0] + dx, n[1] + dy)
            if self.in_bounds(m) and self.has_edge(n, m):
                out.append(d)
        return out

    def arrow(self, n, macho: int = 0, moved_rocks: set | None = None) -> str | None:
        """駅方向矢印（D23）: 最短方向。岩で塞がれた辺は指さない。同距離は DIRS 順"""
        cands = [(d, (n[0] + dx, n[1] + dy)) for d in DIRS
                 for dx, dy in [DELTA[d]]
                 if self.is_passable(n, (n[0] + dx, n[1] + dy), macho, moved_rocks)]
        cands = [(d, m) for d, m in cands if m in self.dist]
        if not cands:
            return None
        cands.sort(key=lambda dm: (self.dist[dm[1]], DIRS.index(dm[0])))
        return cands[0][0]

    def liar_dir(self, n, macho: int = 0, moved_rocks: set | None = None) -> str | None:
        """悪いこ（嘘つき系）: 必ず駅から遠ざかる方向を指す（本作のキモ・変更禁止）。
        dist 未登録ノード（切断済み等）は「駅から無限遠」として最優先で指す。"""
        FAR = 10 ** 9
        cands = [(d, (n[0] + dx, n[1] + dy)) for d in DIRS
                 for dx, dy in [DELTA[d]]
                 if self.is_passable(n, (n[0] + dx, n[1] + dy), macho, moved_rocks)]
        if not cands:
            return None
        cands.sort(key=lambda dm: (-self.dist.get(dm[1], FAR), DIRS.index(dm[0])))
        return cands[0][0]


# ---------------------------------------------------------------- シミュレータ（決定論コア）
@dataclass
class Engine:
    board: Board
    prof: DifficultyProfile
    pos: tuple[int, int]
    heading: str
    gauge: int
    waiting: bool                 # D18 開始指示待ち
    hachi_used: bool = False
    map_used: bool = False        # みち案内板ワープ済みフラグ
    macho: int = 0                # マッチョの残数（地割れを渡れる）
    moved_rocks: set = field(default_factory=set)  # どかした岩のある辺
    liar_met: set = field(default_factory=set)     # 一度騙された悪いこのいるノード（以後無視・D32）
    log: list = field(default_factory=list)

    def clone(self) -> "Engine":
        return Engine(self.board, self.prof, self.pos, self.heading, self.gauge,
                      self.waiting, self.hachi_used, self.map_used,
                      self.macho, set(self.moved_rocks), set(self.liar_met), list(self.log))

    # ---- 駅方向矢印（岩・地割れ込みの通行可能判定を使う）
    def arrow(self, node) -> str | None:
        return self.board.arrow(node, self.macho, self.moved_rocks)

    def liar_dir(self, node) -> str | None:
        return self.board.liar_dir(node, self.macho, self.moved_rocks)

    def _move(self, placed: dict, d: str, why: str) -> None:
        dx, dy = DELTA[d]
        self.pos = (self.pos[0] + dx, self.pos[1] + dy)
        self.heading = d
        self.gauge -= 1
        self.log.append(f"  {why}: {d} へ → {self.pos}（元気 {self.gauge}）")

    def _jk_relocate(self, placed: dict, node) -> None:
        """女子高生のクセ: 目の前を通られると照れて退避（消えて隣へ移動）"""
        piece = placed.pop(node)
        for d in DIRS:
            dx, dy = DELTA[d]
            m = (node[0] + dx, node[1] + dy)
            if self.board.in_bounds(m) and m in self.board.dist and m not in placed:
                placed[m] = Piece("JK", piece.direction)
                self.log.append(f"  女子高生は照れて {m} へ退避した")
                return
        self.log.append("  女子高生は照れてその場から消えた")

    def run_until_stop(self, placed: dict) -> tuple[str, str]:
        """次の「プレイヤーの判断が必要な停止」まで決定論的に進める。
        戻り値: ("STOP", node) / ("WIN", ...) / ("LOSE", reason)。placed は可変（JK退避を反映）"""
        guard = 0
        while True:
            guard += 1
            if guard > 1000:
                return ("LOSE", "散歩が長すぎます（想定外の循環）")
            if self.gauge <= 0:
                return ("LOSE", "元気が尽きて帰宅しました")
            if self.pos == self.prof.goal:
                return ("WIN", "駅員さんに到達")
            node = self.pos

            # 0. 強制イベント: わがまま誘導犬ハチ（介護犬仕様・D26）
            if node == self.prof.forced_hachi and not self.hachi_used:
                self.hachi_used = True
                self.log.append("  [強制イベント] ハチがエスコートを始めた（駅方向矢印どおり）")
                d = self.arrow(node)
                if d is None:
                    return ("LOSE", "ハチが途方に暮れた")
                self._move(placed, d, "  ハチにエスコートされ")
                node = self.pos
                # 必ず右。右がなければ左折。土地勘があれば抗えるが初級にはない
                r = right_of(self.heading)
                if self.board.in_bounds((node[0] + DELTA[r][0], node[1] + DELTA[r][1])) \
                        and self.board.has_edge(node, (node[0] + DELTA[r][0], node[1] + DELTA[r][1])):
                    self.log.append("  [強制イベント] ハチの必ず右——従うしかない（初級に土地勘はなし）")
                    self._move(placed, r, "  強制右折で")
                else:
                    l = left_of(self.heading)
                    if self.board.in_bounds((node[0] + DELTA[l][0], node[1] + DELTA[l][1])) \
                            and self.board.has_edge(node, (node[0] + DELTA[l][0], node[1] + DELTA[l][1])):
                        self.log.append("  [強制イベント] 右がないのでハチが左折を指示")
                        self._move(placed, l, "  やむなく左折で")
                    else:
                        self.log.append("  ハチは何も言わずにダッシュで走り去った")
                continue

            # 自律: 点字つき交差点（繰返し有効・D24）。置き自転車があると点字が読めず無効（D30）
            bike_here = placed.get(node)
            if node == self.prof.forced_autocross \
                    and node not in self.prof.forced_bikes \
                    and not (bike_here is not None and bike_here.kind == "BIKE"):
                d = self.arrow(node)
                if d is not None:
                    self.log.append("  [自律] 点字つき交差点——お爺ちゃんが自分で駅方向へ進む")
                    self._move(placed, d, "  自分の判断で")
                    continue

            # ワープ: みち案内板——触れた時点で2交差点分、駅方向矢印に沿って進む（中間イベント全部スキップ）
            if node == self.prof.forced_map and not self.map_used:
                self.map_used = True
                self.log.append("  [ワープ] みち案内板——駅方向矢印どおりに2交差点分進む")
                for _ in range(2):
                    d = self.arrow(node)
                    if d is None:
                        break
                    self._move(placed, d, "  ワープ")
                    node = self.pos
                    if node == self.prof.goal:
                        return ("WIN", "駅員さんに到達")
                    if self.gauge <= 0:
                        return ("LOSE", "元気が尽きました")
                continue

            # 0. 人のピースがある交差点では必ず呼び止まって案内を聞く（直進できても停止）
            #    一度騙された悪いこは以後無視（学習済み・D32）。矢印はピース扱いで必ず発火停止。
            # 0'. 広場（警告ノード）と開始指示待ち（D18）も必ず停止——右デフォルトは適用しない
            piece_here = placed.get(node)
            if piece_here is not None and piece_here.kind == "BA" and node in self.liar_met:
                piece_here = None
            if piece_here or node in self.prof.plazas or self.waiting:
                r = self._resolve_stop(placed)
                if r is not None:
                    return r
                continue

            # ジジイの行動ルール v3: 到着のたびに上から順に判定
            options = [d for d in DIRS
                       for dx, dy in [DELTA[d]]
                       if self.board.in_bounds((node[0] + dx, node[1] + dy))
                       and self.board.is_passable(node, (node[0] + dx, node[1] + dy),
                                                  self.macho, self.moved_rocks)]
            # 亀裂十字路: 直進優先が適用されない（必ず曲がるか戻る）
            if node in self.prof.cracked_crosses:
                options = [d for d in options if d != self.heading]
            if not options:
                return ("LOSE", "身動きが取れなくなった（完全に閉ざされた）")
            # 3. 直進できるなら直進
            if self.heading in options:
                self._move(placed, self.heading, "  直進")
                continue
            # 2. 一方しか進めなければ、左であっても進む（先がなければ戻る、を含む）
            if len(options) == 1:
                self.log.append("  先がないので戻る")
                self._move(placed, options[0], "  一方の道へ")
                continue

            r = right_of(self.heading)
            d = r if r in options else options[0]
            self.log.append("  行き先に困ったら法律どおり右（正解かどうかは運）")
            self._move(placed, d, "  右へ")
            continue

    def _resolve_stop(self, placed: dict) -> tuple[str, str] | None:
        """停止の解決（待機は元気2倍速）。呼び止め・広場・開始直後で人の案内を確認する。
        解決して移動したら None（呼び出し側はループ継続）、判断が必要なら ("STOP", node)"""
        self.gauge -= 2
        if self.gauge <= 0:
            return ("LOSE", "指示を待つあいだに元気が尽きた")
        node = self.pos
        resolver = placed.get(node)
        if resolver is not None:
            if resolver.kind == "BA":
                # 悪いこ（嘘つき系）: 必ず駅から遠ざかる方向を指す（キモ・不変）。
                # 1回目: 爺は無条件で従う（学習して以後無視）。2回目以降: 無視して自律に戻る。
                if node in self.liar_met:
                    self.waiting = False
                    return None
                d = self.liar_dir(node)
                self.liar_met.add(node)
                if d is None:
                    return ("LOSE", "悪いこも指せる道がない場所にいます")
                self.log.append(f"  悪いこ「駅ならこっちだよ、まかせて」→ {d}（嘘。駅と逆方向）")
                self.waiting = False
                self._move(placed, d, "  騙されて")
                return None
            if resolver.kind in ("FR", "FL"):
                # 強制右/左指示: この角で必ず曲がる（直進があっても）。看板は常設。
                turn = right_of(self.heading) if resolver.kind == "FR" else left_of(self.heading)
                self.log.append(f"  [強{'右' if resolver.kind == 'FR' else '左'}指示] {turn} へ曲がる")
                self.waiting = False
                self._move(placed, turn, "  強制方向で")
                return None
            if resolver.kind in ("AR", "AL"):
                # 右/左矢印（1回で消滅）: この角で必ず曲がる。塞がれていれば矢印は空振りで消える
                placed.pop(node)
                turn = right_of(self.heading) if resolver.kind == "AR" else left_of(self.heading)
                tn = (node[0] + DELTA[turn][0], node[1] + DELTA[turn][1])
                if not self.board.is_passable(node, tn, self.macho, self.moved_rocks):
                    self.log.append(f"  [{'右' if resolver.kind == 'AR' else '左'}矢印] 先が塞がれていて空振り（消滅）")
                    return ("STOP", node)
                self.log.append(f"  [{'右' if resolver.kind == 'AR' else '左'}矢印] {turn} へ曲がる（消滅）")
                self.waiting = False
                self._move(placed, turn, "  矢印どおり")
                return None
            if resolver.kind == "GO":
                # 正しいこ: 駅方向矢印どおりに案内（お巡りさんと同じ正しい案内）
                d = self.arrow(node)
                if d is None:
                    return ("LOSE", "正しいこも分からない場所にいます")
                self.log.append(f"  正しいこ「駅はあっちだよ」→ {d}（駅方向矢印どおり）")
                self.waiting = False
                self._move(placed, d, "  案内されて")
                return None
            if resolver.kind == "JK":
                dx, dy = DELTA[resolver.direction]
                if not self.board.has_edge(node, (node[0] + dx, node[1] + dy)):
                    return ("LOSE", "案内が道に合っていない（検証漏れ）")
                self.log.append(f"  女子高生「あ、あっち……です」→ {resolver.direction}")
                self.waiting = False
                self._move(placed, resolver.direction, "  案内されて")
                self._jk_relocate(placed, node)
                return None
            if resolver.kind == "COP":
                d = self.arrow(node)
                if d is None:
                    return ("LOSE", "お巡りさんも分からない場所にいます")
                self.log.append("  お巡りさん「交番はあっちですよ」（駅方向矢印どおり）")
                self.waiting = False
                self._move(placed, d, "  案内されて")
                return None
            # 誘導しないピース（置き自転車など）があっても爺は待つだけ——プレイヤー判断へ
            return ("STOP", node)
        return ("STOP", node)


# ---------------------------------------------------------------- ソルバQA（§10.8 / puzzle-generation §7）
# 行動（1手）: ピースを置く（予算=PIECE_COST）/ 岩をどかす（1）/ 撤去（0）
# free_place=False: 配置先は停止中のノードのみ。True: 盤面の任意ノード（実ゲーム寄り）
def solve(prof: DifficultyProfile, max_moves: int, max_states: int = 200_000) -> tuple[int | None, list, Engine]:
    """最小手数と手順を返す。予算内で解けるかの証明を兼ねる（全探索・Dijkstra）"""
    import heapq
    board = Board.build(prof)
    base = Engine(board, prof, prof.start, "E", prof.gauge, waiting=prof.start_wait)
    placed0 = {n: Piece("BIKE", None) for n in prof.forced_bikes}
    for n, kind in prof.env_pieces:
        placed0[n] = Piece(kind, None)
    st0, _ = base.run_until_stop(placed0)
    if st0 == "WIN":
        return 0, [], base
    if st0 != "STOP":
        return None, [], base

    def key_of(eng: Engine, placed: dict) -> tuple:
        return (eng.pos, eng.heading, eng.gauge, eng.waiting,
                eng.hachi_used, eng.map_used,
                frozenset(eng.moved_rocks), frozenset(eng.liar_met),
                frozenset(placed.items()))

    def place_targets(eng: Engine, placed: dict) -> list:
        """配置先。free_place=False: 停止中のノードのみ。
        True: 停止ノード + 未学習の悪いこのいる角（D32カウンタ用の先置き）。
        全面自由配置は探索空間が爆発するため絞る（生成器はこれで十分検証可能）"""
        node = eng.pos
        if not prof.free_place:
            return [node]
        out = [node]
        for n, p in placed.items():
            if p.kind == "BA" and n not in eng.liar_met and n != node:
                out.append(n)
        return out

    def expand(eng: Engine, placed: dict, used: int):
        """停止状態 eng からの1手 → (手数, Engine, placed dict, action) の列"""
        node = eng.pos
        for kind in prof.pieces:
            cost = PIECE_COST[kind]
            if used + cost > max_moves:
                continue
            for t in place_targets(eng, placed):
                cur = placed.get(t)
                if cur is not None and not (cur.kind == "BA" and kind in ("GO", "COP", "JK")):
                    continue  # 1スロット1ピース。例外: 未学習の悪いこは人ピースで無効化（D32）
                dir_options = ([d for d in DIRS
                                if board.has_edge(t, (t[0] + DELTA[d][0], t[1] + DELTA[d][1]))]
                               if kind == "JK" else [None])
                for d in dir_options:
                    p2 = dict(placed)
                    p2[t] = Piece(kind, d)
                    yield cost, eng.clone(), p2, (t, kind, d)
        # 岩をどかす（停止ノードに隣接する岩、1手）
        if used + 1 <= max_moves:
            for d in DIRS:
                dx, dy = DELTA[d]
                m = (node[0] + dx, node[1] + dy)
                key = frozenset((node, m))
                if key in board.rocks and key not in eng.moved_rocks:
                    e2 = eng.clone()
                    e2.moved_rocks.add(key)
                    e2.log.append(f"  ▶ 岩をどかした（{node}→{m} 方向）")
                    yield 1, e2, dict(placed), (node, "ROCK", d)

    # 初期化: 開始→最初の停止まで進める
    if base.pos == prof.goal:
        return 0, [], base
    pq = [(0, 0, base, placed0, [])]   # (手数, 通し番号, Engine, placed, actions)
    seen = {key_of(base, placed0)}
    serial = 1
    while pq:
        used, _, eng, placed, actions = heapq.heappop(pq)
        if eng.pos == prof.goal:
            return used, actions, eng
        if len(seen) > max_states:
            return None, [], eng  # 探索打ち切り（証明不能として扱う）
        for cost, e2, p2, act in expand(eng, placed, used):
            e3 = e2
            st, _ = e3.run_until_stop(p2)
            if st == "WIN":
                if used + cost <= max_moves:
                    return used + cost, actions + [act], e3
                continue
            if st != "STOP":
                continue
            k = key_of(e3, p2)
            if k in seen:
                continue
            seen.add(k)
            heapq.heappush(pq, (used + cost, serial, e3, p2, actions + [act]))
            serial += 1
    return None, [], base


def replay2(prof: DifficultyProfile, actions: list):
    board = Board.build(prof)
    eng = Engine(board, prof, prof.start, "E", prof.gauge, waiting=prof.start_wait)
    placed: dict = {n: Piece("BIKE", None) for n in prof.forced_bikes}
    for n, kind in prof.env_pieces:
        placed[n] = Piece(kind, None)
    status, info = eng.run_until_stop(placed)
    for node, kind, d in actions:
        assert status == "STOP", f"手順エラー: {status} @ {eng.pos}"
        if kind == "ROCK":
            dx, dy = DELTA[d]
            key = frozenset((node, (node[0] + dx, node[1] + dy)))
            assert key in board.rocks, f"手順エラー: {node}→{d} に岩がない"
            eng.moved_rocks.add(key)
            print(f"  ▶ 岩をどかした（{node}→{d} 方向）")
        else:
            assert prof.free_place or eng.pos == node, \
                f"手順エラー: {node} で置くべき（今 {eng.pos}）"
            placed[node] = Piece(kind, d)
            print(f"  ▶ {PIECE_NAME[kind]}を {node} に配置" + (f"（{d} 向き）" if d else ""))
        status, info = eng.run_until_stop(placed)
        for line in eng.log:
            print(line)
        eng.log.clear()
    assert status == "WIN", f"再生に失敗: {status} {info}"
    return eng, info


# ---------------------------------------------------------------- 表示
_PIECE_MARK = {"JK": "j", "COP": "c", "BIKE": "b", "GO": "g", "BA": "?", "AR": ">", "AL": "<"}


def print_board(prof: DifficultyProfile, placed: dict) -> None:
    W, H = prof.size
    env = {n: k for n, k in prof.env_pieces}
    rock_edges = {frozenset(r) for r in prof.rocks}
    print("   " + " ".join(str(x) for x in range(W)))
    for y in range(H):
        row = []
        for x in range(W):
            n = (x, y)
            if n == prof.goal:
                c = "G"
            elif n == prof.start:
                c = "S"
            elif n == prof.forced_hachi:
                c = "H"
            elif n == prof.forced_autocross:
                c = "A"
            elif n in prof.plazas:
                c = "P"
            elif n in placed or n in env:
                k = placed[n].kind if n in placed else env[n]
                c = _PIECE_MARK.get(k, "*")
            elif n in (prof.node_names or {}):
                c = "o"
            else:
                c = "."
            # 岩（右・下の隣接辺）を表示の一部に
            if frozenset((n, (x + 1, y))) in rock_edges:
                c += "#"
            else:
                c += " "
            row.append(c)
        print(f" {y} " + "".join(row))
    print("  S=出発 G=駅員さん A=点字交差点 H=ハチ P=広場 g=正しいこ ?=悪いこ c=お巡りさん"
          " >=右矢印 <=左矢印 b=自転車 j=女子高生 #=岩 o=交差点")
    for n, name in sorted((prof.node_names or {}).items()):
        print(f"   {n}: {name}")


# ---------------------------------------------------------------- ゲーム進行
def _all_stages() -> list:
    """全ステージを進行順にフラット化する"""
    out = []
    for book_name in ("intro", "marunouchi", "quiz"):
        for no in sorted(BOOKS[book_name]):
            out.append((book_name, no, BOOKS[book_name][no]))
    return out


def run_game() -> int:
    """ステージ進行つきゲームモード（引数なしで起動した場合のデフォルト）"""
    stages = _all_stages()
    cleared = set()
    print("=" * 40)
    print("  リアルフェイクタウン")
    print("  点字ブロックで、街を読み、人に導かれる")
    print("=" * 40)

    while True:
        # ステージ選択
        print(f"\n{'─' * 40}")
        print(f"  クリア: {len(cleared)}/{len(stages)}")
        print(f"{'─' * 40}")
        for i, (book, no, prof) in enumerate(stages):
            key = f"{book}:{no}"
            if key in cleared:
                mark = "☆"
            elif i == len(cleared):
                mark = "▶"
            elif i < len(cleared):
                mark = "☆"
            else:
                mark = "··"
            print(f"  {i + 1:2d}. {mark} [{book[:4]}] {prof.name}")

        choice = input("\nステージ番号（q=終了）: ").strip()
        if choice == "q":
            print("お疲れさまでした！")
            return 0
        try:
            idx = int(choice) - 1
        except ValueError:
            continue
        if idx < 0 or idx >= len(stages):
            continue
        if idx > len(cleared):
            print("  前のステージを先にクリアしてください")
            continue

        book_name, no, prof = stages[idx]
        win = _play_stage(prof)
        if win:
            cleared.add(f"{book_name}:{no}")
            print("\n  ☆☆☆ クリア！お疲れさまでした ☆☆☆")
            if len(cleared) == len(stages):
                print("\n  全ステージクリア！ありがとう！")
                return 0
        else:
            print("\n  帰宅……もう一度挑戦しましょう")
            retry = input("  リトライ？（y/n）: ").strip().lower()
            if retry != "y":
                continue
            # リトライ（same stage再プレイ）
            win = _play_stage(prof)
            if win:
                cleared.add(f"{book_name}:{no}")


def _play_stage(prof: DifficultyProfile) -> bool:
    """1ステージを対局プレイし、勝利で True を返す"""
    board = Board.build(prof)
    eng = Engine(board, prof, prof.start, "E", prof.gauge, waiting=prof.start_wait)
    placed: dict = {n: Piece("BIKE", None) for n in prof.forced_bikes}
    for n, kind in prof.env_pieces:
        placed[n] = Piece(kind, None)
    env_nodes = set(placed)
    kp_left = prof.kp
    print(f"\n  「{prof.name}」 {prof.note}")
    print(f"  KP={prof.kp} 元気={prof.gauge}")
    print(f"  コマンド: p <x,y> <種類> [向き] / push <x,y> <向き> / r <x,y> / go / q")

    status, info = eng.run_until_stop(placed)
    while True:
        for line in eng.log:
            print(line)
        eng.log.clear()
        print(f"\n  --- 停止中 {eng.pos}（元気 {eng.gauge} / KP {kp_left}）{info or ''}")
        print_board(prof, placed)
        if status == "WIN":
            return True
        if status == "LOSE":
            print(f"  帰宅……（{info}）")
            return False
        try:
            cmd = input("  > ").strip()
        except EOFError:
            return False
        if cmd == "q":
            return False
        if cmd == "go":
            status, info = eng.run_until_stop(placed)
            continue
        parts = cmd.split()
        if parts[0] == "p" and len(parts) >= 3:
            try:
                x, y = map(int, parts[1].split(","))
            except ValueError:
                print("座標は x,y 形式")
                continue
            node = (x, y)
            kind = parts[2].upper()
            if kind not in PIECE_COST or kind not in prof.pieces:
                print("そのピースは持っていません")
                continue
            cur = placed.get(node)
            if cur is not None and not (cur.kind == "BA" and kind in ("GO", "COP", "JK")):
                print("既にピースがあります")
                continue
            if not prof.free_place and node != eng.pos:
                print("停止中の交差点にしか置けません")
                continue
            if not board.in_bounds(node) or node not in board.dist:
                print("道から離れています")
                continue
            if PIECE_COST[kind] > kp_left:
                print("KPが足りません")
                continue
            d = None
            if kind == "JK":
                d = parts[3].upper() if len(parts) > 3 else "E"
                if d not in DIRS:
                    print("向きは E/S/W/N")
                    continue
                dx, dy = DELTA[d]
                if not board.has_edge(node, (node[0] + dx, node[1] + dy)):
                    print("その向きに道がありません（D23）")
                    continue
            if cur is not None and cur.kind == "BA":
                print("  （悪いこは人の声で無効化された・D32）")
            placed[node] = Piece(kind, d)
            kp_left -= PIECE_COST[kind]
            print(f"  配置した（KP残り {kp_left}）")
        elif parts[0] == "push" and len(parts) == 3:
            try:
                x, y = map(int, parts[1].split(","))
            except ValueError:
                print("座標は x,y 形式")
                continue
            node = (x, y)
            if node != eng.pos:
                print("いる場所の隣の岩しかどかせません")
                continue
            d = parts[2].upper()
            if d not in DIRS:
                print("向きは E/S/W/N")
                continue
            key = frozenset((node, (node[0] + DELTA[d][0], node[1] + DELTA[d][1])))
            if key not in board.rocks or key in eng.moved_rocks:
                print("そこに岩はありません")
                continue
            if kp_left < 1:
                print("KPが足りません")
                continue
            eng.moved_rocks.add(key)
            kp_left -= 1
            print(f"  岩をどかした（KP残り {kp_left}）")
        elif parts[0] == "r" and len(parts) == 2:
            try:
                x, y = map(int, parts[1].split(","))
            except ValueError:
                continue
            node = (x, y)
            if node in env_nodes:
                print("環境ピースは撤去できません")
                continue
            if node in placed:
                kp_left += PIECE_COST[placed.pop(node).kind]
                print(f"  撤去した（KP残り {kp_left}）")
        else:
            print("コマンド: p <x,y> <種類> [向き] / push <x,y> <向き> / r <x,y> / go / q")


def run_demo(stages: dict) -> int:
    """全ステージをソルバで解いて自動プレイする"""
    ok = True
    for no in sorted(stages):
        prof = stages[no]
        print(f"\n=== ステージ{no}「{prof.name}」 ===")
        print(f"  {prof.note}")
        cost, actions, _ = solve(prof, prof.kp)
        if cost is None:
            print("  [NG] 予算内で解けません（ソルバQA失敗）")
            ok = False
            continue
        print(f"  [ソルバQA] 最小手数 = {cost}（KP予算 {prof.kp} 以内 ✓）")
        print("  --- 自動プレイ ---")
        print_board(prof, {})
        eng, info = replay2(prof, actions)
        print(f"  [{info}] 元気残り {eng.gauge}")
        if eng.pos == prof.goal:
            print("  [WIN] ✓")
        else:
            ok = False
    print("\n全ステージ: " + ("OK ✓" if ok else "失敗あり ✗"))
    return 0 if ok else 1


def status_ok(eng: Engine, info: str) -> bool:
    return eng.pos == eng.prof.goal


def run_solve(no: int, stages: dict) -> int:
    prof = stages[no]
    cost, actions, _ = solve(prof, prof.kp)
    if cost is None:
        print(f"ステージ{no}: 予算 {prof.kp} 内で解けません（証明）")
        return 1
    print(f"ステージ{no}「{prof.name}」: 最小手数 = {cost}（予算 {prof.kp}、N-1手では不成立を全探索で確認）")
    for node, kind, d in actions:
        if kind == "ROCK":
            print(f"  - {node} から {d} 方向の岩をどかす")
        else:
            print(f"  - {node} に {PIECE_NAME[kind]}" + (f"（{d} 向き）" if d else ""))
    return 0


def run_play(no: int, stages: dict) -> int:
    prof = stages[no]
    board = Board.build(prof)
    eng = Engine(board, prof, prof.start, "E", prof.gauge, waiting=prof.start_wait)
    placed: dict = {}
    kp_left = prof.kp
    print(f"ステージ{no}「{prof.name}」 {prof.note}")
    print(f"コマンド: p <x,y> <JK|COP> [E|S|W|N] / r <x,y> / go / map / q")
    status, info = eng.run_until_stop(placed)
    while True:
        for line in eng.log:
            print(line)
        eng.log.clear()
        print(f"\n--- お爺ちゃんは {eng.pos} で停止中（元気 {eng.gauge} / KP {kp_left}）{info or ''}")
        print_board(prof, placed)
        if status == "WIN":
            print("クリア！お疲れさまでした。")
            return 0
        if status == "LOSE":
            print(f"帰宅……（{info}）リトライしてください")
            return 1
        try:
            line = input("> ").strip()
        except EOFError:
            return 1
        if line == "q":
            return 0
        if line == "map":
            continue
        if line == "go":
            status, info = eng.run_until_stop(placed)
            continue
        parts = line.split()
        if parts[0] == "p" and len(parts) >= 3:
            x, y = map(int, parts[1].split(","))
            node = (x, y)
            kind = parts[2].upper()
            if kind not in PIECE_COST or kind not in prof.pieces:
                print("そのピースは持っていません")
                continue
            if node in placed:
                print("そこには既にピースがあります")
                continue
            if node not in board.dist:
                print("そこは道から離れています")
                continue
            if PIECE_COST[kind] > kp_left:
                print("KPが足りません")
                continue
            d = None
            if kind == "JK":
                d = parts[3].upper() if len(parts) > 3 else "E"
                if d not in DIRS:
                    print("向きは E/S/W/N")
                    continue
                dx, dy = DELTA[d]
                if not board.has_edge(node, (node[0] + dx, node[1] + dy)):
                    print("その向きに道がありません（宣言型方向・D23）")
                    continue
            placed[node] = Piece(kind, d)
            kp_left -= PIECE_COST[kind]
            print(f"配置した（KP残り {kp_left}）")
        elif parts[0] == "r" and len(parts) == 2:
            x, y = map(int, parts[1].split(","))
            node = (x, y)
            if node in placed:
                kp_left += PIECE_COST[placed.pop(node).kind]
                print(f"撤去した（KP残り {kp_left}）")
        else:
            print("コマンド: p <x,y> <JK|COP> [向き] / r <x,y> / go / map / q")


def main() -> int:
    ap = argparse.ArgumentParser(description="リアルフェイクタウン")
    ap.add_argument("--profiles", action="store_true", help="プロファイル一覧")
    ap.add_argument("--demo", action="store_true", help="全ステージ自動プレイ")
    ap.add_argument("--solve", type=int, metavar="N", help="ステージNの最小手数を証明")
    ap.add_argument("--stage", type=int, metavar="N", help="ステージNを対局プレイ")
    ap.add_argument("--book", choices=sorted(BOOKS), default=None,
                    help="intro / marunouchi / quiz (デフォルト: 全部)")
    args = ap.parse_args()

    if args.demo:
        stages = BOOKS[args.book] if args.book else MARUNOUCHI_STAGES
        return run_demo(stages)
    if args.solve is not None:
        stages = BOOKS[args.book] if args.book else MARUNOUCHI_STAGES
        return run_solve(args.solve, stages)
    if args.stage is not None:
        stages = BOOKS[args.book] if args.book else MARUNOUCHI_STAGES
        return run_play(args.stage, stages)
    if args.profiles:
        for book_name in sorted(BOOKS):
            for no in sorted(BOOKS[book_name]):
                p = BOOKS[book_name][no]
                print(f"[{book_name}] ステージ{no}「{p.name}」 {p.size[0]}x{p.size[1]} KP={p.kp}")
        return 0

    # デフォルト: ゲームモード
    return run_game()


if __name__ == "__main__":
    sys.exit(main())
