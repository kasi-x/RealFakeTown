using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using UnityEngine;

namespace RealFakeTown.Sim
{
    /// <summary>
    /// OSM 実街路グラフ（Assets/StreamingAssets/osm_marunouchi.json）の C# 版ステージ定義。
    /// tools/osm_to_graph.py が生成した JSON（nodes/edges）を Unity 側で読んで遊ぶ。
    /// JSON はトップレベルの配列や [[0,1]] 形式の辺を含むため JsonUtility では扱えない。
    /// ここでは正規表現ベースの手パースで読み、失敗時は例外を投げず null を返す。
    /// </summary>
    public static class OsmGraph
    {
        /// <summary>StreamingAssets に置く JSON ファイル名。</summary>
        public const string JsonName = "osm_marunouchi.json";

        /// <summary>LoadRaw の結果。ノードごとの生データと辺リスト（id は JSON 側の通し番号）。</summary>
        public sealed class RawData
        {
            public int[] Id = Array.Empty<int>();
            public int[] Gx = Array.Empty<int>();
            public int[] Gy = Array.Empty<int>();
            public double[] Lat = Array.Empty<double>();
            public double[] Lon = Array.Empty<double>();
            public List<int[]> Edges = new List<int[]>();
            public int NodeCount => Id.Length;
        }

        /// <summary>StreamingAssets から JSON を読んで手パースする。読めなければ null。</summary>
        public static RawData LoadRaw()
        {
            string text;
            try
            {
                var path = Path.Combine(Application.streamingAssetsPath, JsonName);
                if (!File.Exists(path)) return null;
                text = File.ReadAllText(path);
            }
            catch (Exception)
            {
                return null;
            }
            return Parse(text);
        }

        /// <summary>
        /// JSON テキストから "nodes" と "edges" の配列をブラケット対応で抽出して手パースする。
        /// ノードは {"id":i,"gx":x,"gy":y,"lat":f,"lon":f} の各フィールドを正規表現で、
        /// 辺は [a,b] を正規表現で取る。形式が想定と違う場合は null。
        /// </summary>
        internal static RawData Parse(string text)
        {
            var nodesText = ExtractArray(text, "\"nodes\"");
            var edgesText = ExtractArray(text, "\"edges\"");
            if (nodesText == null || edgesText == null) return null;

            var raw = new RawData();
            var ids = new List<int>();
            var gxs = new List<int>();
            var gys = new List<int>();
            var lats = new List<double>();
            var lons = new List<double>();

            foreach (Match m in Regex.Matches(nodesText, @"\{[^{}]*\}"))
            {
                var obj = m.Value;
                var id = IntField(obj, "id");
                var gx = IntField(obj, "gx");
                var gy = IntField(obj, "gy");
                var lat = NumField(obj, "lat");
                var lon = NumField(obj, "lon");
                if (id == null || gx == null || gy == null || lat == null || lon == null) continue;
                ids.Add(id.Value); gxs.Add(gx.Value); gys.Add(gy.Value);
                lats.Add(lat.Value); lons.Add(lon.Value);
            }
            if (ids.Count == 0) return null;

            var edgeIds = new List<int[]>();
            foreach (Match m in Regex.Matches(edgesText, @"\[\s*(\d+)\s*,\s*(\d+)\s*\]"))
            {
                int a, b;
                if (!int.TryParse(m.Groups[1].Value, out a)) continue;
                if (!int.TryParse(m.Groups[2].Value, out b)) continue;
                edgeIds.Add(new[] { a, b });
            }
            if (edgeIds.Count == 0) return null;

            raw.Id = ids.ToArray();
            raw.Gx = gxs.ToArray();
            raw.Gy = gys.ToArray();
            raw.Lat = lats.ToArray();
            raw.Lon = lons.ToArray();
            raw.Edges = edgeIds;
            return raw;
        }

        /// <summary>キー文字列の直後にある [...] 配列をブラケット対応で切り出す（無ければ null）。</summary>
        static string ExtractArray(string text, string key)
        {
            var i = text.IndexOf(key, StringComparison.Ordinal);
            if (i < 0) return null;
            var open = text.IndexOf('[', i);
            if (open < 0) return null;
            var depth = 0;
            for (var k = open; k < text.Length; k++)
            {
                if (text[k] == '[') depth++;
                else if (text[k] == ']')
                {
                    depth--;
                    if (depth == 0) return text.Substring(open, k - open + 1);
                }
            }
            return null;
        }

        static int? IntField(string obj, string key) =>
            MatchInt(obj, key + @"""\s*:\s*(-?\d+)");

        static double? NumField(string obj, string key) =>
            MatchDouble(obj, key + @"""\s*:\s*(-?\d+(?:\.\d+)?)");

        static int? MatchInt(string s, string pattern)
        {
            var m = Regex.Match(s, pattern);
            int v;
            return m.Success && int.TryParse(m.Groups[1].Value, out v) ? (int?)v : null;
        }

        static double? MatchDouble(string s, string pattern)
        {
            var m = Regex.Match(s, pattern);
            double v;
            return m.Success
                && double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out v)
                ? (double?)v : null;
        }

        // ------------------------------------------------------------- ステージ

        /// <summary>no=1: 全グラフ / no=2: 最短経路コリドア。JSON が読めなければ null。</summary>
        public static StageProfile BuildStage(int no)
        {
            var raw = LoadRaw();
            if (raw == null || raw.NodeCount == 0) return null;
            switch (no)
            {
                case 1: return BuildWhole(raw);
                case 2: return BuildCorridor(raw);
                default: return null;
            }
        }

        /// <summary>
        /// ノード同一性: gx,gy が全ノードで一意なら Node(gx,gy) を使う（グリッド互換・デバッグ表示に有利）。
        /// 重複があれば Node(id,0) にフォールバックする（id は必ず一意なので同一性は保たれる）。
        /// </summary>
        static Node[] MapNodes(RawData raw, out bool useGxGy)
        {
            useGxGy = GxGyUnique(raw);
            var map = new Node[raw.NodeCount];
            for (var i = 0; i < raw.NodeCount; i++)
                map[i] = useGxGy ? new Node(raw.Gx[i], raw.Gy[i]) : new Node(raw.Id[i], 0);
            return map;
        }

        static bool GxGyUnique(RawData raw)
        {
            var seen = new HashSet<long>();
            for (var i = 0; i < raw.NodeCount; i++)
            {
                var key = (long)raw.Gx[i] * 1000003L + raw.Gy[i];
                if (!seen.Add(key)) return false;
            }
            return true;
        }

        /// <summary>lon/lat を bbox 正規化: 最小を 0 にし、長辺が約 30 単位になるよう一様スケール（縦横比維持）。</summary>
        static Pos[] NormalizedPositions(RawData raw)
        {
            var lonMin = raw.Lon[0]; var lonMax = raw.Lon[0];
            var latMin = raw.Lat[0]; var latMax = raw.Lat[0];
            for (var i = 1; i < raw.NodeCount; i++)
            {
                lonMin = Math.Min(lonMin, raw.Lon[i]); lonMax = Math.Max(lonMax, raw.Lon[i]);
                latMin = Math.Min(latMin, raw.Lat[i]); latMax = Math.Max(latMax, raw.Lat[i]);
            }
            var lonSpan = lonMax - lonMin;
            var latSpan = latMax - latMin;
            var scale = 30.0 / Math.Max(lonSpan, latSpan);   // 長辺 ≈ 30 単位
            var pos = new Pos[raw.NodeCount];
            for (var i = 0; i < raw.NodeCount; i++)
            {
                var east = (raw.Lon[i] - lonMin) * scale;
                var north = (raw.Lat[i] - latMin) * scale;
                pos[i] = new Pos((float)east, (float)north);
            }
            return pos;
        }

        static int[] Degrees(RawData raw)
        {
            var deg = new int[raw.NodeCount];
            foreach (var e in raw.Edges)
            {
                if (e[0] >= 0 && e[0] < raw.NodeCount) deg[e[0]]++;
                if (e[1] >= 0 && e[1] < raw.NodeCount) deg[e[1]]++;
            }
            return deg;
        }

        /// <summary>最西端（lon 最小、同値は lat・id 昇順）と最東端（lon 最大、同値は lat・id 昇順）。</summary>
        static void FindStartGoal(RawData raw, out int startId, out int goalId)
        {
            startId = 0; goalId = 0;
            for (var i = 1; i < raw.NodeCount; i++)
            {
                if (LonLatLess(raw.Lon[i], raw.Lat[i], raw.Lon[startId], raw.Lat[startId])) startId = i;
                if (LonLatGreater(raw.Lon[i], raw.Lat[i], raw.Lon[goalId], raw.Lat[goalId])) goalId = i;
            }
        }

        static bool LonLatLess(double lon, double lat, double bestLon, double bestLat) =>
            lon < bestLon || (lon == bestLon && lat < bestLat);

        static bool LonLatGreater(double lon, double lat, double bestLon, double bestLat) =>
            lon > bestLon || (lon == bestLon && lat > bestLat);

        static StageProfile BuildWhole(RawData raw)
        {
            var map = MapNodes(raw, out _);
            var pos = NormalizedPositions(raw);
            int startId, goalId;
            FindStartGoal(raw, out startId, out goalId);
            var start = map[startId];
            var goal = map[goalId];

            var prof = new StageProfile
            {
                Name = "OSM丸の内 皇居→東京駅",
                Note = "実街路 408 ノード全体。皇居側（最西端）から東京駅（最東端）へ。",
                Pieces = new[] { "JK", "COP" },
                W = MaxGx(raw) + 1, H = MaxGy(raw) + 1,
                Start = start, Goal = goal,
                Gauge = raw.NodeCount,   // ノード数に比例
                Kp = 15,
                StartWait = false,       // OSM ステージは開始指示待ちなし
                Edges = new List<Node[]>(),
                NodePos = new Dictionary<Node, Pos>(),
            };
            for (var i = 0; i < raw.NodeCount; i++) prof.NodePos[map[i]] = pos[i];
            foreach (var e in raw.Edges) prof.Edges.Add(new[] { map[e[0]], map[e[1]] });

            // 次数≥3 の上位 5 交差点に点字ブロック（次数降順、同数は Node 辞書順 = gx,gy 昇順で決定論的）
            var deg = Degrees(raw);
            var candidates = new List<int>();
            for (var i = 0; i < raw.NodeCount; i++) if (deg[i] >= 3) candidates.Add(i);
            candidates.Sort((a, b) =>
            {
                var c = deg[b].CompareTo(deg[a]);
                return c != 0 ? c : map[a].CompareTo(map[b]);
            });
            for (var k = 0; k < candidates.Count && k < 5; k++)
                prof.Events[map[candidates[k]]] = NodeEvent.BrailleCross;

            // 広場: 中央（gx,gy 範囲の中点）に最も近い次数≥3 交差点から 1 つ（点字と重複しない）。
            // 決定論ルール: 距離二乗最小、同値は Node 辞書順。
            var brailleSet = new HashSet<Node>();
            foreach (var n in prof.Events.Keys) brailleSet.Add(n);
            var cx = (MinGx(raw) + MaxGx(raw)) / 2.0;
            var cy = (MinGy(raw) + MaxGy(raw)) / 2.0;
            int plazaId = -1; var bestD2 = double.MaxValue;
            for (var i = 0; i < raw.NodeCount; i++)
            {
                if (deg[i] < 3 || brailleSet.Contains(map[i])) continue;
                var dx = raw.Gx[i] - cx; var dy = raw.Gy[i] - cy;
                var d2 = dx * dx + dy * dy;
                if (d2 < bestD2 || (d2 == bestD2 && (plazaId < 0 || map[i].CompareTo(map[plazaId]) < 0)))
                {
                    bestD2 = d2; plazaId = i;
                }
            }
            if (plazaId >= 0) prof.Plazas.Add(map[plazaId]);
            return prof;
        }

        static StageProfile BuildCorridor(RawData raw)
        {
            var d = BuildCorridorData(raw, 2);
            return d != null ? d.Profile : null;
        }

        /// <summary>BuildCorridor / DemoGeneration の共有データ（コリドア盤面・最短経路・コリドア内次数）。</summary>
        sealed class CorridorData
        {
            public StageProfile Profile;
            public List<Node> Path = new();              // BFS 最短経路（start→goal の Node 列）
            public List<Node[]> CorridorEdges = new();   // コリドア内の辺
            public Dictionary<Node, int> Degree = new(); // コリドア内次数
        }

        /// <summary>コリドア部分グラフ: BFS 最短経路から ±band ホップ以内のノードと辺だけを残す。</summary>
        static CorridorData BuildCorridorData(RawData raw, int band)
        {
            var map = MapNodes(raw, out _);
            var pos = NormalizedPositions(raw);
            int startId, goalId;
            FindStartGoal(raw, out startId, out goalId);
            var start = map[startId];
            var goal = map[goalId];

            var adj = BuildAdjacency(raw, map);
            var path = ShortestPath(raw, map, adj, startId, goalId);
            if (path == null) return null;   // goal 未到達（連結でない）→ コリドアなし

            // コリドア: 経路上の各ノードから ±band ホップ以内のノード集合
            var corridor = new HashSet<Node>();
            foreach (var p in path) corridor.Add(p);
            var indexOf = new Dictionary<Node, int>();
            for (var i = 0; i < raw.NodeCount; i++) indexOf[map[i]] = i;
            foreach (var p in path)
            {
                var pid = indexOf[p];
                var seen = new HashSet<int> { pid };
                var qq = new Queue<(int Node, int Depth)>();
                qq.Enqueue((pid, 0));
                while (qq.Count > 0)
                {
                    var (u, d) = qq.Dequeue();
                    if (d >= band) continue;
                    foreach (var v in adj[u])
                    {
                        if (!seen.Add(v)) continue;
                        qq.Enqueue((v, d + 1));
                    }
                }
                foreach (var v in seen) corridor.Add(map[v]);
            }

            // コリドア内の辺（両端点がコリドア内）と次数
            var corrEdges = new List<Node[]>();
            var degree = new Dictionary<Node, int>();
            foreach (var e in raw.Edges)
            {
                var a = map[e[0]]; var b = map[e[1]];
                if (!corridor.Contains(a) || !corridor.Contains(b)) continue;
                corrEdges.Add(new[] { a, b });
                degree[a] = degree.TryGetValue(a, out var da) ? da + 1 : 1;
                degree[b] = degree.TryGetValue(b, out var db) ? db + 1 : 1;
            }

            var enodes = new HashSet<Node>();
            foreach (var e in corrEdges) { enodes.Add(e[0]); enodes.Add(e[1]); }
            var prof = new StageProfile
            {
                Name = "OSM丸の内 皇居→東京駅（コリドア）",
                Note = "最短経路 ±" + band + " ホップの実街路。歩数" + (path.Count - 1) + "。",
                Pieces = new[] { "JK", "COP" },
                W = MaxGx(raw) + 1, H = MaxGy(raw) + 1,
                Start = start, Goal = goal,
                Gauge = enodes.Count,
                Kp = 15,
                StartWait = false,
                Edges = corrEdges,
                NodePos = new Dictionary<Node, Pos>(),
            };
            foreach (var n in enodes) prof.NodePos[n] = pos[indexOf[n]];
            return new CorridorData { Profile = prof, Path = path, CorridorEdges = corrEdges, Degree = degree };
        }

        /// <summary>全グラフの隣接リスト（隣接は Node 辞書順でソート → BFS が決定論的）。</summary>
        static List<int>[] BuildAdjacency(RawData raw, Node[] map)
        {
            var adj = new List<int>[raw.NodeCount];
            for (var i = 0; i < raw.NodeCount; i++) adj[i] = new List<int>();
            foreach (var e in raw.Edges)
            {
                adj[e[0]].Add(e[1]);
                adj[e[1]].Add(e[0]);
            }
            for (var i = 0; i < raw.NodeCount; i++)
                adj[i].Sort((a, b) => map[a].CompareTo(map[b]));
            return adj;
        }

        /// <summary>Start からの BFS で最短経路を復元（Goal から親を辿る）。Goal 未到達なら null。</summary>
        static List<Node> ShortestPath(RawData raw, Node[] map, List<int>[] adj, int startId, int goalId)
        {
            var prev = new int[raw.NodeCount];
            var dist = new int[raw.NodeCount];
            for (var i = 0; i < raw.NodeCount; i++) { prev[i] = -1; dist[i] = -1; }
            var q = new Queue<int>();
            dist[startId] = 0; q.Enqueue(startId);
            while (q.Count > 0)
            {
                var u = q.Dequeue();
                foreach (var v in adj[u])
                {
                    if (dist[v] >= 0) continue;
                    dist[v] = dist[u] + 1; prev[v] = u; q.Enqueue(v);
                }
            }
            if (dist[goalId] < 0) return null;
            var path = new List<int>();
            for (var u = goalId; u >= 0; u = prev[u]) path.Add(u);
            path.Reverse();
            var nodes = new List<Node>();
            foreach (var i in path) nodes.Add(map[i]);
            return nodes;
        }

        /// <summary>辺リスト内の BFS で from→to の経路（Node 辞書順隣接・決定論的）。到達不能なら {from}。</summary>
        static List<Node> BfsRoute(List<Node[]> edges, Node from, Node to)
        {
            var adj = new Dictionary<Node, List<Node>>();
            foreach (var e in edges)
            {
                if (!adj.TryGetValue(e[0], out var la)) { la = new List<Node>(); adj[e[0]] = la; }
                if (!adj.TryGetValue(e[1], out var lb)) { lb = new List<Node>(); adj[e[1]] = lb; }
                la.Add(e[1]); lb.Add(e[0]);
            }
            foreach (var kv in adj) kv.Value.Sort((a, b) => a.CompareTo(b));

            var prev = new Dictionary<Node, Node>();
            var seen = new HashSet<Node> { from };
            var q = new Queue<Node>();
            q.Enqueue(from);
            while (q.Count > 0)
            {
                var u = q.Dequeue();
                List<Node> list;
                if (!adj.TryGetValue(u, out list)) continue;
                foreach (var v in list)
                {
                    if (!seen.Add(v)) continue;
                    prev[v] = u; q.Enqueue(v);
                }
            }
            if (!seen.Contains(to)) return new List<Node> { from };
            var route = new List<Node>();
            for (var u = to; ; u = prev[u])
            {
                route.Add(u);
                if (u == from) break;
            }
            route.Reverse();
            return route;
        }

        /// <summary>
        /// 生成器デモ: OSM コリドア（BuildStage(2)）をベースに、BFS 最短経路上の中間交差点で
        /// 子供（ChildRevisit）が駅と逆方向へ連れ去る「逸脱→戻る」パズルを逆算生成する。
        /// 決定論ルール:
        ///   - トリガー: 経路の中央に最も近い、コリドア内次数≥3 の中間ノード（同距離は Node 辞書順）
        ///   - DeclaredAim: AntiArrowNode（駅から最も遠い隣ノード・同距離は方位角昇順）
        ///   - TrickPath: 経路でトリガーまで → 逸脱ノード → コリドア内 BFS でゴールへ戻る
        ///   - FallbackPath: BFS 最短経路（生成器が全辺を閉鎖する）
        /// ソルバは生成器側の CloneProfile で StartWait=true（停止点=スタートのみ）になるため
        /// DFS 分岐は1点。137ノードでも実用時間内に収まり爆発は原則起きないが、
        /// 防御的に targetMoves を 3→1 へ下げ、それでも例外が出ればコリドアを ±1 に縮小する。
        /// </summary>
        public static GeneratedPuzzle DemoGeneration()
        {
            var raw = LoadRaw();
            if (raw == null || raw.NodeCount == 0)
                return new GeneratedPuzzle { Success = false, Message = "OSM JSON が読めない" };

            foreach (var band in new[] { 2, 1 })
            {
                var data = BuildCorridorData(raw, band);
                if (data == null) continue;

                // 全トリガー候補（コリドア内次数≥3 の中間ノード）を試す
                for (var ti = 1; ti + 1 < data.Path.Count; ti++)
                {
                    var trigger = data.Path[ti];
                    int dg;
                    if (!data.Degree.TryGetValue(trigger, out dg) || dg < 3) continue;

                    // 駅方向と逆の隣ノード（AntiArrowNode）
                    var board = Board.Build(data.Profile);
                    var anti = board.AntiArrowNode(trigger);
                    if (anti == null) continue;

                    // TrickPath: 経路でトリガーまで → 逸脱（駅と逆方向）→ コリドア内 BFS でゴールへ戻る
                    var trickPath = new List<Node>();
                    for (var i = 0; i <= ti; i++) trickPath.Add(data.Path[i]);
                    trickPath.Add(anti.Value);
                    var back = BfsRoute(data.CorridorEdges, anti.Value, data.Profile.Goal);
                    for (var i = 1; i < back.Count; i++) trickPath.Add(back[i]);

                    // 技経路に再訪ノードが含まれることを検証（子供トリック成立要件）
                    var seen = new HashSet<Node>();
                    bool revisited = false;
                    foreach (var nd in trickPath)
                    {
                        if (!seen.Add(nd)) { revisited = true; break; }
                    }
                    if (!revisited) continue;

                    // FallbackPath = BFS 最短経路 → 生成器が分岐以降の辺だけ閉鎖（子ノードAim のため技経路の接頭辞は共有）
                    var trick = new TrickSpec
                    {
                        Mechanic = TrickMechanic.ChildRevisit,
                        TriggerNode = trigger,
                        DeclaredAim = anti,
                        TrickPath = trickPath,
                        FallbackPath = new List<Node>(data.Path),
                    };
                    for (var target = 3; target >= 1; target--)
                    {
                        try
                        {
                            var result = HardPuzzleGenerator.Generate(data.Profile, trick, target);
                            if (result.TrickNecessary) return result;
                        }
                        catch { }
                    }
                }
            }
            return new GeneratedPuzzle { Success = false, Message = "技必須のトリガーが見つからなかった（OSM コリドアは木に近い構造）" };
        }

        static int MinGx(RawData raw) { var m = raw.Gx[0]; for (var i = 1; i < raw.NodeCount; i++) m = Math.Min(m, raw.Gx[i]); return m; }
        static int MaxGx(RawData raw) { var m = raw.Gx[0]; for (var i = 1; i < raw.NodeCount; i++) m = Math.Max(m, raw.Gx[i]); return m; }
        static int MinGy(RawData raw) { var m = raw.Gy[0]; for (var i = 1; i < raw.NodeCount; i++) m = Math.Min(m, raw.Gy[i]); return m; }
        static int MaxGy(RawData raw) { var m = raw.Gy[0]; for (var i = 1; i < raw.NodeCount; i++) m = Math.Max(m, raw.Gy[i]); return m; }
    }
}