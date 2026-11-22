using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace RealFakeTown.Sim
{
    /// <summary>導入ブック（3ステージ）</summary>
    public static class IntroBook
    {
        public static StageProfile Build(int no)
        {
            switch (no)
            {
                case 2:
                    var p2 = new StageProfile
                    {
                        Name = "おまわりさんのいる交差点", W = 4, H = 3,
                        Start = new Node(0, 0), Goal = new Node(3, 2),
                        Gauge = 40, Kp = 6, Note = "導入2: 方向指定できないピース（お巡りさん）と点字つき交差点。",
                    };
                    p2.Events[new Node(1, 1)] = NodeEvent.BrailleCross;
                    return p2;
                case 3:
                    var p3 = new StageProfile
                    {
                        Name = "ハチの右", W = 4, H = 4,
                        Start = new Node(0, 0), Goal = new Node(2, 2),
                        Gauge = 50, Kp = 4, StartWait = false,
                        Note = "導入3: 強制イベント（ハチの必ず右）の読み。",
                    };
                    p3.Events[new Node(1, 1)] = NodeEvent.Hachi;
                    p3.Edges = new List<Node[]> {
                        new[] { new Node(0,0), new Node(1,0) }, new[] { new Node(0,0), new Node(0,1) },
                        new[] { new Node(1,0), new Node(1,1) }, new[] { new Node(0,1), new Node(1,1) },
                        new[] { new Node(1,1), new Node(2,1) }, new[] { new Node(1,1), new Node(1,2) },
                        new[] { new Node(2,1), new Node(3,1) }, new[] { new Node(1,2), new Node(1,3) },
                        new[] { new Node(2,1), new Node(2,2) },
                    };
                    return p3;
                default:
                    return new StageProfile
                    {
                        Name = "まっすぐ道を渡って", W = 3, H = 3,
                        Start = new Node(0, 0), Goal = new Node(2, 2),
                        Gauge = 30, Kp = 3,
                        Note = "導入1: 女子高生のみ。開始は指示待ち（D18）。",
                    };
            }
        }

        public static StageProfile BuildWithPieces(int no)
        {
            var p = Build(no);
            p.Pieces = no switch { 2 => new[] { "JK", "COP" }, _ => new[] { "JK" } };
            return p;
        }
    }

    /// <summary>クイズブック（5ステージ）</summary>
    public static class QuizBook
    {
        public static StageProfile Build(int no)
        {
            var p = MarunouchiBook.Build(no <= 3 ? no : no - 2);  // marunouchi 1-3 をベースに再利用
            p.Name = no switch
            {
                1 => "Q1: まっすぐ進む",
                2 => "Q2: 広場でお巡りさん",
                3 => "Q3: ハチの右を受け止める",
                4 => "Q4: 置き自転車の差し替え",
                _ => "Q5: ハチと亀裂と広場",
            };
            p.Pieces = no switch
            {
                1 => new[] { "JK" },
                2 => new[] { "COP" },
                3 => new[] { "JK", "COP" },
                4 => new[] { "JK", "COP", "BIKE" },
                _ => new[] { "JK", "FR", "FL" },
            };
            p.Note = "[クイズ] メカニクスの総合テスト。難易度: " + (no <= 2 ? "易" : no <= 4 ? "中" : "高");
            if (no == 5) { p.Events[new Node(2, 1)] = NodeEvent.CrackedCross; p.Events[new Node(1, 1)] = NodeEvent.Hachi; }
            return p;
        }
    }

    /// <summary>全ブックへの統合アクセス</summary>
    public static class GameBooks
    {
        public static (string bookName, int stageNo, StageProfile prof)[] GetAllStages()
        {
            var list = new List<(string, int, StageProfile)>();
            for (var i = 1; i <= 3; i++) list.Add(("intro", i, IntroBook.BuildWithPieces(i)));
            for (var i = 1; i <= 4; i++) list.Add(("marunouchi", i, MarunouchiBook.Build(i)));
            for (var i = 1; i <= 5; i++) list.Add(("quiz", i, QuizBook.Build(i)));
            // OSM 実街路ブック（JSON が読めない環境では null になり追加されない）
            try
            {
                var osm1 = OsmGraph.BuildStage(1);
                if (osm1 != null) list.Add(("osm", 1, osm1));
                var osm2 = OsmGraph.BuildStage(2);
                if (osm2 != null) list.Add(("osm", 2, osm2));
            }
            catch (Exception)
            {
                // StreamingAssets が無い環境でも他のブックは遊べるようにする
            }
            return list.ToArray();
        }
    }

    /// <summary>
    /// C#単体で完結するゲームループ。Unity の -executeMethod から呼び出すか、
    /// dotnet run でコンソールアプリとして起動する。
    /// </summary>
    public static class GameRunner
    {
        public static void Start()
        {
            var stages = GameBooks.GetAllStages();
            var cleared = new HashSet<int>();
            Console.WriteLine("╔══════════════════════════════════════╗");
            Console.WriteLine("║     リアルフェイクタウン              ║");
            Console.WriteLine("║   点字ブロックで、街を読み、          ║");
            Console.WriteLine("║   人に導かれる                        ║");
            Console.WriteLine("╚══════════════════════════════════════╝");

            while (true)
            {
                Console.WriteLine($"\n── クリア: {cleared.Count}/{stages.Length} ──");
                for (var i = 0; i < stages.Length; i++)
                {
                    var (book, no, prof) = stages[i];
                    string mark;
                    if (cleared.Contains(i)) mark = "☆";
                    else if (i == cleared.Count) mark = "▶";
                    else if (i < cleared.Count) mark = "☆";
                    else mark = "··";
                    Console.WriteLine($"  {i + 1,2}. {mark} [{book}] {prof.Name}");
                }
                Console.Write("\nステージ番号 (q=終了): ");
                var input = Console.ReadLine();
                if (input?.Trim().ToLower() == "q") { Console.WriteLine("お疲れさまでした！"); return; }
                if (!int.TryParse(input, out var idx) || idx < 1 || idx > stages.Length) continue;
                if (idx - 1 > cleared.Count) { Console.WriteLine("前のステージを先にクリアしてください"); continue; }

                var (b, n, pr) = stages[idx - 1];
                var win = PlayStage(pr);
                if (win)
                {
                    cleared.Add(idx - 1);
                    Console.WriteLine("\n  ☆☆☆ クリア！お疲れさまでした ☆☆☆");
                    if (cleared.Count == stages.Length) { Console.WriteLine("\n  全ステージクリア！"); return; }
                }
                else Console.WriteLine("\n  帰宅……もう一度挑戦しましょう");
            }
        }

        static bool PlayStage(StageProfile prof)
        {
            var board = Board.Build(prof);
            var world = new WorldSide(board, prof);
            var judge = new GrandpaJudge();
            var placed = new Placements();
            var kp = prof.Kp;
            Console.WriteLine($"\n  「{prof.Name}」 {prof.Note}");
            Console.WriteLine($"  KP={kp} 元気={prof.Gauge}");
            Console.WriteLine("  p <x,y> <JK|COP|BIKE|FR|FL> [向き] / r <x,y> / go / q");

            while (true)
            {
                var a = world.PerceiveArrival(placed);
                var v = judge.Judge(a);
                var status = world.Apply(placed, v);

                if (status == "WIN") { Console.WriteLine("  クリア！"); return true; }
                if (status == "LOSE") { Console.WriteLine($"  帰宅…… ({v.Reason})"); return false; }
                if (v.Kind == VerdictKind.Wait)
                {
                    Console.WriteLine($"\n  --- 停止中 {world.Pos}（元気 {world.Gauge} / KP {kp}）");
                    PrintBoard(board, prof, placed);
                    Console.Write("  > ");
                    var line = Console.ReadLine();
                    if (line == null || line.Trim() == "q") return false;
                    var parts = line.Trim().Split(' ');
                    if (parts.Length >= 3 && parts[0] == "p")
                    {
                        var coords = parts[1].Split(',');
                        var node = new Node(int.Parse(coords[0]), int.Parse(coords[1]));
                        var kindStr = parts[2].ToUpper();
                        var kind = kindStr switch
                        {
                            "JK" => PieceKind.Jk, "COP" => PieceKind.Cop,
                            "BIKE" => PieceKind.Bike, "FR" => PieceKind.Fr,
                            "FL" => PieceKind.Fl, _ => (PieceKind?)null
                        };
                        if (kind == null) { Console.WriteLine("不明なピース"); continue; }
                        Dir dir = Dir.E;
                        if (kind == PieceKind.Jk && parts.Length > 3)
                            Enum.TryParse(parts[3].ToUpper(), out dir);
                        placed.Place(node, new Piece(kind.Value, dir));
                        Console.WriteLine($"  配置した");
                    }
                    else if (parts.Length == 2 && parts[0] == "r")
                    {
                        var coords = parts[1].Split(',');
                        placed.Remove(new Node(int.Parse(coords[0]), int.Parse(coords[1])));
                        Console.WriteLine("  撤去した");
                    }
                }
            }
        }

        static void PrintBoard(Board board, StageProfile prof, Placements placed)
        {
            Console.Write("   ");
            for (var x = 0; x < prof.W; x++) Console.Write(x + " ");
            Console.WriteLine();
            for (var y = 0; y < prof.H; y++)
            {
                Console.Write($" {y} ");
                for (var x = 0; x < prof.W; x++)
                {
                    var n = new Node(x, y);
                    if (n.Equals(prof.Goal)) Console.Write("G ");
                    else if (n.Equals(prof.Start)) Console.Write("S ");
                    else if (prof.Events.ContainsKey(n)) Console.Write("E ");
                    else if (prof.Plazas.Contains(n)) Console.Write("P ");
                    else if (placed.TryGet(n, out var pc)) Console.Write(pc.Kind == PieceKind.Jk ? "j " : pc.Kind == PieceKind.Cop ? "c " : "b ");
                    else Console.Write(". ");
                }
                Console.WriteLine();
            }
        }
    }

    /// <summary>Unity -executeMethod 用エントリポイント。</summary>
    public static class GameEntry
    {
        /// <summary>-executeMethod RealFakeTown.Sim.GameEntry.RunGame</summary>
        public static void RunGame() => GameRunner.Start();

        /// <summary>-executeMethod RealFakeTown.Sim.GameEntry.RunSimulation
        /// 全ステージをヘッドレスで実行し、シミュコアの動作を検証する。</summary>
        public static void RunSimulation()
        {
            var log = new System.Text.StringBuilder();
            var allOk = true;

            // Stage 1: ピースなしでまっすぐ進む（start_wait=false）
            var s1 = MarunouchiBook.Build(1);
            var r1 = Simulator.Run(s1, new Placements());
            log.AppendLine($"S1「{s1.Name}」: {(r1.Win ? "PASS" : "FAIL")} — 0手クリア（直進優先のみ）");
            if (!r1.Win) allOk = false;

            // Stage 2: COP を広場に置いて案内してもらう
            var s2 = MarunouchiBook.Build(2);
            var p2 = new Placements();
            p2.Place(new Node(3, 1), new Piece(PieceKind.Cop, Dir.E));
            var r2 = Simulator.Run(s2, p2);
            log.AppendLine($"S2「{s2.Name}」: {(r2.Win ? "PASS" : "FAIL")} — COP配置で案内（1手）");
            if (!r2.Win) allOk = false;

            // Stage 3: ハチの強制右に従ってゴールへ
            var s3 = MarunouchiBook.Build(3);
            var p3 = new Placements();
            p3.Place(new Node(0, 1), new Piece(PieceKind.Jk, Dir.E));
            var r3 = Simulator.Run(s3, p3);
            log.AppendLine($"S3「{s3.Name}」: {(r3.Win ? "PASS" : "FAIL")} — ハチの右が正解ルート");
            if (!r3.Win) allOk = false;

            // Stage 4: 置き自転車で点字無効＋人の案内で迂回
            var s4 = MarunouchiBook.Build(4);
            var p4 = new Placements();
            p4.Place(new Node(3, 1), new Piece(PieceKind.Jk, Dir.E));
            var r4 = Simulator.Run(s4, p4);
            log.AppendLine($"S4「{s4.Name}」: {(r4.Win ? "PASS" : "FAIL")} — 自転車で点字無効、直進ルートで到達");
            if (!r4.Win) allOk = false;

            log.AppendLine(allOk ? "=== ALL_PASS ===" : "=== FAILED ===");
            Debug.Log(log.ToString());
            System.IO.File.WriteAllText("/tmp/rft-simulation-result.txt", log.ToString());
        }
    }
}
