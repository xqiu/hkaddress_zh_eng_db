#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path

def safe_get(d, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def join_loc_and_name(loc, name):
    loc = (loc or "").strip()
    name = (name or "").strip()
    if loc and name:
        return f"{loc} {name}"
    return name or loc

def first_nonempty(*vals):
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def main(in_dir: Path, out_file: Path):
    # 结构：
    # cities[(CityName, CityEngName)]
    #   -> areas[(AreaName, AreaEngName)]
    #       -> roads[(RoadName, RoadEngName)] = set of buildings (BuildingNo, BuildingName, BuildingEngName)
    cities = {}

    for p in sorted(in_dir.glob("*.geojson")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skip {p.name}: cannot parse JSON ({e})")
            continue

        features = data.get("features", [])
        if not isinstance(features, list):
            continue

        for feat in features:
            props = feat.get("properties", {})
            prem  = safe_get(props, "Address", "PremisesAddress", default={})
            chi   = safe_get(prem, "ChiPremisesAddress", default={})
            eng   = safe_get(prem, "EngPremisesAddress", default={})

            city_cn = safe_get(chi, "Region")
            city_en = safe_get(eng, "Region")
            area_cn = safe_get(chi, "ChiDistrict")
            area_en = safe_get(eng, "EngDistrict")

            # —— 道路名（带 LocationName 前缀），街道优先，其次村名 —— #
            chi_street_name = safe_get(chi, "ChiStreet", "StreetName")
            chi_street_loc  = safe_get(chi, "ChiStreet", "LocationName")
            chi_vill_name   = safe_get(chi, "ChiVillage", "VillageName")
            chi_vill_loc    = safe_get(chi, "ChiVillage", "LocationName")

            if chi_street_name:
                road_cn = join_loc_and_name(chi_street_loc, chi_street_name)
            elif chi_vill_name:
                road_cn = join_loc_and_name(chi_vill_loc, chi_vill_name)
            else:
                road_cn = ""

            eng_street_name = safe_get(eng, "EngStreet", "StreetName")
            eng_street_loc  = safe_get(eng, "EngStreet", "LocationName")
            eng_vill_name   = safe_get(eng, "EngVillage", "VillageName")
            eng_vill_loc    = safe_get(eng, "EngVillage", "LocationName")

            if eng_street_name:
                road_en = join_loc_and_name(eng_street_loc, eng_street_name)
            elif eng_vill_name:
                road_en = join_loc_and_name(eng_vill_loc, eng_vill_name)
            else:
                road_en = ""

            # 无城市/区域/道路等核心信息则跳过
            if not (city_cn or city_en or area_cn or area_en or road_cn or road_en):
                continue

            # —— 楼名与门牌号 —— #
            building_name_cn = safe_get(chi, "BuildingName")
            building_name_en = safe_get(eng, "BuildingName")

            # BuildingNoFrom 可能出现在 Street 或 Village（中/英）
            building_no = first_nonempty(
                safe_get(chi, "ChiStreet", "BuildingNoFrom"),
                safe_get(eng, "EngStreet", "BuildingNoFrom"),
                safe_get(chi, "ChiVillage", "BuildingNoFrom"),
                safe_get(eng, "EngVillage", "BuildingNoFrom"),
            )

            city_key = (city_cn, city_en)
            area_key = (area_cn, area_en)
            road_key = (road_cn, road_en)

            city_entry = cities.setdefault(city_key, {})
            area_entry = city_entry.setdefault(area_key, {})
            bset = area_entry.setdefault(road_key, set())

            # 只有当存在楼名（中文或英文其一）时，才输出 Buildings 项
            if (building_name_cn or building_name_en):
                bset.add((building_no, building_name_cn or "", building_name_en or ""))

    # —— 组装最终结构 —— #
    out = []
    for (city_cn, city_en) in sorted(cities.keys(), key=lambda x: (x[0], x[1])):
        areas = cities[(city_cn, city_en)]
        area_list = []
        for (area_cn, area_en) in sorted(areas.keys(), key=lambda x: (x[0], x[1])):
            roads = areas[(area_cn, area_en)]
            road_list = []
            for (r_cn, r_en) in sorted(roads.keys(), key=lambda r: (r[0], r[1])):
                buildings = roads[(r_cn, r_en)]
                road_obj = {
                    "RoadName": r_cn,
                    "RoadEngName": r_en
                }
                if buildings:
                    # 排序：先按 BuildingNo，再按中英文楼名
                    sorted_bs = sorted(buildings, key=lambda t: (t[0], t[1], t[2]))
                    road_obj["Buildings"] = [
                        {"BuildingNo": bn, "BuildingName": bcn, "BuildingEngName": ben}
                        for (bn, bcn, ben) in sorted_bs
                    ]
                road_list.append(road_obj)

            area_list.append({
                "ZipCode": "999077",  # per your requirement
                "AreaName": area_cn,
                "AreaEngName": area_en,
                "RoadList": road_list
            })

        out.append({
            "CityName": city_cn,
            "CityEngName": city_en,
            "AreaList": area_list
        })

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Done. Wrote {out_file}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input_folder", type=Path, help="Folder containing *.geojson files")
    ap.add_argument("output_json", type=Path, help="Output JSON path")
    args = ap.parse_args()
    main(args.input_folder, args.output_json)
