#!/usr/bin/env bash
# Download the PLATEAU SDK for Unity tarball into vendor/.
#
# Packages/manifest.json references the tarball via file:../vendor/, so this
# must succeed once before the Unity project can be opened (fresh clone or
# after an SDK version bump).
set -euo pipefail
cd "$(dirname "$0")/.."

version="4.3.0"
url="https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unity/releases/download/v${version}/PLATEAU-SDK-for-Unity-v${version}.0.tgz"
out="vendor/PLATEAU-SDK-for-Unity-v${version}.0.tgz"

if [ -f "$out" ]; then
    echo "Already present: $out"
    exit 0
fi

mkdir -p vendor
echo "Downloading PLATEAU SDK v${version} (~762 MB)..."
curl -fL --retry 3 -o "$out" "$url"
echo "Done: $out"
