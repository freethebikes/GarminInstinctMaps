#!/usr/bin/env python3
"""
Bulk-generate hosted tiles for a whole state/country from an OSM .pbf extract.

Unlike gen_tiles.py (which builds the small bundled region and keeps every
feature in memory), this streams the extract: each way is simplified and cut
into tile runs as it is read, so memory scales with the OUTPUT (a few hundred
MB for California), not with the raw OSM data.

It writes only static tile files -- tile_<ix>_<iy>.json on the shared world
grid (gen_tiles.GRID_*) -- ready to upload to the static host the watch
fetches from (Config.SERVER_URL). It does not touch the bundled resources.

Every tile is capped at --max-bytes: the watch parses a whole tile into its
96 KB heap and holds up to 3x3 of them, so one lake-country tile at 12 KB is
a crash. Over-cap tiles are degraded in steps (fewer labels -> coarser
simplification -> drop smallest water, then smallest roads) until they fit.

Multiple extracts: every run first writes RAW tiles (before the size cap) to
--raw-dir, merging with tiles already there. A feature that crosses the border
between two extracts appears in both (Geofabrik keeps crossing ways whole) and
simplifies to identical ints, so merging drops exact duplicate lines and a
border tile ends up with both sides. The cap is applied once at the end
(finalize: raw -> --out), so a capped tile is never merged with a raw one.

Usage:
  python3 -m venv tools/.venv && tools/.venv/bin/pip install osmium
  curl -o tools/osm/california.osm.pbf \\
      https://download.geofabrik.de/north-america/us/california-<YYMMDD>.osm.pbf
  tools/.venv/bin/python tools/gen_static.py --fresh \\
      --pbf tools/osm/california.osm.pbf

  # Several regions, one at a time (download, process, delete), then cap:
  tools/.venv/bin/python tools/gen_static.py --fresh --no-finalize --pbf west.osm.pbf
  tools/.venv/bin/python tools/gen_static.py --no-finalize --pbf south.osm.pbf
  tools/.venv/bin/python tools/gen_static.py              # finalize only
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_tiles as gt  # noqa: E402
import osm_pbf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tile_name(ix, iy):
    return f"tile_{ix}_{iy}.json"


def merge_into_raw(tiles, raw_dir):
    """Writes this run's tiles to raw_dir, merging with existing raw tiles.
    Returns the number of tiles that already existed (border tiles)."""
    merged = 0
    for (ix, iy), t in tiles.items():
        path = os.path.join(raw_dir, tile_name(ix, iy))
        if os.path.exists(path):
            merged += 1
            with open(path) as f:
                old = json.load(f)
            seen = {tuple(ln) for ln in old["lines"]}
            lines = old["lines"] + [ln for ln in t["lines"]
                                    if tuple(ln) not in seen]
            seen = {json.dumps(e) for _, e in old["labels"]}
            labels = old["labels"] + [[p, e] for p, e in t["labels"]
                                      if json.dumps(e) not in seen]
            t = {"lines": lines, "labels": labels}
        with open(path, "w") as f:
            f.write(gt.dump(t))
    return merged


def finalize(raw_dir, out_dir, grid, max_labels, max_bytes):
    """Caps every raw tile and writes the servable tile set to out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    for fn in os.listdir(out_dir):
        if fn.startswith("tile_") and fn.endswith(".json"):
            os.remove(os.path.join(out_dir, fn))
    sizes = []
    steps = {}
    for fn in os.listdir(raw_dir):
        if not (fn.startswith("tile_") and fn.endswith(".json")):
            continue
        ix, iy = map(int, fn[5:-5].split("_"))
        with open(os.path.join(raw_dir, fn)) as f:
            t = json.load(f)
        text, step = gt.tile_json(grid, ix, iy, t, max_labels, max_bytes)
        steps[step] = steps.get(step, 0) + 1
        sizes.append(len(text))
        with open(os.path.join(out_dir, fn), "w") as f:
            f.write(text)

    sizes.sort()
    n = len(sizes)
    print(f"Wrote {n} tiles to {out_dir}  ({sum(sizes) / 1e6:.1f} MB)")
    print(f"  size median {sizes[n // 2]} B, p90 {sizes[int(n * .9)]} B, "
          f"max {sizes[-1]} B (cap {max_bytes})")
    print("  degrade steps: " + ", ".join(
        f"{k}:{v}" for k, v in sorted(steps.items())) +
        f"  (0 = untouched, {gt.STEP_DROPPED} = features dropped, "
        f"{gt.STEP_OVER} = still over cap)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pbf", help="OSM .pbf extract to add (omit to only "
                                  "finalize)")
    ap.add_argument("--raw-dir", default=os.path.join(ROOT, "tools", "static_raw"),
                    help="uncapped, mergeable tiles accumulated across runs")
    ap.add_argument("--out", default=os.path.join(ROOT, "tools", "static_out"),
                    help="output folder for the capped tile_<ix>_<iy>.json")
    ap.add_argument("--fresh", action="store_true",
                    help="empty --raw-dir first (start a new tile set)")
    ap.add_argument("--no-finalize", action="store_true",
                    help="only add to --raw-dir (more extracts to come)")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"),
                    help="only keep ways touching this box (default: whole file)")
    grid_cfg = json.load(open(os.path.join(ROOT, "grid.json")))
    ap.add_argument("--tile-deg", type=float, default=grid_cfg["tile_deg"])
    ap.add_argument("--simplify-m", type=float, default=grid_cfg["simplify_m"])
    ap.add_argument("--roads", default=grid_cfg["roads"])
    ap.add_argument("--max-labels", type=int, default=grid_cfg["max_labels"])
    ap.add_argument("--max-bytes", type=int, default=gt.MAX_TILE_BYTES,
                    help="per-tile JSON size cap (see gen_tiles.fit_tile)")
    args = ap.parse_args()

    grid = gt.Grid(args.tile_deg)
    os.makedirs(args.raw_dir, exist_ok=True)
    if args.fresh:
        for fn in os.listdir(args.raw_dir):
            if fn.startswith("tile_") and fn.endswith(".json"):
                os.remove(os.path.join(args.raw_dir, fn))

    if args.pbf:
        tiles = {}   # (ix, iy) -> {"lines": [...], "labels": [(prio, entry)]}
        n_ways = n_small = 0
        t0 = time.time()
        print(f"Reading {args.pbf} ...", flush=True)
        for cls, name, pts in osm_pbf.features_from_pbf(args.pbf, args.roads,
                                                         args.bbox):
            n_ways += 1
            if n_ways % 200000 == 0:
                print(f"  {n_ways} ways, {len(tiles)} tiles, "
                      f"{time.time() - t0:.0f}s", flush=True)
            if not gt.add_feature(tiles, grid, cls, name, pts, args.simplify_m):
                n_small += 1
        print(f"  read {n_ways} ways ({n_small} dropped as tiny/degenerate) "
              f"into {len(tiles)} tiles in {time.time() - t0:.0f}s")
        merged = merge_into_raw(tiles, args.raw_dir)
        print(f"  added to {args.raw_dir} ({merged} merged with existing "
              f"tiles)", flush=True)

    if not args.no_finalize:
        finalize(args.raw_dir, args.out, grid, args.max_labels, args.max_bytes)


if __name__ == "__main__":
    main()
