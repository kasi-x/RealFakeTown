#!/usr/bin/env python3
"""OSM (OpenStreetMap) 歩行者ネットワーク → パズル盤面グラフ変換ツール

Overpass API から丸の内周辺の歩行者ネットワークを取得し、
パズルの盤面グラフ（ノード=交差点、辺=歩道）に変換する。

使い方:
  python3 tools/osm_to_graph.py                 # デフォルト範囲でダウンロード

生成した osm_marunouchi.json は C# 側の OsmGraph（Assets/RealFakeTown/Sim/OsmGraph.cs）が
Assets/StreamingAssets/ に置いて読み込む（Unity で遊ぶ）。

依存: urllib（標準ライブラリのみ。osmnx 不要）
"""
import json
import os
import sys
import urllib.request
from collections import deque

# 丸の内（皇居〜東京駅）のバウンディングボックス
BBOX_S, BBOX_W, BBOX_N, BBOX_E = 35.6790, 139.7580, 35.6875, 139.7680

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = f"""[out:json][timeout:25];
way["highway"~"^(footway|pedestrian|steps|path|living_street|residential|unclassified|service)$"]
  ({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
out geom;
"""


def download_osm() -> dict:
    """Overpass API から OSM データをダウンロードする"""
    print("Overpass API から OSM データを取得中...")
    import urllib.parse
    data = urllib.parse.urlencode({"data": QUERY}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data)
    req.add_header("User-Agent", "RealFakeTown/0.1")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    print(f"  取得: {len(result.get('elements', []))} elements")
    return result


def build_graph(osm_data: dict) -> dict:
    """OSM データからパズルグラフを構築する（交差点=ノード、辺=歩道）"""
    # 1. 全ノードを収集（座標付き）
    node_coords: dict[int, tuple[float, float]] = {}
    ways: list[list[dict]] = []

    for elem in osm_data.get("elements", []):
        if elem["type"] != "way":
            continue
        geom = elem.get("geometry", [])
        if len(geom) < 2:
            continue
        ways.append(geom)
        for pt in geom:
            nid = pt.get("node_id") or id(pt)
            lat, lon = pt["lat"], pt["lon"]
            # node_id がない場合は座標でユニーク化
            coord_key = round(lat, 7), round(lon, 7)
            if coord_key not in {(v[0], v[1]) for v in node_coords.values()}:
                node_coords[coord_key] = (lat, lon)

    # 2. 座標の近いノードをマージ（交差点検出: 3以上の道が集まる点）
    # 簡易実装: 座標をグリッドにスナップして交差点を検出
    degree: dict[tuple[float, float], int] = {}
    for way in ways:
        for i, pt in enumerate(way):
            key = (round(pt["lat"], 7), round(pt["lon"], 7))
            if i == 0 or i == len(way) - 1:
                degree[key] = degree.get(key, 0) + 1
            else:
                # 中間点: 前後の角度が大きければ交差点候補
                degree[key] = degree.get(key, 0)

    # 交差点 = 頂点（way の端点）として 2 回以上現れる座標
    intersection_keys = {k for k, v in degree.items() if v >= 2}

    # 3. ノードIDを割り当て
    all_keys = sorted(intersection_keys | set(degree.keys()))
    key_to_id: dict[tuple[float, float], int] = {}
    node_list: list[dict] = []
    for key in all_keys:
        nid = len(node_list)
        key_to_id[key] = nid
        node_list.append({"id": nid, "lat": key[0], "lon": key[1]})

    # 4. 辺を構築（way の連続するノードペア）
    edge_set: set[tuple[int, int]] = set()
    for way in ways:
        prev_key = None
        for pt in way:
            key = (round(pt["lat"], 7), round(pt["lon"], 7))
            if prev_key is not None and prev_key != key:
                a, b = key_to_id[prev_key], key_to_id[key]
                if a != b:
                    edge_set.add((min(a, b), max(a, b)))
            prev_key = key

    # 5. 座標をパズル用の正規化座標に変換（0始まりの整数グリッド）
    lats = [n["lat"] for n in node_list]
    lons = [n["lon"] for n in node_list]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)

    GRID_SIZE = 30  # パズルの最大グリッドサイズ
    lat_range = lat_max - lat_min or 1e-9
    lon_range = lon_max - lon_min or 1e-9
    scale = GRID_SIZE / max(lat_range, lon_range)

    for n in node_list:
        gy = round((lat_max - n["lat"]) * scale)  # 北が上（y=0）
        gx = round((n["lon"] - lon_min) * scale)
        n["gx"], n["gy"] = gx, gy

    # グリッド座標の重複をマージ
    grid_map: dict[tuple[int, int], int] = {}
    merge = {}
    for n in node_list:
        gk = (n["gx"], n["gy"])
        if gk in grid_map:
            merge[n["id"]] = grid_map[gk]
        else:
            grid_map[gk] = n["id"]
            merge[n["id"]] = n["id"]

    # 辺をマージ後のIDで再構築
    final_edges: set[tuple[int, int]] = set()
    for a, b in edge_set:
        a2, b2 = merge.get(a, a), merge.get(b, b)
        if a2 != b2:
            final_edges.add((min(a2, b2), max(a2, b2)))

    # 孤立ノードを除去
    connected = set()
    for a, b in final_edges:
        connected.add(a)
        connected.add(b)

    remap: dict[int, int] = {}
    for old_id in sorted(connected):
        remap[old_id] = len(remap)

    final_nodes = []
    for n in node_list:
        if n["id"] in connected:
            new_id = remap[n["id"]]
            final_nodes.append({"id": new_id, "gx": n["gx"], "gy": n["gy"],
                                "lat": n["lat"], "lon": n["lon"]})

    final_edges = [(remap[a], remap[b]) for a, b in final_edges if a in remap and b in remap]

    return {"nodes": final_nodes, "edges": sorted(set(final_edges)),
            "bbox": {"south": BBOX_S, "west": BBOX_W, "north": BBOX_N, "east": BBOX_E}}


def save_json(graph: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"  保存: {path} (ノード {len(graph['nodes'])}, 辺 {len(graph['edges'])})")


if __name__ == "__main__":
    try:
        data = download_osm()
        graph = build_graph(data)
        out_path = "Assets/RealFakeTown/Sim/osm_marunouchi.json"
        save_json(graph, out_path)
        print(f"\n完了！ {out_path} を StageProfile で読み込めます。")
    except Exception as ex:
        print(f"\n[WARN] OSMダウンロード失敗: {ex}")
        print("  → オフラインのため手組みの丸の内グラフを使用してください。")
        print("  → tools/beginner_stage.py --book marunouchi で既存の盤面が遊べます。")
        print("  → ネットワーク復旧後に再実行してください。")
        sys.exit(1)
