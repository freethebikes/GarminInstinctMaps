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

Usage:
  python3 -m venv tools/.venv && tools/.venv/bin/pip install osmium
  curl -o tools/osm/california.osm.pbf \\
      https://download.geofabrik.de/north-america/us/california-<YYMMDD>.osm.pbf
  tools/.venv/bin/python tools/gen_static.py --pbf tools/osm/california.osm.pbf \\
      --out tools/static_out
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

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pbf", required=True, help="OSM .pbf extract")
    ap.add_argument("--out", default=os.path.join(ROOT, "tools", "static_out"),
                    help="output folder for tile_<ix>_<iy>.json")
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
    tiles = {}   # (ix, iy) -> {"lines": [...], "labels": [(prio, entry)]}
    n_ways = n_small = 0
    t0 = time.time()

    print(f"Reading {args.pbf} ...")
    for cls, name, pts in osm_pbf.features_from_pbf(args.pbf, args.roads,
                                                     args.bbox):
        n_ways += 1
        if n_ways % 200000 == 0:
            print(f"  {n_ways} ways, {len(tiles)} tiles, "
                  f"{time.time() - t0:.0f}s")
        if not gt.add_feature(tiles, grid, cls, name, pts, args.simplify_m):
            n_small += 1

    print(f"  read {n_ways} ways ({n_small} dropped as tiny/degenerate) into "
          f"{len(tiles)} tiles in {time.time() - t0:.0f}s")

    os.makedirs(args.out, exist_ok=True)
    sizes = []
    steps = {}
    for (ix, iy), t in tiles.items():
        text, step = gt.tile_json(grid, ix, iy, t, args.max_labels,
                                  args.max_bytes)
        steps[step] = steps.get(step, 0) + 1
        sizes.append(len(text))
        with open(os.path.join(args.out, f"tile_{ix}_{iy}.json"), "w") as f:
            f.write(text)

    sizes.sort()
    n = len(sizes)
    print(f"Wrote {n} tiles to {args.out}  ({sum(sizes) / 1e6:.1f} MB)")
    print(f"  size median {sizes[n // 2]} B, p90 {sizes[int(n * .9)]} B, "
          f"max {sizes[-1]} B (cap {args.max_bytes})")
    print("  degrade steps: " + ", ".join(
        f"{k}:{v}" for k, v in sorted(steps.items())) +
        f"  (0 = untouched, {gt.STEP_DROPPED} = features dropped, "
        f"{gt.STEP_OVER} = still over cap)")


if __name__ == "__main__":
    main()
