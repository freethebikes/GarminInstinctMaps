#!/usr/bin/env python3
"""
CrudeMaps tile generator.

Pulls coastline / water / major roads from OpenStreetMap (Overpass API),
simplifies the geometry hard (Douglas-Peucker), slices it into a geographic
tile grid, quantizes each tile's coordinates to integers relative to the tile
origin, and emits:

  resources/tiles.xml              <jsonData> entries, one per tile
  resources/tiles_data/*.json      the per-tile data (loaded on demand on watch)
  source/TileIndex.mc              generated grid metadata + resource lookup

The watch loads only the tiles around the current GPS position, so the 96 KB
RAM budget is spent on the visible area, not the whole region.

No third-party dependencies (urllib + json + math from the stdlib only).

Usage:
  python3 tools/gen_tiles.py --bbox 37.70 -122.52 37.83 -122.36 \
      --tile-deg 0.05 --simplify-m 25

  python3 tools/gen_tiles.py --input region.geojson --tile-deg 0.05   # offline
"""

import argparse
import json
import math
import os
import sys
import urllib.request

# Feature classes (kept tiny; the watch maps these to draw style + label zoom).
CLS_COAST = 0
CLS_WATER = 1
CLS_ROAD = 2

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

SCALE = 100000  # integer units per degree (~1.1 m at the equator for lat)


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def overpass_query(bbox, roads):
    s, w, n, e = bbox
    box = f"{s},{w},{n},{e}"
    return f"""
[out:json][timeout:90];
(
  way["natural"="coastline"]({box});
  way["natural"="water"]({box});
  way["waterway"~"river|canal"]({box});
  way["highway"~"{roads}"]({box});
);
out geom;
""".strip()


def fetch_overpass(bbox, roads, attempts=2):
    import time, hashlib
    q = overpass_query(bbox, roads)
    # Cache the raw response so re-runs (e.g. tuning simplification) don't
    # re-hit Overpass.
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             ".overpass_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, hashlib.md5(q.encode()).hexdigest() + ".json")
    if os.path.exists(cache):
        print("  (using cached Overpass response)", file=sys.stderr)
        with open(cache) as f:
            return json.load(f)
    last = None
    for attempt in range(attempts):
        for url in OVERPASS_URLS:
            try:
                req = urllib.request.Request(
                    url, data=q.encode("utf-8"),
                    headers={
                        "User-Agent": "CrudeMaps-tilegen/0.1 (freethebikes@gmail.com)",
                        "Content-Type": "text/plain",
                    })
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                with open(cache, "w") as f:
                    json.dump(data, f)
                return data
            except Exception as ex:  # noqa: BLE001
                last = ex
                print(f"  overpass {url} failed: {ex}", file=sys.stderr)
        if attempt + 1 < attempts:
            print(f"  retrying all endpoints in 10s ...", file=sys.stderr)
            time.sleep(10)
    raise SystemExit(f"All Overpass endpoints failed: {last}")


def classify(tags):
    if tags.get("natural") == "coastline":
        return CLS_COAST
    if tags.get("natural") == "water" or "waterway" in tags:
        return CLS_WATER
    if "highway" in tags:
        return CLS_ROAD
    return None


def features_from_overpass(data):
    """Yields (cls, name_or_None, [(lat,lon), ...])."""
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        cls = classify(el.get("tags", {}))
        if cls is None:
            continue
        name = el.get("tags", {}).get("name")
        pts = [(g["lat"], g["lon"]) for g in geom]
        yield cls, name, pts


def features_from_geojson(path):
    with open(path) as f:
        gj = json.load(f)
    for feat in gj.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        cls = classify(props)
        if cls is None:
            cls = CLS_ROAD if props.get("highway") else CLS_COAST
        name = props.get("name")
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])
        lines = []
        if gtype == "LineString":
            lines = [coords]
        elif gtype == "MultiLineString" or gtype == "Polygon":
            lines = coords
        elif gtype == "MultiPolygon":
            for poly in coords:
                lines.extend(poly)
        for ln in lines:
            pts = [(c[1], c[0]) for c in ln]  # geojson is lon,lat
            if len(pts) >= 2:
                yield cls, name, pts


# --------------------------------------------------------------------------
# Simplification (Douglas-Peucker, planar in local metres)
# --------------------------------------------------------------------------

def simplify(pts, tol_m):
    if len(pts) < 3:
        return pts
    lat_ref = pts[len(pts) // 2][0]
    mlat = 111320.0
    mlon = 111320.0 * math.cos(math.radians(lat_ref))
    xy = [(p[1] * mlon, p[0] * mlat) for p in pts]

    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = xy[a]
        bx, by = xy[b]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        dmax, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = xy[i]
            if seg2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / seg2
                t = max(0.0, min(1.0, t))
                cx, cy = ax + t * dx, ay + t * dy
                d = math.hypot(px - cx, py - cy)
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol_m and idx != -1:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [pts[i] for i in range(len(pts)) if keep[i]]


# --------------------------------------------------------------------------
# Tiling + quantization
# --------------------------------------------------------------------------

class Grid:
    def __init__(self, min_lat, min_lon, tile_deg):
        self.tile_deg = tile_deg
        # Anchor the grid below/left of the actual data extent so every tile
        # index is >= 0 (lets the watch use a cheap truncating tileX/tileY).
        self.lat0 = math.floor(min_lat / tile_deg) * tile_deg
        self.lon0 = math.floor(min_lon / tile_deg) * tile_deg

    @classmethod
    def from_origin(cls, lat0, lon0, tile_deg):
        g = cls.__new__(cls)
        g.tile_deg = tile_deg
        g.lat0 = lat0
        g.lon0 = lon0
        return g

    def ix(self, lon):
        return int(math.floor((lon - self.lon0) / self.tile_deg))

    def iy(self, lat):
        return int(math.floor((lat - self.lat0) / self.tile_deg))

    def origin(self, ix, iy):
        return (self.lat0 + iy * self.tile_deg, self.lon0 + ix * self.tile_deg)


def split_by_tile(pts, grid):
    """Splits a polyline into per-tile runs, duplicating the boundary point so
    lines stay visually continuous across tile edges."""
    runs = []  # (ix, iy, [pts])
    cur = grid.ix(pts[0][1]), grid.iy(pts[0][0])
    run = [pts[0]]
    for k in range(1, len(pts)):
        t = grid.ix(pts[k][1]), grid.iy(pts[k][0])
        if t == cur:
            run.append(pts[k])
        else:
            run.append(pts[k])               # include crossing point in this tile
            runs.append((cur[0], cur[1], run))
            run = [pts[k - 1], pts[k]]        # overlap into the next tile
            cur = t
    runs.append((cur[0], cur[1], run))
    return runs


def quantize(run, origin):
    lat0, lon0 = origin
    out = []
    for lat, lon in run:
        out.append(int(round((lon - lon0) * SCALE)))  # x
        out.append(int(round((lat - lat0) * SCALE)))  # y
    return out


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def polyline_len_m(pts):
    lat_ref = pts[len(pts) // 2][0]
    mlat = 111320.0
    mlon = 111320.0 * math.cos(math.radians(lat_ref))
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        total += math.hypot((b[1] - a[1]) * mlon, (b[0] - a[0]) * mlat)
    return total


def build_tiles(features, grid, tol_m, max_labels):
    # labels are collected with a priority so we can keep only the most
    # prominent few per tile (the screen can't show more anyway).
    tiles = {}  # (ix,iy) -> {"lines": [...], "labels": [(prio, entry), ...]}

    def tile(ix, iy):
        return tiles.setdefault((ix, iy), {"lines": [], "labels": []})

    for cls, name, pts in features:
        simp = simplify(pts, tol_m)
        if len(simp) < 2:
            continue
        for ix, iy, run in split_by_tile(simp, grid):
            if len(run) < 2:
                continue
            origin = grid.origin(ix, iy)
            tile(ix, iy)["lines"].append([cls] + quantize(run, origin))
        if name:
            mid = simp[len(simp) // 2]
            ix, iy = grid.ix(mid[1]), grid.iy(mid[0])
            x, y = quantize([mid], grid.origin(ix, iy))
            prio = polyline_len_m(simp)
            tile(ix, iy)["labels"].append((prio, [cls, x, y, name]))

    # keep the top-N labels per tile by prominence, then drop the priority.
    for t in tiles.values():
        t["labels"].sort(key=lambda pe: pe[0], reverse=True)
        t["labels"] = [entry for _, entry in t["labels"][:max_labels]]
    return tiles


def build_overview(features, grid, base_tol_m, region_w_m, max_labels,
                   budget=1400):
    """A single, heavily-simplified layer covering the whole region, shown when
    zoomed out. It must stay small in RAM (it's always resident), so the
    simplification tolerance scales with how wide the region is (~1 screen pixel)
    and is raised further until the point count fits `budget`."""
    origin = (grid.lat0, grid.lon0)
    # ~1 px on a 176 px screen, with headroom; never finer than the detail tol.
    tol = max(base_tol_m, region_w_m / 176.0 * 1.3)
    min_len = tol * 3.0

    lines = []
    labels = []
    for _attempt in range(7):
        lines = []
        labels = []
        for cls, name, pts in features:
            if polyline_len_m(pts) < min_len:    # drop short/minor features
                continue
            simp = simplify(pts, tol)
            if len(simp) < 2:
                continue
            lines.append([cls] + quantize(simp, origin))
            if name:
                mid = simp[len(simp) // 2]
                x, y = quantize([mid], origin)
                labels.append((polyline_len_m(simp), [cls, x, y, name]))
        total = sum((len(l) - 1) // 2 for l in lines)
        if total <= budget:
            break
        tol *= 1.6        # too heavy: coarsen and drop more short features
        min_len *= 1.6

    labels.sort(key=lambda pe: pe[0], reverse=True)
    labels = [e for _, e in labels[:max_labels]]
    return {
        "lat0": round(grid.lat0, 6),
        "lon0": round(grid.lon0, 6),
        "sc": SCALE,
        "lines": lines,
        "labels": labels,
    }


def write_outputs(tiles, grid, overview, project_root, roads, simplify_m):
    data_dir = os.path.join(project_root, "resources", "tiles_data")
    os.makedirs(data_dir, exist_ok=True)

    # clear stale tiles
    for fn in os.listdir(data_dir):
        if fn.startswith("tile_") and fn.endswith(".json"):
            os.remove(os.path.join(data_dir, fn))

    entries = []
    syms = []
    populated = sorted(k for k, v in tiles.items() if v["lines"] or v["labels"])
    for ix, iy in populated:
        t = tiles[(ix, iy)]
        lat0, lon0 = grid.origin(ix, iy)
        obj = {
            "lat0": round(lat0, 6),
            "lon0": round(lon0, 6),
            "sc": SCALE,
            "lines": t["lines"],
            "labels": t["labels"],
        }
        fname = f"tile_{ix}_{iy}.json"
        with open(os.path.join(data_dir, fname), "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        rid = f"Tile_{ix}_{iy}"
        entries.append(f'    <jsonData id="{rid}" filename="tiles_data/{fname}"/>')
        syms.append(f'        "{ix}_{iy}" => Rez.JsonData.{rid},')

    # overview layer (single resource, always small)
    with open(os.path.join(data_dir, "overview.json"), "w") as f:
        json.dump(overview, f, separators=(",", ":"))
    entries.append('    <jsonData id="Overview" filename="tiles_data/overview.json"/>')

    with open(os.path.join(project_root, "resources", "tiles.xml"), "w") as f:
        f.write('<resources>\n' + "\n".join(entries) + "\n</resources>\n")

    # Shared grid definition so the tile server produces indices the app agrees
    # with (must match the LAT0/LON0/TILE_DEG constants in TileIndex.mc).
    with open(os.path.join(project_root, "grid.json"), "w") as f:
        json.dump({"lat0": round(grid.lat0, 6), "lon0": round(grid.lon0, 6),
                   "tile_deg": grid.tile_deg, "scale": SCALE,
                   "roads": roads, "simplify_m": simplify_m,
                   "max_labels": 12}, f, indent=2)

    # centre of the populated area -> default HOME on the watch
    cxs = [ix for ix, iy in populated]
    cys = [iy for ix, iy in populated]
    clat = grid.lat0 + (min(cys) + max(cys) + 1) / 2.0 * grid.tile_deg
    clon = grid.lon0 + (min(cxs) + max(cxs) + 1) / 2.0 * grid.tile_deg

    idx = f"""// GENERATED by tools/gen_tiles.py -- do not edit by hand.
import Toybox.Application;
import Toybox.Lang;

module TileIndex {{
    const LAT0 = {grid.lat0:.6f};       // SW origin of the tile grid
    const LON0 = {grid.lon0:.6f};
    const TILE_DEG = {grid.tile_deg};
    const HOME_LAT = {clat:.6f};         // centre of the generated data
    const HOME_LON = {clon:.6f};

    // "ix_iy" -> JSON resource id for every populated tile.
    var mSyms = {{
{os.linesep.join(syms) if syms else ""}
    }};

    function floorDiv(v as Float) as Number {{
        var n = v.toNumber();              // truncates toward zero
        if (v < 0.0 && v.toFloat() != n) {{
            n -= 1;
        }}
        return n;
    }}

    function tileX(lon as Float) as Number {{
        return floorDiv((lon - LON0) / TILE_DEG);
    }}

    function tileY(lat as Float) as Number {{
        return floorDiv((lat - LAT0) / TILE_DEG);
    }}

    // Loads and parses a tile, or returns null if that tile has no data.
    function load(ix as Number, iy as Number) {{
        var sym = mSyms[ix + "_" + iy];
        if (sym == null) {{
            return null;
        }}
        return Application.loadResource(sym);
    }}

    // The whole-region overview layer (shown when zoomed out).
    function loadOverview() {{
        return Application.loadResource(Rez.JsonData.Overview);
    }}
}}
"""
    with open(os.path.join(project_root, "source", "TileIndex.mc"), "w") as f:
        f.write(idx)

    total_lines = sum(len(t["lines"]) for t in tiles.values())
    total_pts = sum(sum((len(l) - 1) // 2 for l in t["lines"]) for t in tiles.values())
    print(f"  tiles populated : {len(populated)}")
    print(f"  polylines       : {total_lines}")
    print(f"  points (total)  : {total_pts}")
    print(f"  home (centre)   : {clat:.5f}, {clon:.5f}")


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate CrudeMaps tiles from OSM.")
    ap.add_argument("--bbox", nargs=4, type=float,
                    metavar=("S", "W", "N", "E"),
                    help="south west north east (lat lon lat lon)")
    ap.add_argument("--input", help="local GeoJSON instead of Overpass")
    ap.add_argument("--tile-deg", type=float, default=0.05)
    ap.add_argument("--simplify-m", type=float, default=35.0)
    ap.add_argument("--roads", default="motorway|trunk|primary",
                    help="Overpass highway regex (major roads only by default)")
    ap.add_argument("--max-labels", type=int, default=40,
                    help="max labels kept per tile (by prominence)")
    ap.add_argument("--out", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), help="project root")
    args = ap.parse_args()

    if args.input:
        print(f"Reading {args.input} ...")
        feats = list(features_from_geojson(args.input))
        if not args.bbox:
            lats = [p[0] for _, _, pts in feats for p in pts]
            lons = [p[1] for _, _, pts in feats for p in pts]
            args.bbox = [min(lats), min(lons), max(lats), max(lons)]
    else:
        if not args.bbox:
            ap.error("--bbox is required unless --input is given")
        print(f"Querying Overpass for bbox {args.bbox} ...")
        feats = list(features_from_overpass(fetch_overpass(args.bbox, args.roads)))

    print(f"  features fetched: {len(feats)}")
    if not feats:
        raise SystemExit("No features found for this area/filters.")
    min_lat = min(p[0] for _, _, pts in feats for p in pts)
    min_lon = min(p[1] for _, _, pts in feats for p in pts)
    grid = Grid(min_lat, min_lon, args.tile_deg)
    tiles = build_tiles(feats, grid, args.simplify_m, args.max_labels)
    max_lat = max(p[0] for _, _, pts in feats for p in pts)
    max_lon = max(p[1] for _, _, pts in feats for p in pts)
    mid_lat = (min_lat + max_lat) / 2.0
    region_w_m = (max_lon - min_lon) * 111320.0 * math.cos(math.radians(mid_lat))
    overview = build_overview(feats, grid, max(args.simplify_m * 5.0, 150.0),
                              region_w_m, 20)
    ov_pts = sum((len(l) - 1) // 2 for l in overview["lines"])
    print(f"  overview points : {ov_pts} ({len(overview['lines'])} lines)")
    write_outputs(tiles, grid, overview, args.out, args.roads, args.simplify_m)
    print("Done.")


if __name__ == "__main__":
    main()
