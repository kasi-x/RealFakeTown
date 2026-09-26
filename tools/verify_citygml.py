#!/usr/bin/env python3
"""Step 0 data verification: quantify what the Chiyoda-ku CityGML offers
for the walking-path board, straight from the GML (no Unity import needed).

Usage:
    python3 tools/verify_citygml.py 53394611 53394620 53394621 53394610

Reads udx/{tran,bldg}/<mesh>_*.gml under vendor/citygml (or the path given
with --root) and prints per-mesh and summary stats:
  tran  - road count, class/function/usage codes, LOD surfaces, lod0Network
          (centerline curves), TrafficArea function breakdown (sidewalk!),
          AuxiliaryTrafficArea function breakdown
  bldg  - building count per LOD, measuredHeight coverage
Codelists under codelists/ are used to translate codes to Japanese labels.
"""

import argparse
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

TRAN = "http://www.opengis.net/citygml/transportation/2.0"
BLDG = "http://www.opengis.net/citygml/building/2.0"
GML = "http://www.opengis.net/gml"
CORE = "http://www.opengis.net/citygml/2.0"


def t(tag):
    return f"{{{TRAN}}}{tag}"


def g(tag):
    return f"{{{GML}}}{tag}"


def b(tag):
    return f"{{{BLDG}}}{tag}"


def c(tag):
    return f"{{{CORE}}}{tag}"


def load_codelists(root: Path):
    """code -> Japanese description, per codelist name."""
    out = {}
    for f in (root / "codelists").glob("*.xml"):
        table = {}
        try:
            tree = ET.parse(f)
        except ET.ParseError:
            continue
        for d in tree.iter(g("Definition")):
            name = d.find(g("name"))
            desc = d.find(g("description"))
            if name is not None and name.text and desc is not None:
                table[name.text.strip()] = desc.text.strip()
        out[f.stem] = table
    return out


def vertices(elem, surface_tag):
    """Count posList coordinates inside a lod*MultiSurface-ish property."""
    n = 0
    surf = elem.find(surface_tag)
    if surf is None:
        return 0
    for pos in surf.iter(g("posList")):
        n += len(pos.text.split()) // 3 if pos.text else 0
    return n


def lod_key(elem, prefix):
    """Return f'{prefix}{lod}' for the first lod surface present, else None."""
    for lod in (0, 1, 2, 3):
        if elem.find(f"{prefix}{lod}MultiSurface") is not None:
            return f"LOD{lod}"
    return None


def analyze_tran(path: Path, cl):
    roads = 0
    road_class = Counter()
    lod_tags = Counter()
    roads_all_lods = 0
    net_curves = 0
    ta_function = Counter()
    ata_function = Counter()
    ta_vertices = 0
    road_vertices = 0

    tree = ET.parse(path)
    # Road-level lod2/3 surfaces reference polygons by xlink; resolve them.
    xlink = "{http://www.w3.org/1999/xlink}href"
    poly_by_id = {}
    for poly in tree.iter(g("Polygon")):
        pid = poly.get(g("id"))
        if pid:
            poly_by_id[pid] = sum(
                len(p.text.split()) // 3 for p in poly.iter(g("posList")) if p.text
            )
    for road in tree.iter(t("Road")):
        roads += 1
        cls = road.find(t("class"))
        if cls is not None and cls.text:
            road_class[cls.text.strip()] += 1
        n_lods = 0
        for lod in (1, 2, 3):
            surf = road.find(t(f"lod{lod}MultiSurface"))
            if surf is not None:
                lod_tags[f"tran:lod{lod}MultiSurface"] += 1
                n_lods += 1
                if lod >= 2:
                    road_vertices += sum(
                        poly_by_id.get(e.get(xlink, "").lstrip("#"), 0)
                        for e in surf.iter()
                        if e.get(xlink)
                    )
        if n_lods == 3:
            roads_all_lods += 1
        net = road.find(t("lod0Network"))
        if net is not None:
            net_curves += sum(1 for _ in net.iter(g("LineString")))
        for ta in road.iter(t("TrafficArea")):
            fn = ta.find(t("function"))
            if fn is not None and fn.text:
                ta_function[fn.text.strip()] += 1
            for lod in (0, 2):
                surf = ta.find(t(f"lod{lod}MultiSurface"))
                if surf is not None:
                    ta_vertices += sum(
                        len(p.text.split()) // 3 for p in surf.iter(g("posList")) if p.text
                    )
        for ata in road.iter(t("AuxiliaryTrafficArea")):
            fn = ata.find(t("function"))
            if fn is not None and fn.text:
                ata_function[fn.text.strip()] += 1

    def labeled(counter, codelist):
        table = cl.get(codelist, {})
        return {table.get(k, k): v for k, v in counter.most_common()}

    return {
        "roads": roads,
        "road_class": labeled(road_class, "TransportationComplex_class"),
        "lod_elements": dict(lod_tags),
        "roads_with_lod1_to_3": roads_all_lods,
        "network_curves": net_curves,
        "trafficArea_function": labeled(ta_function, "TrafficArea_function"),
        "auxTrafficArea_function": labeled(ata_function, "AuxiliaryTrafficArea_function"),
        "road_surface_vertices_lod2plus": road_vertices,
        "trafficArea_vertices": ta_vertices,
    }


def analyze_bldg(path: Path):
    lod = Counter()
    buildings = 0
    with_height = 0
    tree = ET.parse(path)
    for bl in tree.iter(b("Building")):
        buildings += 1
        for i in (0, 1, 2, 3):
            if bl.find(f"{b('lod')}{i}Solid") is not None:
                lod[f"LOD{i}"] += 1
        for i in (0, 1, 2, 3):
            if bl.find(f"{b('lod')}{i}MultiSurface") is not None:
                lod[f"LOD{i}MS"] += 1
        if bl.find(b("measuredHeight")) is not None:
            with_height += 1
    return {"buildings": buildings, "lod_elements": dict(lod), "with_measuredHeight": with_height}


def analyze_dem(path: Path):
    tree = ET.parse(path)
    reliefs = 0
    triangles = 0
    verts = 0
    for rf in tree.iter("{http://www.opengis.net/citygml/relief/2.0}ReliefFeature"):
        reliefs += 1
    for tri in tree.iter(g("Triangle")):
        triangles += 1
    for pos in tree.iter(g("posList")):
        if pos.text:
            verts += len(pos.text.split()) // 3
    return {"relief_features": reliefs, "tin_triangles": triangles, "vertices": verts}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("meshes", nargs="+", help="3rd-mesh codes, e.g. 53394611")
    ap.add_argument("--root", default="vendor/citygml", help="CityGML dataset root (contains udx/)")
    args = ap.parse_args()
    root = Path(args.root)
    cl = load_codelists(root)

    tran_total = Counter()
    for mesh in args.meshes:
        print(f"\n===== {mesh} =====")
        tran_files = sorted((root / "udx" / "tran").glob(f"{mesh}_*.gml"))
        bldg_files = sorted((root / "udx" / "bldg").glob(f"{mesh}_*.gml"))
        dem_files = sorted((root / "udx" / "dem").glob(f"{mesh[:6]}_*.gml"))
        if tran_files:
            for f in tran_files:
                s = analyze_tran(f, cl)
                print(f"[tran] {f.name}")
                for k, v in s.items():
                    print(f"   {k}: {v}")
                tran_total["roads"] += s["roads"]
                for k, v in s["trafficArea_function"].items():
                    tran_total[f"TA {k}"] += v
                for k, v in s["auxTrafficArea_function"].items():
                    tran_total[f"ATA {k}"] += v
        else:
            print("[tran] no file")
        if bldg_files:
            for f in bldg_files:
                s = analyze_bldg(f)
                print(f"[bldg] {f.name}: {s}")
        else:
            print("[bldg] no file")
        if dem_files:
            for f in dem_files:
                print(f"[dem ] {f.name}: {analyze_dem(f)}")

    print("\n===== corridor summary =====")
    for k, v in sorted(tran_total.items()):
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
