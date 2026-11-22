using System;
using System.Collections.Generic;

namespace RealFakeTown.Sim
{
    /// <summary>
    /// 丸の内ブック（皇居〜東京駅・実街路手組み盤）の C# 版ステージ定義。
    /// Python 版 tools/beginner_stage.py の MARUNOUCHI_STAGES と同じ盤面・同じv4ルール。
    /// 座標は 5x3 グリッド（方位角ベース任意グラフではその特殊ケースとして扱われる）。
    /// </summary>
    public static class MarunouchiBook
    {
        public static StageProfile Build(int no)
        {
            StageProfile p;
            switch (no)
            {
                case 2:
                    p = Base("行幸通り×仲通りのお巡りさん", 50, 6);
                    p.Events[new Node(2, 1)] = NodeEvent.BrailleCross;
                    p.Plazas.Add(new Node(3, 1));
                    break;
                case 3:
                    p = Base("ハチは行幸通りがお好き", 60, 5);
                    p.Events[new Node(2, 1)] = NodeEvent.Hachi;
                    p.Plazas.Add(new Node(3, 1));
                    break;
                case 4:
                    p = Base("点字をつぶす置き自転車", 50, 6);
                    p.Events[new Node(2, 1)] = NodeEvent.BrailleCross;
                    p.Bikes.Add(new Node(2, 1));
                    p.Plazas.Add(new Node(3, 1));
                    break;
                default:
                    p = Base("和田倉門から行幸通りを駅へ", 40, 3);
                    break;
            }
            return p;
        }

        static StageProfile Base(string name, int gauge, int kp)
        {
            var p = new StageProfile
            {
                Name = name,
                W = 5,
                H = 3,
                Start = new Node(0, 1),
                Goal = new Node(4, 1),
                Edges = MarunouchiEdges(),
                Gauge = gauge,
                Kp = kp,
                StartWait = false,   // 丸の内チュートリアルは開始指示待ちなし
            };
            return p;
        }

        public static List<Node[]> MarunouchiEdges()
        {
            var list = new List<Node[]>();
            list.Add(new[] { new Node(0, 0), new Node(0, 1) });  // お堀端
            list.Add(new[] { new Node(0, 1), new Node(1, 1) });  // 行幸通り
            list.Add(new[] { new Node(1, 1), new Node(2, 1) });
            list.Add(new[] { new Node(2, 1), new Node(3, 1) });
            list.Add(new[] { new Node(3, 1), new Node(4, 1) });
            list.Add(new[] { new Node(1, 0), new Node(1, 1) });  // 日比谷通り
            list.Add(new[] { new Node(1, 1), new Node(1, 2) });
            list.Add(new[] { new Node(2, 0), new Node(2, 1) });  // 丸の内仲通り
            list.Add(new[] { new Node(2, 1), new Node(2, 2) });
            list.Add(new[] { new Node(1, 0), new Node(2, 0) });  // 永代通り
            list.Add(new[] { new Node(2, 0), new Node(3, 0) });
            list.Add(new[] { new Node(3, 0), new Node(3, 1) });  // 駅前（北口）
            list.Add(new[] { new Node(3, 1), new Node(3, 2) });  // 駅前（南口）
            list.Add(new[] { new Node(1, 2), new Node(2, 2) });  // 晴海通り
            list.Add(new[] { new Node(2, 2), new Node(3, 2) });
            return list;
        }
    }

    /// <summary>
    /// 決定論スモークテスト。Unity Test Framework やエディタメニューから RunAll() を呼ぶ。
    /// バッチモードからは RunAllAndReport() を -executeMethod で呼ぶ。
    /// </summary>
    public static class SimSmoke
    {
        /// <summary>Unity -executeMethod 用エントリポイント。結果を /tmp/rft-smoke-result.txt に書く。</summary>
        public static void RunAllAndReport()
        {
            var sb = new System.Text.StringBuilder();
            try
            {
                var ok = RunAll(sb);
                sb.AppendLine("RESULT: " + (ok ? "ALL_PASS" : "FAIL"));
            }
            catch (Exception ex)
            {
                sb.AppendLine("EXCEPTION: " + ex.GetType().Name + " — " + ex.Message);
                sb.AppendLine(ex.StackTrace ?? "no stack");
            }
            System.IO.File.WriteAllText("/tmp/rft-smoke-result.txt", sb.ToString());
        }

        public static bool RunAll(System.Text.StringBuilder sb = null)
        {
            var log = sb ?? new System.Text.StringBuilder();
            var ok = true;
            ok &= ExpectWin(1, Placed(
                new Node(0, 1), PieceKind.Jk, Dir.E), log);
            ok &= ExpectWin(2, Placed(
                new Node(0, 1), PieceKind.Jk, Dir.E,
                new Node(3, 1), PieceKind.Jk, Dir.E), log);
            ok &= ExpectWin(3, Placed(
                new Node(0, 1), PieceKind.Jk, Dir.E,
                new Node(3, 1), PieceKind.Jk, Dir.E), log);
            ok &= ExpectWin(4, Placed(
                new Node(0, 1), PieceKind.Jk, Dir.E,
                new Node(3, 1), PieceKind.Jk, Dir.E), log);
            ok &= CheckOsm(log);
            ok &= CheckOsmDemo(log);
            return ok;
        }

        /// <summary>
        /// 5番目のチェック: OSM 実街路ステージの読込とシミュレーション。
        /// JSON が無い環境では SKIP として PASS（環境差を許容）。
        /// </summary>
        static bool CheckOsm(System.Text.StringBuilder sb)
        {
            var raw = OsmGraph.LoadRaw();
            if (raw == null || raw.NodeCount == 0)
            {
                sb.AppendLine("OSMステージ: SKIP（StreamingAssets/osm_marunouchi.json が無い環境）");
                return true;
            }
            var prof = OsmGraph.BuildStage(1);
            if (prof == null)
            {
                sb.AppendLine("OSMステージ: FAIL — BuildStage(1) が null");
                return false;
            }
            sb.AppendLine("OSMステージ「" + prof.Name + "」: ノード " + raw.NodeCount + "（>300 必須）");
            if (raw.NodeCount <= 300)
            {
                sb.AppendLine("OSMステージ: FAIL — ノード数が 300 以下");
                return false;
            }
            var placed = new Placements();
            var r = Simulator.Run(prof, placed);
            var line = "OSMステージ: Simulator.Run 完了 — " + (r.Win ? "WIN" : "LOSE — " + r.Status)
                + " (Steps=" + r.Steps + ")";
            sb.AppendLine(line);
            var ok = r.Steps > 0;
            if (!ok) sb.AppendLine("OSMステージ: FAIL — Steps=0");
            return ok;
        }

        /// <summary>
        /// 6番目のチェック: OSM コリドアからの逆算生成デモ。
        /// Success 不問（生成失敗も記録）だが、例外は FAIL。
        /// </summary>
        static bool CheckOsmDemo(System.Text.StringBuilder sb)
        {
            try
            {
                var g = OsmGraph.DemoGeneration();
                sb.AppendLine("OSMデモ生成: Success=" + g.Success
                    + ", MinMoves=" + g.MinMoves
                    + ", TrickNecessary=" + g.TrickNecessary
                    + ", ClosedEdges=" + g.ClosedEdges.Count
                    + " — " + g.Message);
                foreach (var l in g.Log) sb.AppendLine("  " + l);
                return true;
            }
            catch (Exception ex)
            {
                sb.AppendLine("OSMデモ生成: FAIL — 例外 " + ex.GetType().Name + ": " + ex.Message);
                return false;
            }
        }

        static Placements Placed(params object[] items)
        {
            var pl = new Placements();
            for (var i = 0; i + 2 < items.Length; i += 3)
            {
                var node = (Node)items[i];
                var kind = (PieceKind)items[i + 1];
                var dir = (Dir)items[i + 2];
                pl.Place(node, new Piece(kind, dir));
            }
            return pl;
        }

        static bool ExpectWin(int no, Placements placed, System.Text.StringBuilder sb)
        {
            var prof = MarunouchiBook.Build(no);
            var r = Simulator.Run(prof, placed);
            var line = "ステージ" + no + "「" + prof.Name + "」: " + (r.Win ? "WIN" : "FAIL — " + r.Status)
                + " (Steps=" + r.Steps + ", StartWait=" + prof.StartWait + ", Gauge=" + prof.Gauge + ")";
            sb.AppendLine(line);
            foreach (var l in r.Log) sb.AppendLine("  " + l);
            return r.Win;
        }
    }
}
