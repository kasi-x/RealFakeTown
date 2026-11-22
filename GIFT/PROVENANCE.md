# 出典・ライセンス（GIFT で取得・生成するもの）

再現に必要なデータはすべて外部の配布元から取得し、ライセンスは各配布元に従います。

| 種別 | 配布元 | ライセンス / 条件 |
| --- | --- | --- |
| **RealFakeTown 本体**（`GIFT/project/`） | このリポジトリ | **MIT License**（Copyright (c) 2026 魚占３、`LICENSE` を参照） |
| **PLATEAU SDK for Unity v4.3.0**<br>`PLATEAU-SDK-for-Unity-v4.3.0.0.tgz` | https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unity/releases/tag/v4.3.0 | Project PLATEAU の定めに従う（リポジトリの LICENSE を確認） |
| **PLATEAU SDK Toolkits for Unity v2.3.0**（任意）<br>`PLATEAU-SDK-Toolkits-for-Unity-v2.3.0.2.tgz` | https://github.com/Project-PLATEAU/PLATEAU-SDK-Toolkits-for-Unity/releases/tag/v2.3.0 | 同上。**本プロジェクトには未配線**（`make toolkits` は取得のみ） |
| **千代田区 3D都市モデル（CityGML, 13101, 2025年度, op）** | https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025 | Project PLATEAU サイトポリシー（CC BY 4.0 及び政府標準利用規約 2.0）。**出典の明記が必要** |
| **OpenStreetMap 歩行ネットワーク**（`tools/osm_to_graph.py` が Overpass API 経由で取得） | https://overpass-api.de/api/interpreter ／ © OpenStreetMap contributors | **ODbL 1.0**。生成物（`osm_marunouchi.json`、それに由来する盤面）を配布・公表する場合は「© OpenStreetMap contributors」の表示と ODbL の条件に従うこと |
| **Unity** | Unity Hub | Unity のライセンス条件（6000.3.8f1 系） |

## 注意

- このリポジトリ本体は **MIT** ですが、**同梱・取得するデータのライセンスは別**です。
  とくに CityGML（PLATEAU）と OSM は**出典明記**が条件で、OSM 由来の派生物には **ODbL** が及びます。
  ゲームを公開する際はクレジット表示を入れてください。
- 重いデータ（`vendor/`、`artifacts/`、`Library/`）は**再配布せず**、各配布元から取得する運用に
  してください（`Makefile` がその形になっています）。
- `GIFT/project/` は**このリポジトリの写し**です（追跡＋未追跡のファイル）。元リポジトリで
  コミットが進んだら `make source` で作り直してください。
