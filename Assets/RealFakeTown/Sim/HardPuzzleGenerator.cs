using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace RealFakeTown.Sim
{
    // ------------------------------------------------------------ 技の定義
    public enum TrickMechanic { ChildRevisit, LiarDetour, DogRedirect, BrailleSuppress }

    /// <summary>逆算生成の入力: どの技をどこで発動させるか。</summary>
    public sealed class TrickSpec
    {
        public TrickMechanic Mechanic;
        public Node TriggerNode;         // 技の発火位置
        public Dir DeclaredDir;          // 子供の宣言方向（グリッド盤用）
        public Node? DeclaredAim;        // 子供の連れ帰り先ノード（任意グラフ用・優先）
        public List<Node> TrickPath = new();   // 技を使った解の経路（ノード列）
        public List<Node> FallbackPath = new(); // 技を使わない経路（=閉鎖対象）
    }

    /// <summary>生成結果。</summary>
    public sealed class GeneratedPuzzle
    {
        public bool Success;
        public string Message = "";
        public int MinMoves;
        public bool TrickNecessary;      // 技が必須であることの証明済み
        public List<Node> ClosedEdges = new(); // 閉鎖した辺のログ
        public List<string> Log = new();
    }

    /// <summary>
    /// 逆算生成アルゴリズム（docs/puzzle-generation.md §5.5）。
    /// 技を先に決め、その技が必須になるように盤面を逆算する。
    /// </summary>
    public static class HardPuzzleGenerator
    {
        /// <summary>
        /// 逆算生成の本体。
        /// 1. 技のトリガーを配置
        /// 2. FallbackPath を閉鎖（岩・地割れ）
        /// 3. 反実仮想検証（技無効で解けるか）
        /// 4. 認証（N手で解ける/N−1手で解けない）
        /// </summary>
        public static GeneratedPuzzle Generate(StageProfile baseProfile, TrickSpec trick, int targetMoves)
        {
            var result = new GeneratedPuzzle();
            var log = new List<string>();
            var prof = CloneProfile(baseProfile);
            prof.Events[trick.TriggerNode] = trick.Mechanic switch
            {
                TrickMechanic.ChildRevisit => NodeEvent.Child,
                TrickMechanic.LiarDetour => NodeEvent.Liar,
                _ => NodeEvent.None
            };
            if (trick.Mechanic == TrickMechanic.ChildRevisit)
            {
                prof.ChildDir = trick.DeclaredDir;
                prof.ChildAim = trick.DeclaredAim;   // 任意グラフでは隣ノード指定が優先
            }

            // --- Step C: FallbackPath 上の「技を使わない直接ルート」を岩で塞ぐ
            var closed = CloseDirectRoute(prof, trick, log);
            result.ClosedEdges.AddRange(closed);

            // --- Step D: 反実仮想検証
            log.Add("--- 反実仮想: 技ありで解く ---");
            var withTrick = PuzzleSolver.SolveMinMoves(prof, new Placements(), targetMoves + 2);
            log.Add($"  技あり min = {withTrick.MinMoves?.ToString() ?? "詰み"}");

            // 技を無効化して解き直す（トリガーノードを削除）
            var noTrickProf = CloneProfile(prof);
            noTrickProf.Events.Remove(trick.TriggerNode);
            log.Add("--- 反実仮想: 技なしで解く ---");
            var withoutTrick = PuzzleSolver.SolveMinMoves(noTrickProf, new Placements(), targetMoves + 2);
            log.Add($"  技なし min = {withoutTrick.MinMoves?.ToString() ?? "詰み"}");

            // 技必須性の判定
            bool trickNecessary;
            if (withTrick.MinMoves == null)
            {
                result.Success = false;
                result.Message = "技ありでも解けない（盤面設計エラー）";
                result.Log = log; return result;
            }
            if (withoutTrick.MinMoves == null)
                trickNecessary = true;   // 技なし=詰み → 技が必須
            else
                trickNecessary = withoutTrick.MinMoves > withTrick.MinMoves;  // 技なしの方が手数が増える → 技が有利

            log.Add($"  技必須 = {trickNecessary}");
            if (!trickNecessary)
            {
                log.Add("  [WARN] 技なしでも同難度。盤面の調整が必要");
            }

            // --- Step E: 認証
            log.Add("--- 認証 ---");
            var certified = PuzzleSolver.Certify(prof, new Placements(), targetMoves);
            log.Add($"  認証: {targetMoves}手で解ける={certified}");

            result.Success = certified;
            result.MinMoves = withTrick.MinMoves ?? 0;
            result.TrickNecessary = trickNecessary;
            result.Message = trickNecessary
                ? $"技「{trick.Mechanic}」が必須。min={result.MinMoves}"
                : "技は必須ではない（調整が必要）";
            result.Log = log;
            return result;
        }

        // ---------------------------------------------------------- FallbackPath の直接ルートを閉鎖
        static List<Node> CloseDirectRoute(StageProfile prof, TrickSpec trick, List<string> log)
        {
            var closed = new List<Node>();
            // TrickPath 上の辺を集合化（技経路の接頭辞は共有するので塞がない）
            var trickEdges = new HashSet<(Node, Node)>();
            for (var i = 0; i + 1 < trick.TrickPath.Count; i++)
            {
                var a = trick.TrickPath[i]; var b = trick.TrickPath[i + 1];
                trickEdges.Add(a.CompareTo(b) < 0 ? (a, b) : (b, a));
            }
            // FallbackPath の隣接ノードペアのうち、技経路に属さない辺だけを削除（岩として表現）
            for (var i = 0; i + 1 < trick.FallbackPath.Count; i++)
            {
                var a = trick.FallbackPath[i];
                var b = trick.FallbackPath[i + 1];
                var key = a.CompareTo(b) < 0 ? (a, b) : (b, a);
                if (trickEdges.Contains(key)) { log.Add($"  保持（技経路の共有辺）: {a}↔{b}"); continue; }
                prof.Edges.RemoveAll(e => e.Length == 2 &&
                    ((e[0].Equals(a) && e[1].Equals(b)) || (e[0].Equals(b) && e[1].Equals(a))));
                closed.Add(a);
                log.Add($"  閉鎖: {a}↔{b}");
            }
            return closed;
        }

        static StageProfile CloneProfile(StageProfile src)
        {
            var c = new StageProfile
            {
                Name = src.Name, Note = src.Note, W = src.W, H = src.H,
                Start = src.Start, Goal = src.Goal,
                Edges = src.Edges != null ? new List<Node[]>(src.Edges) : null,
                NodePos = src.NodePos != null ? new Dictionary<Node, Pos>(src.NodePos) : null,
                Gauge = src.Gauge, Kp = src.Kp, InitialMacho = src.InitialMacho,
                ChildDir = src.ChildDir, ChildAim = src.ChildAim,
                StartWait = src.StartWait, Pieces = src.Pieces,
            };
            foreach (var kv in src.Events) c.Events[kv.Key] = kv.Value;
            foreach (var b in src.Bikes) c.Bikes.Add(b);
            foreach (var pl in src.Plazas) c.Plazas.Add(pl);
            return c;
        }

        // ---------------------------------------------------------- デモ: 丸の内グラフで子供の再訪パズルを生成
        public static GeneratedPuzzle DemoChildRevisit()
        {
            var prof = new StageProfile
            {
                Name = "生成: 子供の再訪パズル",
                W = 5, H = 3,
                Start = new Node(0, 1),
                Goal = new Node(4, 1),
                Gauge = 60, Kp = 4,
                ChildDir = Dir.W,  // 子供は西（皇居方向）へ連れて行く
            };
            // 丸の内の辺を手動構築
            var edges = new List<Node[]>();
            var pairs = new (Node, Node)[] {
                (new Node(0,0), new Node(0,1)), (new Node(0,1), new Node(1,1)),
                (new Node(1,1), new Node(2,1)), (new Node(2,1), new Node(3,1)),
                (new Node(3,1), new Node(4,1)),
                (new Node(1,0), new Node(1,1)), (new Node(2,0), new Node(2,1)),
                (new Node(3,0), new Node(3,1)),
                (new Node(1,1), new Node(1,2)), (new Node(2,1), new Node(2,2)),
                (new Node(3,1), new Node(3,2)),
                (new Node(1,2), new Node(2,2)), (new Node(2,2), new Node(3,2)),
            };
            foreach (var (a, b) in pairs) edges.Add(new[] { a, b });
            prof.Edges = edges;

            // TrickSpec: 子供を (2,1) に配置。宣言方向=W（皇居方向）。
            var trick = new TrickSpec
            {
                Mechanic = TrickMechanic.ChildRevisit,
                TriggerNode = new Node(2, 1),
                DeclaredDir = Dir.W,
                TrickPath = new List<Node> {
                    new Node(0,1), new Node(1,1), new Node(2,1), new Node(1,1),
                    new Node(1,2), new Node(2,2), new Node(3,2), new Node(3,1), new Node(4,1)
                },
                FallbackPath = new List<Node> {
                    new Node(0,1), new Node(1,1), new Node(2,1), new Node(3,1), new Node(4,1)
                },
            };

            return Generate(prof, trick, targetMoves: 3);
        }
    }
}
