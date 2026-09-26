# RealFakeTown — bootstrap for big git-ignored assets + headless checks.
#
# Big files (SDK tarballs, CityGML) live in vendor/ and never enter git.
# `make setup` prepares everything a fresh clone needs to open the project
# in Unity; `make verify` runs a headless resolve + compile check;
# `make graph` rebuilds the walkable graph from the corridor CityGML.

UNITY        := /Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity
SDK_TGZ      := vendor/PLATEAU-SDK-for-Unity-v4.3.0.0.tgz
TOOLKITS_TGZ := vendor/PLATEAU-SDK-Toolkits-for-Unity-v2.3.0.2.tgz
CITYGML_ZIP  := vendor/citygml/13101_chiyoda-ku_pref_2025_citygml_1_op.zip
CITYGML_UDX  := vendor/citygml/udx

# 丸の内回廊 (皇居東側〜東京駅) — 3rd-mesh tran tiles
GRAPH_MESHES := 53394611 53394620 53394621 53394610
GRAPH_OUT    := artifacts/city_graph

SDK_URL      := https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unity/releases/download/v4.3.0/PLATEAU-SDK-for-Unity-v4.3.0.0.tgz
TOOLKITS_URL := https://github.com/Project-PLATEAU/PLATEAU-SDK-Toolkits-for-Unity/releases/download/v2.3.0/PLATEAU-SDK-Toolkits-for-Unity-v2.3.0.2.tgz
# Official PLATEAU portal resource (CityGML v5). The URL is content-addressed;
# if a future re-release breaks it, fetch the current CityGML link from
# the dataset page below. A local zip in ~/Downloads is a secondary fallback.
CITYGML_URL       := https://assets.cms.plateau.reearth.io/assets/d1/e11ec4-3ad6-4923-a441-32cbd7455dee/13101_chiyoda-ku_pref_2025_citygml_1_op.zip
CITYGML_PORTAL    := https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025
CITYGML_DOWNLOADS := $(HOME)/Downloads/$(notdir $(CITYGML_ZIP))

.PHONY: setup sdk toolkits citygml verify graph
setup: sdk citygml

sdk: $(SDK_TGZ)
$(SDK_TGZ):
	@mkdir -p $(dir $@)
	curl -fL --retry 3 -o $@ $(SDK_URL)

# Optional add-on (rendering/game/maps toolkits); not wired into the project.
toolkits: $(TOOLKITS_TGZ)
$(TOOLKITS_TGZ):
	@mkdir -p $(dir $@)
	curl -fL --retry 3 -o $@ $(TOOLKITS_URL)

citygml: $(CITYGML_UDX)
$(CITYGML_UDX): $(CITYGML_ZIP)
	unzip -q -o $(CITYGML_ZIP) -d $(dir $(CITYGML_UDX))
	@touch $@

$(CITYGML_ZIP):
	@mkdir -p $(dir $@)
	@curl -fL --retry 3 -o $@ $(CITYGML_URL) || { \
		echo "Direct download failed, trying a local copy..."; \
		if [ -f "$(CITYGML_DOWNLOADS)" ]; then \
			cp "$(CITYGML_DOWNLOADS)" $@; \
		else \
			echo "CityGML zip unavailable. Download it from:"; \
			echo "  $(CITYGML_PORTAL)"; \
			echo "Save it as $(CITYGML_ZIP) or ~/Downloads/$(notdir $(CITYGML_ZIP)), then rerun 'make citygml'."; \
			exit 1; \
		fi; \
	}

verify:
	$(UNITY) -batchmode -projectPath . -quit -logFile /tmp/rft-unity-verify.log
	@! grep -qE "error CS|Compilation failed" /tmp/rft-unity-verify.log
	@echo "verify: OK (packages resolved, no compile errors)"

# Walkable graph from CityGML (no Unity needed): GeoJSON + stats + SVG/PNG
# render into $(GRAPH_OUT); curated copies for docs live in docs/concepts.
graph: $(CITYGML_UDX)
	python3 tools/gen_city_graph.py $(GRAPH_MESHES) --root vendor/citygml \
		--bbox marunouchi --out $(GRAPH_OUT)
