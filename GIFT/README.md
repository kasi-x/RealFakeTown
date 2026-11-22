# GIFT — RealFakeTown を別 PC（Windows）で再現する一式

RealFakeTown を**別の Windows 機で再現する**ための自己完結パッケージです。
GitHub で送る想定のもの（Unity プロジェクトのソース・docs・tools）は `project/` に同梱済みで、
重いデータは git に入れず公式配布元から取得→再生成します。

```
GIFT/
  Makefile         Windows 用ブートストラップ（Git Bash / MSYS2 / WSL）
  README.md        これ
  PROVENANCE.md    出典・ライセンス
  tools/make_source.py  同梱ソース（project/）の再生成
  project/        ★プロジェクト本体（Assets を含む。Unity プロジェクトルート）
  vendor/, out/, .shim/  取得物・生成物（git 管理外）
```

> **注意**: 本家リポジトリでは `Assets/`（ゲーム本体の C#）が**まだコミットされていません**。
> `make source` は「追跡ファイル＋未追跡（無視されていない）ファイル」を写すので、
> `Assets/` も `docs/` も `tools/` も取りこぼしません。

## 0. 同梱するもの / 取得するもの

| 区分 | 中身 | 大きさ | 手段 |
| --- | --- | --- | --- |
| **同梱** | `GIFT/project/` = Unity プロジェクト（Assets・Packages・ProjectSettings・docs・tools） | 約 1 MB / 約 80 ファイル | `GIFT.zip` に含まれる（`make zip`） |
| 取得 | PLATEAU SDK for Unity v4.3.0（＋任意で Toolkits v2.3.0） | 762 MB（＋1.3 GB） | `make setup`（公式 GitHub リリース） |
| 取得 | 千代田区 2025 CityGML（13101） | 数百 MB | `make setup`（公式ポータル） |
| 取得 | OpenStreetMap 歩行ネットワーク（Overpass API） | 数 MB | `python tools/osm_to_graph.py`（必要時） |
| 生成 | 歩行グラフ `artifacts/city_graph/` | 数 MB | `make graph` |
| 生成 | Unity の `Library/` | 約 3 GB | Unity 初回オープン |

**ディスクは 15 GB 以上**を目安に。

## 1. 前提（Windows）

| 必要なもの | 備考 |
| --- | --- |
| **Unity 6000.3.8f1** | Unity Hub で導入。6000.3 系を維持（PLATEAU SDK v4.3.0 の宣言に合わせる） |
| **GNU Make** | Git Bash / MSYS2 / WSL。`choco install make` でも可 |
| Python 3.10+ | `make graph`（標準ライブラリのみ）と `make source` |
| Git / curl | Windows 10 以降は `curl.exe` 同梱 |

> `make` は PowerShell では動きません。**Git Bash などから実行**してください。
> 本家 Makefile は `python3` を直接呼ぶため、GIFT は `.shim/python3` を作って
> PATH の先頭に置きます（Windows に `python3` が無くても `python` があれば通ります）。

## 2. 手順

```bash
unzip RealFakeTown-GIFT.zip -d RealFakeTown-GIFT && cd RealFakeTown-GIFT

make check        # Unity / python / curl / git / 空き容量
make setup        # PLATEAU SDK tgz + 千代田区 CityGML を vendor/ へ（約2.1GB）
make verify       # ヘッドレスでパッケージ解決＋コンパイル検証（失敗で非0）
make graph        # 歩行グラフを CityGML から再生成（artifacts/city_graph/）

# まとめて:
make all          # = check + setup + verify
```

`make verify` が通れば、Unity Hub で `project/` を開いて作業できます。

### 上書き

```bash
make all UNITY="C:/Program Files/Unity/Hub/Editor/6000.3.8f1/Editor/Unity.exe"
make graph GRAPH_MIN_WIDTH=8 GRAPH_TARGET_NODES=12
make setup REPO=..          # 既存クローンをそのまま使う
```

## 3. 何がどこから来るか

```
公式 GitHub リリース ──► GIFT/vendor/PLATEAU-SDK-*.tgz ──► Packages/manifest.json (file:)
公式ポータル ─────────► GIFT/vendor/citygml/13101_....zip ─► unzip ─► vendor/citygml/udx
                                                    │
              tools/gen_city_graph.py（stdlib のみ）└──► artifacts/city_graph/（GeoJSON+統計+SVG/PNG）
Overpass API ──► tools/osm_to_graph.py ──► osm_marunouchi.json（OsmGraph.cs が読む）
```

## 4. つまずきやすい所

- **CityGML の直リンクは変わり得ます。** `make setup` が失敗したら
  <https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025> から現在の zip を取得し、
  `GIFT/vendor/citygml/` に置くか `~/Downloads/` に置いて再実行（本家 Makefile がフォールバックします）。
- **`vendor/` は git 管理外**です。別 PC にコピーする必要はなく、`make setup` で再取得します。
- **`Library/` は再生成**（初回オープンに 10 分前後）。
- **`make verify` が非0で落ちる**ときは Unity のログ（本家 `make verify` は `/tmp/rft-unity-verify.log`）を確認。
  Windows ではログ先を変えたい場合、本家 Makefile の `verify` を直接叩いてください。
- **`artifacts/`（歩行グラフ）は派生物**。`make graph` で作り直せます（約 7 秒）。

## 5. 動作確認

```bash
cd project
# グラフ生成の自己テスト（Unity 不要）
python3 tools/gen_city_graph.py --selftest

# ステージの自動プレイ／ソルバ QA（Unity 不要）
python3 tools/beginner_stage.py --demo
python3 tools/beginner_stage.py --solve 1
```

`gen_city_graph.py --selftest` と `beginner_stage.py --solve` が通れば、
データとロジックの再現は成功しています。
