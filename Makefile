# RealFakeTown — bootstrap for big git-ignored assets + headless checks.
#
# Big files (SDK tarballs, CityGML) live in vendor/ and never enter git.
# `make setup` prepares everything a fresh clone needs to open the project
# in Unity; `make verify` runs a headless resolve + compile check.

UNITY        := /Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity
SDK_TGZ      := vendor/PLATEAU-SDK-for-Unity-v4.3.0.0.tgz
TOOLKITS_TGZ := vendor/PLATEAU-SDK-Toolkits-for-Unity-v2.3.0.2.tgz
CITYGML_ZIP  := vendor/citygml/13101_chiyoda-ku_pref_2025_citygml_1_op.zip
CITYGML_UDX  := vendor/citygml/udx

SDK_URL      := https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unity/releases/download/v4.3.0/PLATEAU-SDK-for-Unity-v4.3.0.0.tgz
TOOLKITS_URL := https://github.com/Project-PLATEAU/PLATEAU-SDK-Toolkits-for-Unity/releases/download/v2.3.0/PLATEAU-SDK-Toolkits-for-Unity-v2.3.0.2.tgz
# files.geospatial.jp is not reachable from every network, so the local copy
# in ~/Downloads (if any) is used as a fallback for the CityGML zip.
CITYGML_PORTAL    := https://www.mlit.go.jp/plateau/open-data
CITYGML_DOWNLOADS := $(HOME)/Downloads/$(notdir $(CITYGML_ZIP))

.PHONY: setup sdk toolkits citygml verify
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
	@if [ -f "$(CITYGML_DOWNLOADS)" ]; then \
		cp "$(CITYGML_DOWNLOADS)" $@; \
	else \
		echo "CityGML zip not found. Download the 2025 千代田区 CityGML from:"; \
		echo "  $(CITYGML_PORTAL)   (東京都 → 千代田区 → CityGML)"; \
		echo "Save it as $(CITYGML_ZIP) or ~/Downloads/$(notdir $(CITYGML_ZIP)), then rerun 'make citygml'."; \
		exit 1; \
	fi

verify:
	$(UNITY) -batchmode -projectPath . -quit -logFile /tmp/rft-unity-verify.log
	@! grep -qE "error CS|Compilation failed" /tmp/rft-unity-verify.log
	@echo "verify: OK (packages resolved, no compile errors)"
