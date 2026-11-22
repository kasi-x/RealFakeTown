using UnityEngine;
using System.Collections.Generic;
using RealFakeTown.Sim;

namespace RealFakeTown
{
    /// <summary>Unity の Play Mode で自動起動。</summary>
    public class GameBootstrapperBehaviour : MonoBehaviour
    {
        void Awake()
        {
            var cam = new GameObject("MainCamera").AddComponent<Camera>();
            cam.tag = "MainCamera";
            cam.orthographic = true;
            cam.orthographicSize = 4f;
            cam.transform.position = new Vector3(2f, 10f, 0.5f);
            cam.transform.LookAt(new Vector3(2f, 0f, 1f));
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.92f, 0.9f, 0.85f);
            var light = new GameObject("Light").AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.1f;
            light.transform.rotation = Quaternion.Euler(55, -25, 0);
        }

        void Start() => GameVisual.Initialize();
        void Update()
        {
            GameVisual.UpdateFrame();
            if (Input.GetMouseButtonDown(0)) GameVisual.HandleClick();
        }
        void OnGUI() => GameVisual.DrawHUD();
    }

    public static class GameVisual
    {
        // --- ステージ一覧・クリア
        static (string book, int no, StageProfile prof)[] _stages = System.Array.Empty<(string, int, StageProfile)>();
        static int _stageIdx;
        static readonly HashSet<int> _cleared = new HashSet<int>();

        // --- シミュ状態
        static Board _board; static StageProfile _prof;
        static WorldSide _world; static Placements _placed;
        static int _kpLeft; static int _turn;
        static readonly Stack<(WorldSide w, Placements p, int kp, int turn)> _undoStack = new();
        static string _message = "ピースを選んで配置してください";

        // --- ビジュアル
        static GameObject _boardRoot; static GameObject _grandpa;
        static readonly Dictionary<GameObject, Node> _nodeObjects = new();   // GameObject → Node 逆引き
        static readonly Dictionary<Node, Renderer> _nodeRenderers = new();
        static readonly Dictionary<Node, GameObject> _pieces = new();
        static readonly Dictionary<Node, int> _jkAim = new();               // JK の aim 巡回位置（Exits 順）
        static PieceKind? _sel; static Node? _hoverNode;
        static Node? _hintNode; static float _hintTimer;

        // --- 色
        static readonly Color CNode = new(0.92f, 0.9f, 0.82f);
        static readonly Color CBraille = new(1f, 0.92f, 0.35f);
        static readonly Color CPlaza = new(0.55f, 0.82f, 0.55f);
        static readonly Color CHachi = new(0.95f, 0.55f, 0.25f);
        static readonly Color CChild = new(0.4f, 0.8f, 0.8f);
        static readonly Color CLiar = new(0.7f, 0.45f, 0.85f);
        static readonly Color CCracked = new(0.45f, 0.4f, 0.32f);
        static readonly Color CGoal = new(0.92f, 0.25f, 0.25f);
        static readonly Color CStart = new(0.35f, 0.55f, 0.92f);
        static readonly Color CRoad = new(0.72f, 0.7f, 0.62f);
        static readonly Color CGrandpa = new(0.15f, 0.15f, 0.65f);
        static readonly Color CJk = new(1f, 0.65f, 0.78f);
        static readonly Color CCop = new(0.25f, 0.45f, 0.95f);
        static readonly Color CBike = new(0.65f, 0.65f, 0.65f);
        static readonly Color CHover = new(1f, 1f, 0.5f);
        static readonly Color CHint = new(1f, 0.25f, 0.2f);

        // --- ピース定義
        static readonly (string code, string name, PieceKind kind, int cost)[] PieceDefs = {
            ("JK", "女子高生", PieceKind.Jk, 1),
            ("COP", "お巡りさん", PieceKind.Cop, 3),
            ("FR", "強制右", PieceKind.Fr, 1),
            ("FL", "強制左", PieceKind.Fl, 1),
            ("BIKE", "置き自転車", PieceKind.Bike, 1),
        };

        // ---------------------------------------------------- 初期化
        public static void Initialize()
        {
            _stages = GameBooks.GetAllStages();
            if (_stages.Length == 0)
            {
                _message = "ステージがありません";
                return;
            }
            LoadStage(0);
        }

        /// <summary>ステージを読み込み、盤面・世界・配置・カメラを再構築する。</summary>
        public static void LoadStage(int idx)
        {
            _stageIdx = idx;
            var (book, no, prof) = _stages[idx];
            _prof = prof;
            _board = Board.Build(prof);
            _world = new WorldSide(_board, _prof);
            _placed = new Placements();
            _kpLeft = _prof.Kp;
            _turn = 0;
            _undoStack.Clear();
            _sel = null;
            _hoverNode = null;
            _hintNode = null; _hintTimer = 0f;
            _jkAim.Clear();
            _pieces.Clear();
            _message = $"<color=#ffd>{book} {no}</color> — ピースを選んで配置してください";
            BuildBoard();
            SpawnGrandpa();
            FitCamera();
        }

        /// <summary>ノードの世界座標。北=+North → Unity の +Z。</summary>
        static Vector3 BoardPos(Node n) => new(_board.PositionOf(n).East, 0f, _board.PositionOf(n).North);

        static void BuildBoard()
        {
            if (_boardRoot != null) Object.Destroy(_boardRoot);
            _boardRoot = new GameObject("Board");
            _nodeObjects.Clear();
            _nodeRenderers.Clear();

            // ノード群の bounds（カメラ・地面サイズ用）
            var minX = float.MaxValue; var maxX = float.MinValue;
            var minZ = float.MaxValue; var maxZ = float.MinValue;
            foreach (var n in _board.Nodes)
            {
                var p = _board.PositionOf(n);
                minX = Mathf.Min(minX, p.East); maxX = Mathf.Max(maxX, p.East);
                minZ = Mathf.Min(minZ, p.North); maxZ = Mathf.Max(maxZ, p.North);
            }
            if (minX > maxX) { minX = -1f; maxX = 1f; minZ = -1f; maxZ = 1f; }

            // 地面
            var bg = GameObject.CreatePrimitive(PrimitiveType.Plane);
            bg.name = "Ground";
            bg.transform.position = new Vector3((minX + maxX) / 2f, -0.05f, (minZ + maxZ) / 2f);
            var gw = Mathf.Max(1f, maxX - minX) + 4f;
            var gd = Mathf.Max(1f, maxZ - minZ) + 4f;
            bg.transform.localScale = new Vector3(gw / 10f, 1f, gd / 10f);
            bg.GetComponent<Renderer>().material.color = new Color(0.88f, 0.88f, 0.82f);
            bg.transform.SetParent(_boardRoot.transform, true);

            // 道路: n.CompareTo(e.To) &lt; 0 のときだけ描いて二重描画を防ぐ
            foreach (var n in _board.Nodes)
            {
                var a = BoardPos(n);
                foreach (var e in _board.Exits(n))
                {
                    if (n.CompareTo(e.To) >= 0) continue;
                    var b = BoardPos(e.To);
                    var len = Vector3.Distance(a, b);
                    var road = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    road.name = "Road";
                    road.transform.position = (a + b) * 0.5f;
                    road.transform.rotation = Quaternion.Euler(0f, e.Bearing, 0f);
                    road.transform.localScale = new Vector3(0.18f, 0.02f, len);
                    road.GetComponent<Renderer>().material.color = CRoad;
                    road.transform.SetParent(_boardRoot.transform, true);
                }
            }

            // ノード立方体（イベント/Start/Goal/Plaza で色分け）
            foreach (var n in _board.Nodes)
            {
                var (c, sz) = NodeAppearance(n);
                var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                go.name = $"N_{n.X}_{n.Y}";
                go.transform.position = BoardPos(n);
                go.transform.localScale = new Vector3(sz, 0.08f, sz);
                go.GetComponent<Renderer>().material.color = c;
                go.transform.SetParent(_boardRoot.transform, true);
                _nodeRenderers[n] = go.GetComponent<Renderer>();
                _nodeObjects[go] = n;

                var label = LabelOf(n);
                if (label.Length > 0)
                {
                    var tm = new GameObject($"L_{n.X}_{n.Y}").AddComponent<TextMesh>();
                    tm.transform.position = BoardPos(n) + new Vector3(0f, 0.15f, 0f);
                    tm.characterSize = 0.25f; tm.fontSize = 24; tm.anchor = TextAnchor.MiddleCenter;
                    tm.color = Color.black;
                    tm.text = label;
                    tm.transform.SetParent(_boardRoot.transform, true);
                }
            }
        }

        static (Color c, float sz) NodeAppearance(Node n)
        {
            var ev = _prof.Events.TryGetValue(n, out var e) ? e : NodeEvent.None;
            return ev switch
            {
                NodeEvent.BrailleCross => (CBraille, 0.55f),
                NodeEvent.Plaza => (CPlaza, 0.6f),
                NodeEvent.Hachi => (CHachi, 0.5f),
                NodeEvent.Child => (CChild, 0.55f),
                NodeEvent.Liar => (CLiar, 0.55f),
                NodeEvent.CrackedCross => (CCracked, 0.5f),
                _ => n.Equals(_prof.Goal) ? (CGoal, 0.55f)
                   : n.Equals(_prof.Start) ? (CStart, 0.5f)
                   : (CNode, 0.4f)
            };
        }

        static string LabelOf(Node n)
        {
            if (n.Equals(_prof.Goal)) return "駅";
            var ev = _prof.Events.TryGetValue(n, out var e) ? e : NodeEvent.None;
            return ev switch
            {
                NodeEvent.BrailleCross => "点",
                NodeEvent.Plaza => "広",
                NodeEvent.Hachi => "犬",
                NodeEvent.Child => "子",
                NodeEvent.Liar => "嘘",
                NodeEvent.CrackedCross => "割",
                _ => ""
            };
        }

        static void SpawnGrandpa()
        {
            _grandpa = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            _grandpa.name = "Grandpa";
            _grandpa.transform.position = BoardPos(_prof.Start) + new Vector3(0f, 0.3f, 0f);
            _grandpa.transform.localScale = new Vector3(0.25f, 0.25f, 0.25f);
            _grandpa.GetComponent<Renderer>().material.color = CGrandpa;
            _grandpa.transform.SetParent(_boardRoot.transform, true);
        }

        /// <summary>ノード位置の bounds に合わせて orthographic カメラをフィットさせる。</summary>
        static void FitCamera()
        {
            var cam = Camera.main;
            if (cam == null || _board == null) return;
            var minX = float.MaxValue; var maxX = float.MinValue;
            var minZ = float.MaxValue; var maxZ = float.MinValue;
            foreach (var n in _board.Nodes)
            {
                var p = _board.PositionOf(n);
                minX = Mathf.Min(minX, p.East); maxX = Mathf.Max(maxX, p.East);
                minZ = Mathf.Min(minZ, p.North); maxZ = Mathf.Max(maxZ, p.North);
            }
            if (minX > maxX) { minX = -1f; maxX = 1f; minZ = -1f; maxZ = 1f; }
            var cx = (minX + maxX) / 2f; var cz = (minZ + maxZ) / 2f;
            var spanX = maxX - minX; var spanZ = maxZ - minZ;
            var pad = Mathf.Max(3f, Mathf.Max(spanX, spanZ) * 0.15f);
            var aspect = cam.aspect > 0.01f ? cam.aspect : 16f / 9f;
            cam.orthographic = true;
            cam.orthographicSize = Mathf.Max(spanZ / 2f + pad, (spanX / 2f + pad) / aspect);
            cam.transform.position = new Vector3(cx, 10f, cz);
            cam.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
        }

        // ---------------------------------------------------- 毎フレーム
        public static void UpdateFrame()
        {
            if (_world == null || _boardRoot == null) return;

            // スムーズ移動
            var target = BoardPos(_world.Pos) + new Vector3(0f, 0.3f, 0f);
            if (_grandpa != null)
                _grandpa.transform.position = Vector3.Lerp(_grandpa.transform.position, target, 8f * Time.deltaTime);

            // ヒントハイライト時間
            if (_hintTimer > 0f)
            {
                _hintTimer -= Time.deltaTime;
                if (_hintTimer <= 0f) _hintNode = null;
            }

            UpdateHover();

            // Space で進行
            if (Input.GetKeyDown(KeyCode.Space) && _world.Gauge > 0) AdvanceTurn();
            // Z でアンドゥ
            if (Input.GetKeyDown(KeyCode.Z)) DoUndo();
            // R でステージリスタート
            if (Input.GetKeyDown(KeyCode.R)) RestartStage();
            // H でヒント
            if (Input.GetKeyDown(KeyCode.H)) DoHint();
        }

        static void AdvanceTurn()
        {
            PushUndo();
            var a = _world.PerceiveArrival(_placed);
            var v = _world.Judge(a);
            _message = _world.Apply(_placed, v);
            if (_message == "WIN") { _message = "★ クリア！"; _cleared.Add(_stageIdx); }
            else if (_message == "LOSE") _message = "帰宅……";
            _turn++;
        }

        static void RestartStage()
        {
            if (_stageIdx < 0 || _stageIdx >= _stages.Length) return;
            LoadStage(_stageIdx);
            _message = "ステージをリスタートしました";
        }

        static void DoHint()
        {
            _hintNode = null;
            if (_board == null) return;
            try
            {
                var r = PuzzleSolver.SolveMinMoves(_prof, _placed.Clone(), 3);
                if (r.MinMoves.HasValue && r.Actions.Count > 0)
                {
                    var (hn, hp) = r.Actions[0];
                    _hintNode = hn;
                    _hintTimer = 1f;
                    _message = $"ヒント: {hn} に {PieceName(hp.Kind)} を置く（残り {r.MinMoves} 手）";
                }
                else
                {
                    _message = "3手以内の解は見つかりませんでした";
                }
            }
            catch (System.Exception)
            {
                _message = "ヒント解読を中断しました";
            }
        }

        static string PieceName(PieceKind k) => k switch
        {
            PieceKind.Jk => "女子高生",
            PieceKind.Cop => "お巡りさん",
            PieceKind.Bike => "置き自転車",
            PieceKind.Fr => "強制右",
            _ => "強制左"
        };

        static void UpdateHover()
        {
            _hoverNode = null;
            var cam = Camera.main;
            if (cam != null && Physics.Raycast(cam.ScreenPointToRay(Input.mousePosition), out var hit, 500f))
            {
                Node n;
                if (_nodeObjects.TryGetValue(hit.transform.gameObject, out n))
                    _hoverNode = n;
            }
            foreach (var kv in _nodeRenderers)
            {
                var c = kv.Key.Equals(_hintNode) ? CHint
                    : kv.Key.Equals(_hoverNode) && _sel != null ? CHover
                    : NodeAppearance(kv.Key).c;
                kv.Value.material.color = c;
            }
        }

        // ---------------------------------------------------- マウスクリック配置
        public static void HandleClick()
        {
            if (_hoverNode != null && _sel != null)
                TryPlaceAt(_hoverNode.Value);
        }

        public static void TryPlaceAt(Node n)
        {
            if (_board == null || _sel == null) return;
            if (_kpLeft <= 0) { _message = "KP が足りません"; return; }
            if (!_board.Contains(n)) return;

            var exits = _board.Exits(n);

            // JK: aim（隣ノード指定）。デフォルトは駅方向（ArrowNode）、再クリックで Exits 順に巡回
            if (_sel.Value == PieceKind.Jk)
            {
                if (exits.Count == 0) { _message = "出口のないノードには置けません"; return; }
                if (_placed.TryGet(n, out var existing))
                {
                    if (existing.Kind != PieceKind.Jk) { _message = "既に別のピースが配置されています"; return; }
                    var cur = _jkAim.TryGetValue(n, out var i) ? i : DefaultAimIndex(n, exits);
                    var next = (cur + 1) % exits.Count;
                    if (next == cur) { _message = "このノードの出口は1つだけです"; return; }
                    PushUndo();
                    _jkAim[n] = next;
                    var aim = exits[next].To;
                    _placed.Place(n, new Piece(PieceKind.Jk, aim));
                    RefreshPieceVisuals();
                    _message = $"JK の向きを変更: {n} → {aim}";
                    return;
                }
                PushUndo();
                var idx = DefaultAimIndex(n, exits);
                _jkAim[n] = idx;
                var def = exits[idx].To;
                _placed.Place(n, new Piece(PieceKind.Jk, def));
                _kpLeft -= 1;
                AddPieceVisual(n, new Piece(PieceKind.Jk, def));
                _message = $"配置: JK @ {n} → {def}";
                return;
            }

            // その他のピースは方向指定不要
            if (_placed.TryGet(n, out _)) { _message = "既に配置されています"; return; }
            PushUndo();
            _placed.Place(n, new Piece(_sel.Value, Dir.E));
            _kpLeft -= 1;
            AddPieceVisual(n, new Piece(_sel.Value, Dir.E));
            _message = $"配置: {PieceName(_sel.Value)} @ {n}";
        }

        /// <summary>駅方向矢印（ArrowNode）の Exits 内位置。矢印が無ければ先頭。</summary>
        static int DefaultAimIndex(Node n, List<Exit> exits)
        {
            var arrow = _board.ArrowNode(n);
            if (!arrow.HasValue) return 0;
            for (var i = 0; i < exits.Count; i++)
                if (exits[i].To.Equals(arrow.Value)) return i;
            return 0;
        }

        static void AddPieceVisual(Node n, Piece p)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            go.name = $"P_{n.X}_{n.Y}";
            go.transform.position = BoardPos(n) + new Vector3(0f, 0.2f, 0f);
            go.transform.localScale = new Vector3(0.22f, 0.25f, 0.22f);
            go.GetComponent<Renderer>().material.color = p.Kind switch
            {
                PieceKind.Jk => CJk, PieceKind.Cop => CCop, _ => CBike
            };
            go.transform.SetParent(_boardRoot.transform, true);
            _pieces[n] = go;

            // JK は aim 方向に矢印を表示
            if (p.Kind == PieceKind.Jk && p.Aim.HasValue)
            {
                var arrow = GameObject.CreatePrimitive(PrimitiveType.Cube);
                arrow.name = "JkArrow";
                var b = _board.BearingBetween(n, p.Aim.Value);
                arrow.transform.position = BoardPos(n) + new Vector3(0f, 0.38f, 0f);
                arrow.transform.rotation = Quaternion.Euler(0f, b, 0f);
                arrow.transform.localScale = new Vector3(0.08f, 0.08f, 0.28f);
                arrow.GetComponent<Renderer>().material.color = new Color(0.55f, 0.15f, 0.3f);
                arrow.transform.SetParent(go.transform, true);
            }
        }

        static void RefreshPieceVisuals()
        {
            foreach (var kv in _pieces) if (kv.Value != null) Object.Destroy(kv.Value);
            _pieces.Clear();
            foreach (var kv in _placed.All) AddPieceVisual(kv.Key, kv.Value);
        }

        public static void DoUndo()
        {
            if (_undoStack.Count == 0) { _message = "戻せる操作がありません"; return; }
            (_world, _placed, _kpLeft, _turn) = _undoStack.Pop();
            _message = "元に戻しました";
            RefreshPieceVisuals();
        }

        static void PushUndo()
        {
            _undoStack.Push((_world.Clone(), _placed.Clone(), _kpLeft, _turn));
            if (_undoStack.Count > 20)
            {
                var arr = _undoStack.ToArray(); // 先頭が最新
                _undoStack.Clear();
                for (var i = 0; i < 20; i++) _undoStack.Push(arr[i]);
            }
        }

        // ---------------------------------------------------- HUD
        public static void DrawHUD()
        {
            if (_prof == null || _stages.Length == 0) return;
            var sw = Screen.width; var sh = Screen.height;

            // ステータスバー（上）
            GUI.backgroundColor = new Color(0.15f, 0.15f, 0.2f, 0.9f);
            GUI.Box(new Rect(0, 0, sw, 36), "");
            var (book, no, _) = _stages[_stageIdx];
            GUI.Label(new Rect(10, 4, 500, 28), $"<b><size=16>{book} {no}: {_prof.Name}</size></b>",
                new GUIStyle { normal = { textColor = Color.white } });
            GUI.Label(new Rect(sw - 250, 4, 240, 28),
                $"<color=white><b>KP {_kpLeft}</b> | 元気 {_world.Gauge} | Turn {_turn}</color>",
                new GUIStyle { richText = true });

            // ステージ選択ボタン列
            var btnW = 108f; var btnH = 24f; var gap = 4f;
            var perRow = Mathf.Max(1, Mathf.FloorToInt((sw - 16f) / (btnW + gap)));
            var rows = (int)Mathf.Ceil(_stages.Length / (float)perRow);
            for (var i = 0; i < _stages.Length; i++)
            {
                var (b, n, p) = _stages[i];
                var r = i / perRow; var c = i % perRow;
                var rect = new Rect(8 + c * (btnW + gap), 40 + r * (btnH + 2), btnW, btnH);
                var isCur = i == _stageIdx;
                GUI.backgroundColor = isCur ? new Color(0.3f, 0.6f, 0.9f) : new Color(0.22f, 0.22f, 0.28f, 0.9f);
                var star = _cleared.Contains(i) ? "★ " : "";
                if (GUI.Button(rect, $"{star}{b} {n}") && i != _stageIdx)
                    LoadStage(i);
            }

            // メッセージ
            var msgY = 40 + rows * (btnH + 2) + 4;
            GUI.Label(new Rect(10, msgY, sw - 20, 24), $"<color=white>{_message}</color>",
                new GUIStyle { richText = true });

            // ピースボタン（下）
            var pbW = 90f; var pbH = 50f; var pgap = 8f;
            var totalW = PieceDefs.Length * (pbW + pgap) - pgap;
            var startX = (sw - totalW) / 2;
            var y = sh - pbH - 12;
            for (var i = 0; i < PieceDefs.Length; i++)
            {
                var (code, name, kind, cost) = PieceDefs[i];
                var r = new Rect(startX + i * (pbW + pgap), y, pbW, pbH);
                var isSel = _sel == kind;
                GUI.backgroundColor = isSel ? new Color(0.3f, 0.7f, 0.3f) : new Color(0.25f, 0.25f, 0.3f, 0.9f);
                if (GUI.Button(r, $"<b>{name}</b>\nKP {cost}", new GUIStyle { richText = true, alignment = TextAnchor.MiddleCenter }))
                {
                    _sel = isSel ? null : kind;
                    _message = _sel != null ? $"{name} を選択（ノードをクリック）" : "選択解除";
                }
            }

            // 操作ヒント
            GUI.Label(new Rect(10, sh - pbH - 34, 500, 20),
                "<color=gray>Space=進行 | Z=元に戻す | R=リスタート | H=ヒント</color>",
                new GUIStyle { richText = true });
        }

        // ---------------------------------------------------- スモーク用内部フック（GameVisualSmoke が使用）
        public static int StagesCount => _stages.Length;
        public static string StageLabel(int i) => $"{_stages[i].book} {_stages[i].no}: {_stages[i].prof.Name}";
        public static GameObject BoardRoot => _boardRoot;
        public static int NodeCount => _nodeRenderers.Count;
        public static int DirectedEdgeCount { get { var c = 0; foreach (var n in _board.Nodes) c += _board.Exits(n).Count; return c; } }
        public static int LabelCount { get { var c = 0; foreach (var t in _boardRoot.GetComponentsInChildren<TextMesh>()) c++; return c; } }
        public static IEnumerable<Node> SmokeNodes => _board.Nodes;
        public static Node SmokeStart => _prof.Start;
        public static int SmokeExits(Node n) => _board.Exits(n).Count;
        public static Node? SmokeArrow(Node n) => _board.ArrowNode(n);
        public static int SmokePlacedCount { get { var c = 0; foreach (var _ in _placed.All) c++; return c; } }
        public static Piece? SmokePieceAt(Node n) => _placed.TryGet(n, out var p) ? p : (Piece?)null;
        public static bool SmokeHas(Node n) => _placed.TryGet(n, out _);
        public static Vector3 SmokeBoardPos(Node n) => BoardPos(n);
        public static bool SmokeIsMapped(GameObject go) => _nodeObjects.ContainsKey(go);
        public static bool SmokeHintSet => _hintNode.HasValue;
        public static string SmokeMessage => _message;
        public static void SelectKind(PieceKind k) { _sel = k; }
        public static void DoHintPublic() => DoHint();
    }

    /// <summary>一時スモーク（-executeMethod 用・検証後に削除）。</summary>
    public static class GameVisualSmoke
    {
        public static void Run()
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("GameVisualSmoke start");
            try
            {
                var camGo = new GameObject("SmokeCam");
                var cam = camGo.AddComponent<Camera>();
                cam.orthographic = true;
                cam.tag = "MainCamera";

                GameVisual.Initialize();
                sb.AppendLine("stages=" + GameVisual.StagesCount);

                for (var i = 0; i < GameVisual.StagesCount; i++)
                {
                    GameVisual.LoadStage(i);
                    CheckStage(sb, i, GameVisual.StageLabel(i));
                }
                PlacementTest(sb);
                HintTest(sb);
            }
            catch (System.Exception ex)
            {
                sb.AppendLine("EXCEPTION: " + ex);
            }
            sb.AppendLine("GameVisualSmoke end");
            System.IO.File.WriteAllText("/tmp/rft-visual-smoke.txt", sb.ToString());
            Debug.Log(sb.ToString());
        }

        static void CheckStage(System.Text.StringBuilder sb, int idx, string name)
        {
            var root = GameVisual.BoardRoot;
            if (root == null) { sb.AppendLine($"stage={name} NO ROOT"); return; }
            var rends = root.GetComponentsInChildren<Renderer>(true);
            var nodes = 0; var roads = 0; var labels = 0; var grandpa = 0; var ground = 0;
            foreach (var r in rends)
            {
                var go = r.gameObject;
                if (go.name.StartsWith("N_")) nodes++;
                else if (go.name == "Road") roads++;
                else if (go.name == "Grandpa") grandpa++;
                else if (go.name == "Ground") ground++;
                else if (go.name.StartsWith("L_")) labels++;
            }
            var expNodes = GameVisual.NodeCount;
            var expRoads = GameVisual.DirectedEdgeCount / 2;
            var expLabels = GameVisual.LabelCount;
            var ok = nodes == expNodes && roads == expRoads && labels == expLabels
                     && grandpa == 1 && ground == 1;
            var camSize = Camera.main != null ? Camera.main.orthographicSize : -1f;
            sb.AppendLine(
                $"stage={name} nodes={nodes}/{expNodes} roads={roads}/{expRoads} labels={labels}/{expLabels} " +
                $"grandpa={grandpa} ground={ground} camSize={camSize:F2} ok={ok}");
        }

        static void PlacementTest(System.Text.StringBuilder sb)
        {
            // JK を出口のある非スタートノードに配置 → aim=ArrowNode → 再クリックで巡回 → undo → COP
            Node? pick = null;
            foreach (var n in GameVisual.SmokeNodes)
            {
                if (n.Equals(GameVisual.SmokeStart)) continue;
                if (GameVisual.SmokeExits(n) > 0) { pick = n; break; }
            }
            if (!pick.HasValue) { sb.AppendLine("placement: no node"); return; }
            var n0 = pick.Value;

            GameVisual.SelectKind(PieceKind.Jk);
            var arrow = GameVisual.SmokeArrow(n0);
            // 直接: デフォルト配置
            var before = GameVisual.SmokePlacedCount;
            GameVisual.TryPlaceAt(n0);
            var p1 = GameVisual.SmokePieceAt(n0);
            var aimOK = p1.HasValue && p1.Value.Kind == PieceKind.Jk
                        && p1.Value.Aim.HasValue && p1.Value.Aim.Value.Equals(arrow);
            var placedCnt = GameVisual.SmokePlacedCount;
            sb.AppendLine($"placement JK aim=arrow:{aimOK} placed:{placedCnt > before}");

            // 再クリックで Exits 順に巡回
            GameVisual.TryPlaceAt(n0);
            var p2 = GameVisual.SmokePieceAt(n0);
            var cycled = p2.HasValue && p2.Value.Aim.HasValue
                         && !p2.Value.Aim.Value.Equals(p1.Value.Aim.Value);
            var placed2 = GameVisual.SmokePlacedCount;
            sb.AppendLine($"placement JK cycle:{cycled} placed-still-one:{placed2 == placedCnt}");

            // undo×2 で元へ
            GameVisual.DoUndo(); GameVisual.DoUndo();
            var undone = !GameVisual.SmokeHas(n0);
            sb.AppendLine($"placement undo×2:{undone}");

            // COP は aim なし
            GameVisual.SelectKind(PieceKind.Cop);
            GameVisual.TryPlaceAt(n0);
            var p3 = GameVisual.SmokePieceAt(n0);
            var copOK = p3.HasValue && p3.Value.Kind == PieceKind.Cop && !p3.Value.Aim.HasValue;
            sb.AppendLine($"placement cop:{copOK}");
            GameVisual.DoUndo();

            // レイキャスト逆引き（ノード直上から真下）
            var cam = Camera.main;
            if (cam != null)
            {
                var p = GameVisual.SmokeBoardPos(n0) + new Vector3(0f, 10f, 0f);
                if (Physics.Raycast(new Ray(p, Vector3.down), out var hit, 500f))
                    sb.AppendLine("raycast hit=" + hit.transform.name + " isNode="
                        + GameVisual.SmokeIsMapped(hit.transform.gameObject));
            }
        }

        static void HintTest(System.Text.StringBuilder sb)
        {
            GameVisual.DoHintPublic();
            sb.AppendLine("hint: nodeSet=" + GameVisual.SmokeHintSet + " msg=" + GameVisual.SmokeMessage);
        }
    }
}
