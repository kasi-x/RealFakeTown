# ─────────────────────────────────────────────────────────────────────────────
#  RealFakeTown — Windows 再現用ブートストラップ（GIFT）
#
#  重いデータ（PLATEAU SDK tgz、千代田区 CityGML）と派生物（Library/、
#  artifacts/city_graph）は git に入れず、公式配布元から取得し、このプロジェクトで
#  再生成する。GitHub で送る想定のもの（Unity プロジェクトのソース・docs・tools）は
#  GIFT/project/ に同梱済み。
#
#  使い方（Git Bash / MSYS2 / WSL。PowerShell 不可）:
#      cd GIFT
#      make check          # 前提確認（Unity / python / curl / 空き容量）
#      make all            # 前提 → 同梱ソース展開 → 重いデータ取得 → 検証
#
#  個別に:
#      make source         1. GIFT/project/ にソースを写す（送る側で実行）
#      make setup          2. PLATEAU SDK tgz + 千代田区 CityGML を vendor/ へ（約2.1GB）
#      make verify         3. ヘッドレスでパッケージ解決＋コンパイル検証
#      make graph          4. 歩行グラフを CityGML から再生成（artifacts/）
#      make toolkits       5. Toolkits tgz（任意。プロジェクトには未配線）
#      make zip            6. 受け渡し用 GIFT.zip を作る
#      make send           7. zip を作り直して Taildrop で送る（送る側の操作）
#
#  上書き例:
#      make all UNITY="C:/Program Files/Unity/Hub/Editor/6000.3.8f1/Editor/Unity.exe"
#      make graph GRAPH_MIN_WIDTH=8
# ─────────────────────────────────────────────────────────────────────────────

SHELL       := /bin/sh
.SHELLFLAGS := -ec

GIFT        := $(CURDIR)
# プロジェクトルート。同梱ソース（GIFT/project）を既定にし、既存クローンを使う場合は REPO=..。
REPO        ?= $(GIFT)/project

# Windows 既定。Git Bash からは /c/... 形式でも可。
UNITY       ?= C:/Program Files/Unity/Hub/Editor/6000.3.8f1/Editor/Unity.exe
PY          ?= python
# 本家 Makefile は `python3` を直接呼ぶので、Windows 用に shim を噛ませる
# ── 送り先（Tailscale / Taildrop）。送る側＝このマシンで `make send` を実行する。
TAILDROP   ?= pc-1:
GIFT_NAME  ?= RealFakeTown-GIFT.zip

SHIM        := $(GIFT)/.shim
PY3         := $(SHIM)/python3

# グラフ生成パラメータ（本家 Makefile と同じ既定。必要なら上書き）
GRAPH_MESHES        ?= 53394611 53394620 53394621 53394610
GRAPH_MIN_WIDTH     ?= 6.0
GRAPH_CORRIDOR_BAND ?= 200
GRAPH_MERGE_TOL     ?= 15.0
GRAPH_TARGET_NODES  ?= 15

.PHONY: help check all source setup toolkits verify graph zip send clean

help:
	@sed -n '2,26p' $(GIFT)/Makefile | sed 's/^# \{0,1\}//'

# ── 前提確認 ────────────────────────────────────────────────────────────────
check:
	@echo "── 前提確認 ─────────────────────────────"
	@command -v curl >/dev/null || { echo "NG: curl がありません"; exit 1; }
	@command -v git  >/dev/null || { echo "NG: git がありません";  exit 1; }
	@if command -v $(PY) >/dev/null 2>&1; then P=$(PY); \
	 elif command -v python3 >/dev/null 2>&1; then P=python3; \
	 elif command -v py >/dev/null 2>&1; then P=py; \
	 else echo "NG: python が見つかりません"; exit 1; fi; \
	 echo "OK: $$P $$($$P --version 2>&1)"; \
	 $(MAKE) --no-print-directory $(PY3) PY="$$P"
	@[ -f "$(UNITY)" ] && echo "OK: Unity $(UNITY)" || echo "!! Unity が見つかりません: $(UNITY)（make UNITY=... で指定）"
	@[ -f "$(REPO)/ProjectSettings/ProjectVersion.txt" ] && echo "OK: プロジェクトルート $(REPO)" || { echo "NG: プロジェクトが見つかりません（make source か REPO=.. を指定）"; exit 1; }
	@echo "── 空き容量（目安 15GB 以上）──"; df -h "$(REPO)" | tail -1

# ── 同梱ソース（送る側で実行）───────────────────────────────────────────────
source:
	@$(PY) "$(GIFT)/tools/make_source.py" --repo "$(GIFT)/.." --out "$(REPO)" --clean
	@echo "OK: $(REPO)（git 管理外。.gitignore 済み）"

# ── 本家 Makefile への委譲（UNITY を Windows に差し替えて渡す）──────────────
setup: $(PY3)
	@$(MAKE) -C "$(REPO)" setup UNITY="$(UNITY)"

toolkits: $(PY3)
	@$(MAKE) -C "$(REPO)" toolkits

verify: $(PY3)
	@$(MAKE) -C "$(REPO)" verify UNITY="$(UNITY)"
	@echo "verify: OK"

graph: $(PY3)
	@PATH="$(SHIM):$$PATH" $(MAKE) -C "$(REPO)" graph UNITY="$(UNITY)" \
	  GRAPH_MESHES="$(GRAPH_MESHES)" GRAPH_MIN_WIDTH="$(GRAPH_MIN_WIDTH)" \
	  GRAPH_CORRIDOR_BAND="$(GRAPH_CORRIDOR_BAND)" GRAPH_MERGE_TOL="$(GRAPH_MERGE_TOL)" \
	  GRAPH_TARGET_NODES="$(GRAPH_TARGET_NODES)"

# python3 が無い Windows 用の shim（本家 Makefile の `python3` 呼び出しを満たす）
$(PY3):
	@mkdir -p "$(SHIM)"
	@printf '#!/bin/sh\nexec "%s" "$$@"\n' "$(PY)" > "$(PY3)"
	@chmod +x "$(PY3)"
	@echo "shim: $(PY3) -> $(PY)"

# ── 受け渡し用 zip ──────────────────────────────────────────────────────────
zip: source
	@mkdir -p "$(GIFT)/out"
	@rm -f "$(GIFT)/out/RealFakeTown-GIFT.zip"
	@cd "$(GIFT)" && "$(PY)" -c "import pathlib,zipfile; \
	  root=pathlib.Path('.'); z=zipfile.ZipFile('out/RealFakeTown-GIFT.zip','w',zipfile.ZIP_DEFLATED); \
	  [z.write(f,f.as_posix()) for f in sorted(root.rglob('*')) if f.is_file() and not f.as_posix().startswith(('out/','vendor/','.shim/')) and not f.name.endswith('.log') and '__pycache__' not in f.as_posix()]; z.close(); print('wrote out/RealFakeTown-GIFT.zip')"
	@shasum -a 256 "$(GIFT)/out/RealFakeTown-GIFT.zip" 2>/dev/null || sha256sum "$(GIFT)/out/RealFakeTown-GIFT.zip"
	@ls -la "$(GIFT)/out/RealFakeTown-GIFT.zip"

# 送る（zip を作り直して Taildrop へ）
send: zip
	@tailscale file cp --name "$(GIFT_NAME)" "$(GIFT)/out/$(GIFT_NAME)" "$(TAILDROP)" \
	  && echo "sent $(GIFT_NAME) -> $(TAILDROP)"
	@shasum -a 256 "$(GIFT)/out/$(GIFT_NAME)" 2>/dev/null || sha256sum "$(GIFT)/out/$(GIFT_NAME)"

clean:
	@rm -rf "$(SHIM)"

all: check setup verify
	@echo "── 完了。Unity Hub で $(REPO) を開いてください（6000.3.8f1）──"
