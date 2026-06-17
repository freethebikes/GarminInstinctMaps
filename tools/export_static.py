#!/usr/bin/env python3
"""
Export tiles to the static hosting folder (site/tiles/) served by GitHub Pages.

The watch fetches missing tiles from
  https://<user>.github.io/<repo>/site/tiles/tile_<ix>_<iy>.json

This copies the currently generated tiles (resources/tiles_data/) into
site/tiles/. To offer MORE coverage than the bundled app, generate extra
regions first (they accumulate in resources/tiles_data on each run unless you
clear it) and then export — or generate straight into a staging folder and copy.

Usage:
  python3 tools/gen_tiles.py --bbox ...      # (repeat per region you want hosted)
  python3 tools/export_static.py
  git add site && git commit -m "tiles" && git push
"""

import glob
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "resources", "tiles_data")
DST = os.path.join(ROOT, "site", "tiles")


def main():
    os.makedirs(DST, exist_ok=True)
    files = glob.glob(os.path.join(SRC, "*.json"))
    n = 0
    for f in files:
        shutil.copy2(f, os.path.join(DST, os.path.basename(f)))
        n += 1
    # .nojekyll at the repo root tells Pages to serve files verbatim.
    open(os.path.join(ROOT, ".nojekyll"), "a").close()
    print(f"Exported {n} files to site/tiles/  (incl. overview.json)")
    print("Now: git add site .nojekyll && git commit && git push")


if __name__ == "__main__":
    main()
