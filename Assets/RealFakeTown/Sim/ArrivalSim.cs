using System;
using System.Collections.Generic;
using System.Text;

namespace RealFakeTown.Sim
{
    /// <summary>
    /// 交差点到着時の処理（game-design §3 行動ルール v4）の決定論リファレンス実装。
    /// 「爺が側の判断（GrandpaJudge）」と「オブジェクト側（WorldSide: グラフ側で起きる変化）」を分離する。
    /// - WorldSide.PerceiveArrival(): 到着時の世界の変化を知覚スナップショット（Arrival）にする（発火順）
    /// - GrandpaJudge.Judge():        知覚だけを見て、判断順（点字＞犬正しい＞理性＞犬うそ）で行動を決める（純関数）
    /// - WorldSide.Apply():           判断を世界に適用する（移動・チケット/マッチョ消費・発火済みフラグ・元気）
    ///
    /// グラフモデル: 任意グラフ（方位角ベース）。辺は隣接リストで持ち、各出口に方位角を持つ。
    /// 「直進」=進行方向との偏差が閾値未満で最小、「法律どおり右」=右側で偏差最小。
    /// 要求系（人・嘘つき・子供）は知覚時に「宣言方位→最近傍の出口ノード」に解決して渡すので、
    /// Judge はノード値を読むだけの純関数のまま。格子盤は方位が 90° 刻みの特殊ケース。
    /// 決定論: 乱数不使用。タイブレークは「方位角昇順の出口順」で一意。
    /// </summary>

    // ------------------------------------------------------------- 方位（4方位: 宣言向きの互換用）
    public enum Dir { E, S, W, N }

    /// <summary>方位角（bearing）: 0=北 90=東 180=南 270=西。地理座標（東,北）から atan2 で得る。</summary>
    public static class Nav
    {
        /// 直進とみなす偏差の閾値（度）。±60° 未満を「まっすぐ」とみなす。
        public const float StraightThreshold = 60f;

        public static float BearingOf(Dir d)
        {
            switch (d) { case Dir.E: return 90f; case Dir.S: return 180f; case Dir.W: return 270f; default: return 0f; }
        }

        /// from → to の時計回り偏差 0..360（右折方向が正）。
        public static float Dev(float from, float to)
        {
            var d = (to - from) % 360f;
            return d < 0f ? d + 360f : d;
        }

        /// 角度差の絶対値 0..180。
        public static float AbsDev(float from, float to)
        {
            var d = Dev(from, to);
            return d <= 180f ? d : 360f - d;
        }

        /// 宣言方位に最も近い出口。同距離は方位角昇順（＝リスト順）で決定的。
        public static Exit? NearestExit(List<Exit> exits, float bearing)
        {
            Exit? best = null; float bestDev = float.MaxValue;
            foreach (var e in exits)
            {
                var d = AbsDev(bearing, e.Bearing);
                if (d < bestDev) { bestDev = d; best = e; }
            }
            return best;
        }

        /// 「直進」: 偏差が閾値未満の出口のうち偏差最小。なければ null。
        public static Exit? StraightExit(List<Exit> exits, float heading)
        {
            Exit? best = null; float bestDev = StraightThreshold;
            foreach (var e in exits)
            {
                var d = Dev(heading, e.Bearing);
                var dev = d <= 180f ? d : 360f - d;
                if (dev < bestDev) { bestDev = dev; best = e; }
            }
            return best;
        }

        /// 「法律どおり右」: 右側（偏差 0..180°）で偏差最小の出口。右がなければ null。
        public static Exit? RightExit(List<Exit> exits, float heading)
        {
            Exit? best = null; float bestDev = float.MaxValue;
            foreach (var e in exits)
            {
                var d = Dev(heading, e.Bearing);
                if (d <= 0f || d > 180f) continue;
                if (d < bestDev) { bestDev = d; best = e; }
            }
            return best;
        }
    }

    public static class Dirs
    {
        /// 右回りの決定論順（グリッド盤との互換用）。
        public static readonly Dir[] Clockwise = { Dir.E, Dir.S, Dir.W, Dir.N };

        public static int IndexOf(Dir d)
        {
            switch (d) { case Dir.E: return 0; case Dir.S: return 1; case Dir.W: return 2; default: return 3; }
        }

        public static Dir Right(Dir d) => Clockwise[(IndexOf(d) + 1) & 3];
        public static Dir Left(Dir d) => Clockwise[(IndexOf(d) + 3) & 3];
        public static int Dx(Dir d) { switch (d) { case Dir.E: return 1; case Dir.W: return -1; default: return 0; } }
        public static int Dy(Dir d) { switch (d) { case Dir.S: return 1; case Dir.N: return -1; default: return 0; } }
    }

    // ------------------------------------------------------------- 座標（ノード識別子。幾何は Board.Pos が持つ）
    public readonly struct Node : IEquatable<Node>, IComparable<Node>
    {
        public readonly int X; public readonly int Y;
        public Node(int x, int y) { X = x; Y = y; }
        public bool Equals(Node other) => X == other.X && Y == other.Y;
        public override bool Equals(object obj) => obj is Node n && Equals(n);
        public override int GetHashCode() => (X * 397) ^ Y;
        public int CompareTo(Node other) => X != other.X ? X - other.X : Y - other.Y;
        public static bool operator ==(Node a, Node b) => a.Equals(b);
        public static bool operator !=(Node a, Node b) => !a.Equals(b);
        public override string ToString() => "(" + X + "," + Y + ")";
        public static Node Move(Node n, Dir d) => new Node(n.X + Dirs.Dx(d), n.Y + Dirs.Dy(d));
    }

    /// <summary>平面位置（東, 北）。方位角 = atan2(East差, North差)。グリッド盤は (x, -y) で y+ が南。</summary>
    public readonly struct Pos
    {
        public readonly float East, North;
        public Pos(float east, float north) { East = east; North = north; }
    }

    // ------------------------------------------------------------- 盤面
    public enum EdgeKind { Open, Toll }   // Toll = 弱い工事（マッチョで通過）。未登録 = 道がない

    /// <summary>出口（有向辺）。Bearing はこの辺を進む方位角。</summary>
    public readonly struct Exit
    {
        public readonly Node To; public readonly float Bearing; public readonly EdgeKind Kind;
        public Exit(Node to, float bearing, EdgeKind kind) { To = to; Bearing = bearing; Kind = kind; }
    }

    /// <summary>オブジェクト側の世界（グラフ）。爺側はこれを直接書き換えない。</summary>
    public sealed class Board
    {
        readonly Dictionary<Node, List<Exit>> adj = new Dictionary<Node, List<Exit>>();
        readonly Dictionary<Node, Pos> pos = new Dictionary<Node, Pos>();
        readonly Dictionary<Node, int> dist = new Dictionary<Node, int>();
        readonly Node goal;

        public Board(Node goal) { this.goal = goal; }

        public IEnumerable<Node> Nodes => adj.Keys;
        public bool Contains(Node n) => adj.ContainsKey(n);
        public Pos PositionOf(Node n) => pos[n];

        public void AddNode(Node n, Pos p)
        {
            pos[n] = p;
            if (!adj.ContainsKey(n)) adj[n] = new List<Exit>(4);
        }

        /// a-b 間の方位角（pos 必須）。pos 未登録ならグリッド差分 (dx, -dy) から推定。
        public float BearingBetween(Node a, Node b)
        {
            float dx, dy;
            if (pos.TryGetValue(a, out var pa) && pos.TryGetValue(b, out var pb))
            {
                dx = pb.East - pa.East; dy = pb.North - pa.North;
            }
            else
            {
                dx = b.X - a.X; dy = -(b.Y - a.Y);   // グリッド: y+ は南なので北成分は -dy
            }
            var deg = (float)(Math.Atan2(dx, dy) * 180.0 / Math.PI);
            return deg < 0f ? deg + 360f : deg;
        }

        /// 無向辺の追加。両方向の出口を方位角昇順に保つ（決定性）。
        public void AddEdge(Node a, Node b, EdgeKind kind)
        {
            if (!pos.ContainsKey(a)) AddNode(a, new Pos(a.X, -a.Y));
            if (!pos.ContainsKey(b)) AddNode(b, new Pos(b.X, -b.Y));
            InsertExit(a, new Exit(b, BearingBetween(a, b), kind));
            InsertExit(b, new Exit(a, BearingBetween(b, a), kind));
        }

        void InsertExit(Node from, Exit e)
        {
            var list = adj[from];
            var i = 0;
            while (i < list.Count && list[i].Bearing < e.Bearing) i++;
            // 同方位・同行先の重複は上書き（後勝ち）
            for (var j = 0; j < list.Count; j++)
                if (list[j].To.Equals(e.To)) { list[j] = e; return; }
            list.Insert(i, e);
        }

        public List<Exit> Exits(Node n)
        {
            List<Exit> l;
            return adj.TryGetValue(n, out l) ? l : Empty;
        }
        static readonly List<Exit> Empty = new List<Exit>(0);

        /// 駅方向矢印（D23）: ゴールからの BFS 距離が最小の隣ノード。同距離は方位角昇順。
        public void BakeDistance()
        {
            dist.Clear();
            if (!adj.ContainsKey(goal)) return;
            dist[goal] = 0;
            var q = new Queue<Node>(); q.Enqueue(goal);
            while (q.Count > 0)
            {
                var n = q.Dequeue();
                foreach (var e in Exits(n))   // 方位角昇順で走査 → 距離の確定も決定的
                {
                    if (dist.ContainsKey(e.To)) continue;
                    dist[e.To] = dist[n] + 1;
                    q.Enqueue(e.To);
                }
            }
        }

        public bool Known(Node n) => dist.ContainsKey(n);

        /// 駅方向矢印が指す隣ノード（歩ける出口のみ）。読めない場合は null。
        public Node? ArrowNode(Node n)
        {
            Node? best = null; int bestDist = int.MaxValue;
            foreach (var e in Exits(n))
            {
                int d;
                if (!dist.TryGetValue(e.To, out d)) continue;
                if (d < bestDist) { bestDist = d; best = e.To; }
            }
            return best;
        }

        /// 嘘つきの指す方向（駅から最も遠ざかる隣ノード・同距離は方位角昇順）。
        public Node? AntiArrowNode(Node n)
        {
            Node? worst = null; int worstDist = -1;
            foreach (var e in Exits(n))
            {
                int d;
                if (!dist.TryGetValue(e.To, out d)) continue;
                if (d > worstDist) { worstDist = d; worst = e.To; }
            }
            return worst;
        }

        public static Board Build(StageProfile prof)
        {
            var b = new Board(prof.Goal);
            // 位置の登録（プロファイル優先。未指定はグリッド (x,-y)）
            if (prof.NodePos != null)
                foreach (var kv in prof.NodePos) b.AddNode(kv.Key, kv.Value);
            b.AddNode(prof.Start, prof.NodePos != null && prof.NodePos.TryGetValue(prof.Start, out var ps)
                ? ps : new Pos(prof.Start.X, -prof.Start.Y));
            b.AddNode(prof.Goal, prof.NodePos != null && prof.NodePos.TryGetValue(prof.Goal, out var pg)
                ? pg : new Pos(prof.Goal.X, -prof.Goal.Y));
            var edges = prof.Edges ?? StageProfile.FullGridEdges(prof.W, prof.H);
            foreach (var e in edges) b.AddEdge(e[0], e[1], EdgeKind.Open);
            b.BakeDistance();
            return b;
        }
    }

    // ------------------------------------------------------------- ステージ
    public enum NodeEvent { None, BrailleCross, Plaza, Hachi, Child, Liar, CrackedCross }

    public sealed class StageProfile
    {
        public string Name = "";
        public string Note = "";
        public string[] Pieces = Array.Empty<string>();
        public int W, H;
        public Node Start, Goal;
        public readonly Dictionary<Node, NodeEvent> Events = new Dictionary<Node, NodeEvent>();
        public readonly HashSet<Node> Bikes = new HashSet<Node>();   // 置き自転車（自律系の点字を無効化・D30）
        public readonly HashSet<Node> Plazas = new HashSet<Node>();  // 警告ノード（必ず停止）
        public List<Node[]> Edges;                                    // null = 全体を格子状に接続
        public Dictionary<Node, Pos> NodePos;                         // null = グリッド (x,-y) から推定
        public int Gauge, Kp, InitialMacho;
        public bool StartWait = true;                                 // D18 開始指示待ち

        public static List<Node[]> FullGridEdges(int w, int h)
        {
            var list = new List<Node[]>();
            for (var x = 0; x < w; x++)
            for (var y = 0; y < h; y++)
            {
                if (x + 1 < w) list.Add(new[] { new Node(x, y), new Node(x + 1, y) });
                if (y + 1 < h) list.Add(new[] { new Node(x, y), new Node(x, y + 1) });
            }
            return list;
        }

        /// 泣いてる子供の宣言方向（連れ帰りの向き・D23で常時表示）。グリッド盤の互換用。
        public Dir ChildDir = Dir.S;
        /// 子供が連れて行く先の隣ノード（任意グラフ用。設定時は ChildDir より優先）。
        public Node? ChildAim;

        public Node? NodeOf(NodeEvent e)
        {
            foreach (var kv in Events) if (kv.Value == e) return kv.Key;
            return null;
        }
    }

    // ------------------------------------------------------------- 配置ピース
    public enum PieceKind { Jk, Cop, Bike, Fr, Fl }

    /// <summary>
    /// 配置ピース。JK は宣言方向を持つ: Dir（4方位・グリッド盤互換）か Aim（隣ノード指定・任意グラフ）。
    /// 知覚時に「宣言方位に最も近い出口」へ解決される。
    /// </summary>
    public readonly struct Piece : IEquatable<Piece>
    {
        public readonly PieceKind Kind;
        public readonly Dir Direction;
        public readonly Node? Aim;      // 任意グラフでの行き先指定（優先）
        public Piece(PieceKind kind, Dir direction) { Kind = kind; Direction = direction; Aim = null; }
        public Piece(PieceKind kind, Node aim) { Kind = kind; Direction = Dir.E; Aim = aim; }
        public bool Equals(Piece other) =>
            Kind == other.Kind && Direction == other.Direction && Nullable.Equals(Aim, other.Aim);
        public override bool Equals(object obj) => obj is Piece p && Equals(p);
        public override int GetHashCode() =>
            (int)Kind * 31 + Dirs.IndexOf(Direction) + (Aim.HasValue ? Aim.Value.GetHashCode() : 0);
    }

    /// <summary>プレイヤーが置いたピース。強制配置の置き自転車も SeedForcedBikes でここに積む（移動可能にするため）。</summary>
    public sealed class Placements
    {
        readonly Dictionary<Node, Piece> map = new Dictionary<Node, Piece>();

        public bool TryGet(Node n, out Piece piece) => map.TryGetValue(n, out piece);
        public void Place(Node n, Piece piece) => map[n] = piece;
        public bool Remove(Node n) => map.Remove(n);
        public IEnumerable<KeyValuePair<Node, Piece>> All => map;
        public Placements Clone() { var c = new Placements(); foreach (var kv in map) c.Place(kv.Key, kv.Value); return c; }
        public bool HasCop()
        {
            foreach (var kv in map) if (kv.Value.Kind == PieceKind.Cop) return true;
            return false;
        }
        public bool IsBike(Node n)
        {
            Piece p; return map.TryGetValue(n, out p) && p.Kind == PieceKind.Bike;
        }
    }

    // ------------------------------------------------------------- 知覚（オブジェクト側 → 爺側）
    public enum ArrivalKind { Normal, Goal, Sealed, WaitPoint }

    /// <summary>
    /// オブジェクト側が到着のたびに作る知覚スナップショット。爺側はこれだけを見て判断する。
    /// 要求系は「行き先ノード」に解決済みで渡す（方位→出口の解決はオブジェクト側の仕事）。
    /// </summary>
    public sealed class Arrival
    {
        public ArrivalKind Kind;
        public Node Node; public float Heading;              // 到着時の進行方位角
        public List<Exit> OpenExits = new List<Exit>();      // 実際に歩ける出口（マッチョなし工事を除外・方位角昇順）
        public Node? StationArrow;                           // 駅方向矢印の指す先（世界の事実・D23）
        public Node? PersonTo;                               // 人の案内の行き先（爺は無条件に従う・理性は使わない）
        public Node? LiarTo;                                 // 嘘つきの行き先（人の声として無条件に従う・点字を隠す）
        public Node? BrailleTo;                              // 点字の行き先（隠されていなければ駅方向矢印）
        public bool DogEscort;                               // ハチの角: 駅方向へ1区間エスコートが発生
        public bool DogRight;                                // 「次の角で必ず右」の要求が来ている
        public Node? ChildTo;                                // 子供の要求の行き先（必ず発火）
        public int Macho;                                    // マッチョの残数（弱い工事の通過判定）
    }

    // ------------------------------------------------------------- 爺が側の判断（純関数）
    public enum VerdictKind { Move, Wait, Win, Sealed }

    public sealed class Verdict
    {
        public VerdictKind Kind;
        public Node MoveTo;              // 行き先ノード（隣接ノードのみ有効）
        public bool DogEscort;           // ハチのエスコート（適用時に PendingRight を設定する）
        public string Reason = "";
    }

    /// <summary>爺が側の判断。知覚（Arrival）だけを見る純関数で、世界を書き換えない。</summary>
    public sealed class GrandpaJudge
    {
        public Verdict Judge(Arrival a)
        {
            if (a.Kind == ArrivalKind.Goal) return new Verdict { Kind = VerdictKind.Win, Reason = "駅員さんに到達" };
            if (a.Kind == ArrivalKind.Sealed) return new Verdict { Kind = VerdictKind.Sealed, Reason = "身動きが取れない" };

            // 発火順 1: 人の案内——理性は人の声には使わない（善意の声を疑わない。嘘つきでも無条件に信じる）
            if (a.PersonTo != null)
                return Move(a.PersonTo.Value, "人の案内に従う");

            // 嘘つきは人の声（点字を隠す）。爺は無条件で信じる。2回目も騙される
            if (a.LiarTo != null)
                return Move(a.LiarTo.Value, "嘘つきに騙される");

            // 発火順 3: 犬（ハチ）——上位（人・点字）がいれば発火しないので、ここに来るのは発火する時
            if (a.DogEscort)
                return new Verdict
                {
                    Kind = VerdictKind.Move,
                    MoveTo = a.StationArrow ?? NearestOrFirst(a, a.Heading),
                    DogEscort = true,
                    Reason = "ハチにエスコートされ",
                };

            // 広場・開始直後: 人がいなければ待つ（右デフォルトは適用しない）
            if (a.Kind == ArrivalKind.WaitPoint) return new Verdict { Kind = VerdictKind.Wait, Reason = "指示待ち" };

            // 発火順 2: 点字（判断順の最上位）
            if (a.BrailleTo != null)
                return Move(a.BrailleTo.Value, "点字どおり");

            // 発火順 3-4: 犬の右は強制（抗いは廃止——D29でシンプルに統一）
            if (a.DogRight)
            {
                var r = Nav.RightExit(a.OpenExits, a.Heading);
                if (r != null) return Move(r.Value.To, "犬の右に従う");
                return Move(NearestOrFirst(a, a.Heading), "犬の右に従う（右がなく直前の道へ）");
            }
            if (a.ChildTo != null)
                return Move(a.ChildTo.Value, "子供の連れ帰りに付き合う");

            // デフォルト: 出口が一箇所でも封鎖されていれば理性は使わず、空いている方へ
            if (a.OpenExits.Count == 0) return new Verdict { Kind = VerdictKind.Sealed, Reason = "完全に閉ざされた" };
            var st = Nav.StraightExit(a.OpenExits, a.Heading);
            if (st != null) return Move(st.Value.To, "直進");
            if (a.OpenExits.Count == 1) return Move(a.OpenExits[0].To, "一方の道へ");
            // T字・分岐: 法律どおり右（右側で偏差最小）
            var right = Nav.RightExit(a.OpenExits, a.Heading);
            if (right != null) return Move(right.Value.To, "法律どおり右");
            return Move(NearestOrFirst(a, a.Heading), "右の道がなく進行方向に最も近い出口へ");
        }

        static Node NearestOrFirst(Arrival a, float heading)
        {
            var e = Nav.NearestExit(a.OpenExits, heading);
            return e != null ? e.Value.To : (a.OpenExits.Count > 0 ? a.OpenExits[0].To : a.Node);
        }

        static Verdict Move(Node to, string reason) =>
            new Verdict { Kind = VerdictKind.Move, MoveTo = to, Reason = reason };
    }

    // ------------------------------------------------------------- オブジェクト側（世界）
    /// <summary>オブジェクト側: グラフと世界の状態。爺側の判断を世界に適用し、知覚を作る。</summary>
    public sealed class WorldSide
    {
        public readonly Board Board;
        public readonly StageProfile Prof;
        public Node Pos; public float Heading;      // 進行方位角（初期値は東=90°: グリッド互換）
        public int Gauge; public int Macho;
        public bool Waiting;                        // D18 開始指示待ち
        public bool HachiUsed, ChildUsed;           // 強制イベントの発火済みフラグ
        public bool LiarDefeated;                   // お巡りさんの付き添いで嘘つきを倒した
        public bool PendingRight;                   // ハチの「次の角で必ず右」
        public readonly List<string> Log = new List<string>();
        readonly GrandpaJudge judge = new GrandpaJudge();

        public WorldSide(Board board, StageProfile prof)
        {
            Board = board; Prof = prof;
            Pos = prof.Start; Heading = 90f;        // 東向きスタート（グリッド盤の Dir.E 互換）
            Gauge = prof.Gauge; Macho = prof.InitialMacho;
            Waiting = prof.StartWait;
            board.BakeDistance();
        }

        NodeEvent EventAt(Node n)
        {
            NodeEvent e; return Prof.Events.TryGetValue(n, out e) ? e : NodeEvent.None;
        }

        bool BikeHere(Node n, Placements placed) => Prof.Bikes.Contains(n) || placed.IsBike(n);

        /// ピースの宣言（Dir または Aim）を、現在ノードの開いている出口へ解決する。
        Node? ResolveAim(Piece p, List<Exit> open)
        {
            float bearing = p.Aim.HasValue
                ? Board.BearingBetween(Pos, p.Aim.Value)
                : Nav.BearingOf(p.Direction);
            var e = Nav.NearestExit(open, bearing);
            return e?.To;
        }

        /// <summary>オブジェクト側: 到着のたびに世界の変化を知覚へ起こす（発火順）。</summary>
        public Arrival PerceiveArrival(Placements placed)
        {
            var a = new Arrival { Node = Pos, Heading = Heading, Macho = Macho };
            if (Pos == Prof.Goal) { a.Kind = ArrivalKind.Goal; return a; }

            foreach (var e in Board.Exits(Pos))
            {
                // 弱い工事はマッチョが仲間にいれば通過できる（理性を消費しない）
                if (e.Kind == EdgeKind.Toll && Macho <= 0) continue;
                a.OpenExits.Add(e);
            }
            if (a.OpenExits.Count == 0) { a.Kind = ArrivalKind.Sealed; return a; }
            a.StationArrow = Board.ArrowNode(Pos);

            var ev = EventAt(Pos);
            bool bikeHere = BikeHere(Pos, placed);
            bool copOnBoard = placed.HasCop();

            // 発火順 1: 人の案内（呼び止め。直進できても停止）。人の案内は犬の要求を上書きする
            Piece piece;
            if (placed.TryGet(Pos, out piece))
            {
                // 人の案内があれば呼び止めが優先（犬の要求を上書き）
                if (piece.Kind == PieceKind.Jk) { a.PersonTo = ResolveAim(piece, a.OpenExits); PendingRight = false; }
                else if (piece.Kind == PieceKind.Cop) { a.PersonTo = a.StationArrow; PendingRight = false; }
            }

            // 嘘つきは人の声（点字を隠す）。人の案内があれば呼び止めが優先され嘘は聞かれない
            if (ev == NodeEvent.Liar && !LiarDefeated && !copOnBoard && a.PersonTo == null)
                a.LiarTo = Board.AntiArrowNode(Pos);

            // 発火順 2: 点字（嘘つき・置き自転車で隠される）
            if (ev == NodeEvent.BrailleCross && !bikeHere && a.LiarTo == null)
                a.BrailleTo = a.StationArrow;

            // 発火順 3: 犬——上位（人・点字）がいれば発火しない
            var hachiNode = Prof.NodeOf(NodeEvent.Hachi);
            if (hachiNode != null && Pos == hachiNode.Value && !HachiUsed
                && a.PersonTo == null && a.BrailleTo == null)
                a.DogEscort = true;

            // 発火順 4: 子供——必ず発火する（嘘をつく）。移動は判断順に従う
            var childNode = Prof.NodeOf(NodeEvent.Child);
            if (childNode != null && Pos == childNode.Value && !ChildUsed)
            {
                if (Prof.ChildAim.HasValue)
                {
                    a.ChildTo = Prof.ChildAim.Value;
                }
                else
                {
                    var e = Nav.NearestExit(a.OpenExits, Nav.BearingOf(Prof.ChildDir));
                    a.ChildTo = e?.To;
                }
                ChildUsed = true;
            }

            // ハチのエスコート由来の「次の角で必ず右」（1回限り）
            if (PendingRight)
            {
                a.DogRight = true;
                PendingRight = false;
            }

            // 広場（警告ノード）・開始指示待ち: 必ず停止（右デフォルト不適用）
            if (Prof.Plazas.Contains(Pos) || Waiting) a.Kind = ArrivalKind.WaitPoint;
            return a;
        }

        /// <summary>オブジェクト側: 爺の判断を世界に適用する（グラフ側で起きる変化）。</summary>
        public string Apply(Placements placed, in Verdict v)
        {
            switch (v.Kind)
            {
                case VerdictKind.Win: return "WIN";
                case VerdictKind.Sealed: Gauge = 0; return "LOSE";
                case VerdictKind.Wait:
                    Gauge -= 2;
                    if (Gauge <= 0) return "LOSE";
                    Log.Add("  指示を待つ（元気 " + Gauge + "）");
                    return "";
                case VerdictKind.Move:
                    break;
            }
            var from = Pos;
            var m = v.MoveTo;
            Gauge -= 1;
            // 弱い工事はマッチョで超える（理性を消費しない）
            foreach (var e in Board.Exits(from))
                if (e.To == m && e.Kind == EdgeKind.Toll) Macho -= 1;
            Heading = Board.BearingBetween(from, m);
            Pos = m;
            var line = "  " + v.Reason + ": 方位" + Heading.ToString("0") + "° → " + Pos + "（元気 " + Gauge + "）";
            Log.Add(line);

            // グラフ側で起きる変化（発火済みフラグ）
            if (v.DogEscort)
            {
                HachiUsed = true;
                PendingRight = true;
            }
            if (Pos == Prof.Goal) return "WIN";
            return "";
        }

        public Verdict Judge(in Arrival a) => judge.Judge(a);

        /// <summary>ソルバの分岐用にディープコピーする。</summary>
        public WorldSide Clone()
        {
            var c = new WorldSide(Board, Prof)
            {
                Pos = Pos, Heading = Heading, Gauge = Gauge, Macho = Macho,
                Waiting = Waiting, HachiUsed = HachiUsed, ChildUsed = ChildUsed,
                LiarDefeated = LiarDefeated, PendingRight = PendingRight,
            };
            return c;
        }
    }

    // ------------------------------------------------------------- シミュレータ
    public sealed class SimResult
    {
        public bool Win; public string Status = ""; public List<string> Log = new List<string>(); public int Steps;
    }

    public static class Simulator
    {
        public static SimResult Run(StageProfile prof, Placements placed, int maxSteps = 2000)
        {
            // 強制配置の置き自転車を配置済みとして積む（移動・撤去はプレイヤーの手でできる）
            foreach (var b in prof.Bikes) placed.Place(b, new Piece(PieceKind.Bike, Dir.E));

            var world = new WorldSide(Board.Build(prof), prof);
            var judge = new GrandpaJudge();
            var result = new SimResult();
            var log = new StringBuilder();

            for (var step = 0; step < maxSteps; step++)
            {
                var a = world.PerceiveArrival(placed);
                var v = judge.Judge(a);
                foreach (var line in world.Log) log.AppendLine(line);
                world.Log.Clear();

                var worldStatus = world.Apply(placed, v);
                foreach (var line in world.Log) log.AppendLine(line);
                world.Log.Clear();

                result.Steps = step + 1;
                if (v.Kind == VerdictKind.Win || worldStatus == "WIN")
                {
                    result.Win = true; result.Status = "駅員さんに到達"; break;
                }
                if (v.Kind == VerdictKind.Sealed || worldStatus == "LOSE")
                {
                    result.Status = string.IsNullOrEmpty(v.Reason) ? "帰宅" : v.Reason; break;
                }
            }
            if (result.Steps >= maxSteps && !result.Win) result.Status = "散歩が長すぎます";
            result.Log = SplitLines(log.ToString());
            return result;
        }

        static List<string> SplitLines(string s)
        {
            var list = new List<string>();
            var parts = s.Split('\n');
            foreach (var line in parts)
            {
                var t = line.TrimEnd('\r');
                if (t.Length > 0) list.Add(t);
            }
            return list;
        }
    }
}
