# CrudeMaps — vector maps for the Garmin Instinct 2

A Connect IQ watch app that renders crude vector maps (coastlines / outlines) by
drawing polylines relative to the current GPS position. The Instinct 2 has no
native map support, so this fills that gap with a lightweight vector renderer.

## Status

**Step 1 — renderer proof: done.** Vector polylines projected to the 176×176
screen, button zoom/pan-tilt with hold-acceleration, zoom-gated labels.

**Step 2 — OSM tile pipeline: done.** `tools/gen_tiles.py` turns OpenStreetMap
data into compact integer tiles bundled as `<jsonData>` resources. The watch
loads only the tiles overlapping the current view and evicts the rest, and
renders straight from the integer arrays (no `[lat,lon]` expansion) to stay
within 96 KB. Tiles auto-load as you pan / as GPS moves.

**Step 3 — fetch-and-cache: done.** Tiles outside the bundled set are fetched
from a tile server over the phone (`Communications.makeWebRequest`) and cached
on-device in `Application.Storage` with LRU eviction. Bundled → Storage cache →
network, in that order; fetches are gated on phone connectivity and throttled.

### Running the tile server

```bash
python3 tools/tile_server.py --port 8088
```

`GET /tile?ix=&iy=` returns a tile, generating it from OSM on a miss (and
disk-caching under `tools/server_cache/`). It uses `grid.json` so its tile
indices match the app's. Point the app at it via `SERVER_URL` in
`source/Config.mc` (set `""` to disable fetching). For the simulator,
`http://127.0.0.1:8088` works; a real watch needs a public URL.

### Testing the fetch in the simulator

1. Start the server (above).
2. `./build.sh run`.
3. In the sim, ensure the phone connection is enabled, then **Simulation → GPS**
   a position *outside* the bundled SF area (or pan there). Missing tiles fetch
   in and are cached; revisit them offline and they load from Storage.

### Generating tiles for an area

```bash
python3 tools/gen_tiles.py --bbox <south> <west> <north> <east> \
    --tile-deg 0.025 --simplify-m 50 --roads "motorway|trunk" --max-labels 12
```

Writes `resources/tiles.xml`, `resources/tiles_data/*.json`, and the generated
`source/TileIndex.mc` (grid metadata + the default HOME centre). Then rebuild.

**Memory matters.** Each tile is loaded whole, so keep tiles small: dense urban
areas need smaller `--tile-deg`, harder `--simplify-m`, and major roads only —
otherwise a single tile can exceed the 96 KB RAM budget. Coastline/outline
regions are far lighter. Watch for the SDK's "jsonData record is large (>8kb)"
warning as a red flag.

## Hardware constraints (Instinct 2)

- 176×176, **1 bit per pixel** — black/white only, no grayscale.
- **watchApp memory budget: 98304 bytes (96 KB)** total (code + data + buffers).
- 5 buttons, **no touch**.
- No standalone internet: network only via the phone over Bluetooth, and apps
  cannot read arbitrary side-loaded files — data must come from bundled
  resources, `Application.Storage`, or `makeWebRequest`.

## Controls

The Instinct 2's buttons are **CTRL / MENU / ABC** (left, top-to-bottom) and
**GPS / SET** (right).

| Button       | Action                                                        |
|--------------|---------------------------------------------------------------|
| MENU / ABC   | Step up / down in the current mode; **hold to accelerate**    |
| GPS (tap)    | Cycle mode: ZOOM → TILT (N/S) → PAN (E/W)                      |
| GPS (hold)   | Open the menu (**Regions**, Download area, Clear cache, About) |
| MENU (hold)  | Also opens the menu (Garmin convention)                       |
| CTRL         | Flip directly between TILT and PAN (easy axis switch)         |
| SET          | Recenter if panned, otherwise exit                            |

**Regions** (menu → Regions) lists named places (`source/RegionCatalog.mc`) and
jumps the map there — works offline for bundled data. When a tile server is
configured, jumping to a region also prefetches that area into Storage.

**Download area** prefetches a `Config.DOWNLOAD_RADIUS` square of tiles around
the current centre into `Application.Storage` so they're available offline; a
`DL n/total` overlay shows progress.

"Pan/tilt" is used in the camera sense: **tilt = vertical (N/S)**, **pan =
horizontal (E/W)**.

## Build & run

Requires a JRE (Java 17+):

```bash
sudo apt-get install -y openjdk-21-jre-headless
```

Then:

```bash
./build.sh        # compile to bin/CrudeMaps.prg
./build.sh run    # compile, start the simulator, side-load the app
```

In the simulator, feed a GPS position via **Simulation → GPS** to see the
position marker move and the map recenter.

## Layout

```
manifest.xml                     app id, instinct2 target, Positioning permission
monkey.jungle                    build config
source/MapApp.mc                 entry point
source/MapView.mc                projection + rendering + zoom/pan state
source/MapInputDelegate.mc       button handling
source/MapData.mc                synthetic test geometry (replaced in step 2)
resources/                       strings, launcher icon
```
