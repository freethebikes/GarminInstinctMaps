#!/usr/bin/env python3
"""
CrudeMaps tile server.

Serves compact tiles to the watch (relayed through the phone). On a cache miss
it generates the tile from OpenStreetMap with the same pipeline the bundled
tiles use, so fetched tiles look identical to bundled ones.

    GET /tile?ix=<int>&iy=<int>   -> tile JSON {lat0,lon0,sc,lines,labels}
    GET /health                   -> "ok"

Tile indices use the shared grid in grid.json (written by gen_tiles.py), so the
watch and server always agree on which tile is which.

    python3 tools/tile_server.py --port 8080

For real field use this needs to run on a public URL the phone can reach; for
simulator testing, http://127.0.0.1:<port> works because the simulator uses the
host machine's network.
"""

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_tiles as gt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "tools", "server_cache")
MARGIN_DEG = 0.003  # pull features slightly beyond the tile so edges join up

GRID = None
CFG = None


def load_grid():
    with open(os.path.join(ROOT, "grid.json")) as f:
        cfg = json.load(f)
    grid = gt.Grid.from_origin(cfg["lat0"], cfg["lon0"], cfg["tile_deg"])
    return grid, cfg


def make_tile(ix, iy):
    """Return the tile dict for (ix, iy), generating + caching on miss."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"tile_{ix}_{iy}.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)

    lat0, lon0 = GRID.origin(ix, iy)
    td = GRID.tile_deg
    bbox = (lat0 - MARGIN_DEG, lon0 - MARGIN_DEG,
            lat0 + td + MARGIN_DEG, lon0 + td + MARGIN_DEG)
    feats = list(gt.features_from_overpass(
        gt.fetch_overpass(bbox, CFG["roads"])))
    tiles = gt.build_tiles(feats, GRID, CFG["simplify_m"], CFG["max_labels"])
    t = tiles.get((ix, iy), {"lines": [], "labels": []})
    obj = {
        "lat0": round(lat0, 6),
        "lon0": round(lon0, 6),
        "sc": CFG["scale"],
        "lines": t["lines"],
        "labels": t["labels"],
    }
    with open(cache, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    return obj


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._send(200, "ok", "text/plain")
        if u.path != "/tile":
            return self._send(404, '{"error":"not found"}')
        q = parse_qs(u.query)
        try:
            ix = int(q["ix"][0])
            iy = int(q["iy"][0])
        except (KeyError, ValueError):
            return self._send(400, '{"error":"need integer ix & iy"}')
        try:
            obj = make_tile(ix, iy)
        except Exception as ex:  # noqa: BLE001
            print(f"  tile {ix},{iy} failed: {ex}", file=sys.stderr)
            return self._send(502, '{"error":"upstream failed"}')
        pts = sum((len(l) - 1) // 2 for l in obj["lines"])
        print(f"  served tile {ix},{iy}: {len(obj['lines'])} lines, {pts} pts")
        return self._send(200, json.dumps(obj, separators=(",", ":")))

    def log_message(self, *_args):
        pass  # quiet default logging; we print our own


def main():
    global GRID, CFG
    ap = argparse.ArgumentParser(description="CrudeMaps tile server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    GRID, CFG = load_grid()
    print(f"Grid origin {GRID.lat0},{GRID.lon0} tile {GRID.tile_deg} "
          f"roads='{CFG['roads']}'")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving tiles on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
