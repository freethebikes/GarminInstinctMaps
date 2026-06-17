# Publishing CrudeMaps to the Connect IQ Store

## What's done (in this repo)

- **Bundled-only build** — fetching is disabled (`Config.SERVER_URL = ""`); the
  app ships with the tiles baked into the package and works fully offline.
- **About / attribution screen** — menu → About shows "© OpenStreetMap
  contributors" (required by the OSM ODbL licence).
- **Multi-device** — manifest targets the non-AMOLED Instinct family
  (instinct2, 2s, 2x, 3 Solar 45mm, Crossover, E 40mm, E 45mm), with a dynamic
  sub-circle and per-device launcher icons. `minApiLevel` 3.2.0 to reach older
  firmware too.
- **Store package** — `./build.sh package` → `bin/CrudeMaps.iq` (this is the
  file you upload), signed with your `~/.Garmin/developer_key.der`.

## Decisions / content YOU need to make first

1. **Which region to bundle.** Right now the bundled tiles are **San Francisco**
   (a test extract). Before publishing, regenerate for the area(s) you actually
   want to ship and be explicit about coverage in the store description:
   ```bash
   python3 tools/gen_tiles.py --bbox <S> <W> <N> <E> \
       --tile-deg 0.025 --simplify-m 50 --roads "motorway|trunk" --max-labels 12
   python3 tools/gen_icons.py        # only needed once
   ./build.sh package
   ```
   Bigger regions = bigger package; keep an eye on per-tile size (>8 KB warning).

2. **Privacy policy URL** — required by Garmin because the app uses location
   (and has the Communications permission). Host a short page and have the URL
   ready for the listing.

## Checklist before submitting

- [ ] **Test on your real Instinct 2** (see below) — buttons, menu, About,
      pan/zoom/tilt, the download ring is hidden (fetch disabled), memory is OK.
- [ ] Pick and regenerate the **bundled region**.
- [ ] Capture **screenshots** (simulator: File → Save Screenshot, or from the
      watch) — the store wants a few.
- [ ] Prepare a **store/marketing icon** (uploaded in the web portal, separate
      from the in-app launcher icon).
- [ ] Write the **description** (mention: vector coastline/outline maps, the
      covered region, offline, "© OpenStreetMap contributors").
- [ ] Have the **privacy policy URL** ready.
- [ ] `./build.sh package` to produce a fresh `bin/CrudeMaps.iq`.
- [ ] Upload at the Connect IQ developer portal, set pricing (free), submit for
      review.

## Sideloading to a real Instinct 2 (for testing)

1. `./build.sh` to produce `bin/CrudeMaps.prg`.
2. Connect the watch by USB; it mounts as a drive.
3. Copy `bin/CrudeMaps.prg` into the watch's `GARMIN/APPS/` folder.
4. Eject, and find CrudeMaps in the watch's activity/app list.

## Re-enabling fetch later (optional)

Set `Config.SERVER_URL` to a public **HTTPS** URL, host `tools/tile_server.py`
behind it (backed by a real OSM source, not live Overpass), repackage. The
Download-area menu and progress ring re-appear automatically.
