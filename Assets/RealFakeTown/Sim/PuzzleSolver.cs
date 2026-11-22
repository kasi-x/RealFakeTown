using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace RealFakeTown.Sim
{
    /// <summary>
    /// パズルソルバ: 最小手数の厳密探索と証明（docs/puzzle-generation.md §7）。
    /// 依存ライブラリ: なし（純C#）。
    ///
    /// 探索空間: A型「いつでも・どこでも配置」のゲームルールに一致させるため、
    /// お爺さんが各ノードに**到着するたび**に「そのノードに誘導ピースを置くか」を分岐する。
    /// 一度置いたピースは残る（永続配置）ので、後続の到着でも同じピースが効く。
    /// 配置コスト=1手。状態は「世界 + 配置済み集合 + 残り手数」でメモ化する。
    /// </summary>
    public static class PuzzleSolver
    {
        public sealed class SolveResult
        {
            public int? MinMoves;
            public List<(Node node, Piece piece)> Actions = new();
            public int StatesExplored;
        }

        /// <summary>
        /// 最小手数を反復深化DFSで厳密に探索する。
        /// 各ノード到着時に全ピース×全行き先の配置を分岐する。
        /// </summary>
        public static SolveResult SolveMinMoves(StageProfile prof, Placements seed, int maxMoves)
        {
            var result = new SolveResult();
            var board = Board.Build(prof);

            for (var limit = 1; limit <= maxMoves; limit++)
            {
                var world = new WorldSide(board, prof);
                var placed = seed.Clone();
                var memo = new HashSet<string>();
                var actions = new List<(Node, Piece)>();

                if (Dfs(world, placed, actions, limit, memo, board, result))
                {
                    result.MinMoves = limit;
                    result.Actions = actions;
                    return result;
                }
            }
            return result;
        }

        /// <summary>「target手で解ける／target−1手で解けない」を証明する。</summary>
        public static bool Certify(StageProfile prof, Placements seed, int target)
        {
            var atTarget = SolveMinMoves(prof, seed, target);
            if (atTarget.MinMoves == null || atTarget.MinMoves > target) return false;
            var atBelow = SolveMinMoves(prof, seed, target - 1);
            return atBelow.MinMoves == null || atBelow.MinMoves > target - 1;
        }

        // ------------------------------------------------------------ DFS
        // 「1手」=1ピース配置。各到着点で (a) 配置せず自律移動に任せる、(b) 1ピース配置して
        // その行き先へ誘導、の2系統を分岐する。配置は永続なので後続到着でも効く。
        static bool Dfs(WorldSide w, Placements placed, List<(Node, Piece)> actions,
                        int left, HashSet<string> memo, Board board, SolveResult result)
        {
            result.StatesExplored++;

            // 1ノード到着→移動を1回進める（配置分岐は「そのノードで効く1手」）。
            var a = w.PerceiveArrival(placed);
            var v = w.Judge(a);
            var status = w.Apply(placed, v);
            if (status == "WIN" || v.Kind == VerdictKind.Win) return true;
            if (status == "LOSE" || v.Kind == VerdictKind.Sealed) return false;
            if (w.Gauge <= 0) return false;

            // メモ化: 位置・向き・残り手数・配置済み集合をキーに。
            var key = w.Pos + "|" + w.Heading.ToString("0.###", CultureInfo.InvariantCulture)
                    + "|" + left + "|" + PlacementKey(placed);
            if (!memo.Add(key)) return false;

            // (a) 配置しないで自律に任せる分岐は、ループ上部の Apply 済みの移動が進んだ先で
            //     再帰的に継続する = ここでは「配置する」分岐だけを試す。
            //     ただし WaitPoint（広場・開始待ち）では配置が必須なので自律分岐は省略可。
            var atNode = w.Pos;
            var exits = board.Exits(atNode);
            if (left > 0)
            {
                foreach (var pk in new[] { PieceKind.Jk, PieceKind.Cop })
                {
                    foreach (var exit in exits)
                    {
                        // COP は駅方向矢印のみ（1候補）。それ以外の出口では JK と意味が重複しないよう許す。
                        if (pk == PieceKind.Cop && exit.To != board.ArrowNode(atNode)) continue;

                        var w2 = w.Clone();
                        var p2 = placed.Clone();
                        var piece = new Piece(pk, exit.To);
                        p2.Place(atNode, piece);
                        // 配置は即座にこのノードの誘導に効く（人がいれば呼び止め→案内）
                        var a2 = w2.PerceiveArrival(p2);
                        var v2 = w2.Judge(a2);
                        // 配置が向きを変えないなら手数の無駄（スキップして探索量を削る）
                        if (v2.Kind != VerdictKind.Move) continue;
                        if (v2.MoveTo == v.MoveTo) continue;   // 自律移動と同じ行き先 → 手数の無駄
                        var st2 = w2.Apply(p2, v2);

                        var act2 = new List<(Node, Piece)>(actions) { (atNode, piece) };
                        if (st2 == "WIN" || v2.Kind == VerdictKind.Win)
                        {
                            actions.Clear(); actions.AddRange(act2);
                            return true;
                        }
                        if (st2 == "LOSE" || v2.Kind == VerdictKind.Sealed) continue;

                        if (Dfs(w2, p2, act2, left - 1, memo, board, result))
                        {
                            actions.Clear(); actions.AddRange(act2);
                            return true;
                        }
                    }
                }
            }

            // (b) 配置しない（現在の移動のまま進む）: ここまで到達した状態で継続探索
            return Dfs(w, placed, actions, left, memo, board, result);
        }

        /// 配置済みピースの正準キー（決定論的ソート）。
        static string PlacementKey(Placements placed)
        {
            var sb = new StringBuilder();
            var list = new List<KeyValuePair<Node, Piece>>(placed.All);
            list.Sort((x, y) => x.Key.CompareTo(y.Key));
            foreach (var kv in list)
                sb.Append(kv.Key).Append('=').Append((int)kv.Value.Kind).Append(';');
            return sb.ToString();
        }

        static bool CheckTerminal(WorldSide w)
        {
            var a = w.PerceiveArrival(new Placements());
            return a.Kind == ArrivalKind.Goal;
        }
    }
}
