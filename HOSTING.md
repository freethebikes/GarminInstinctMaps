# Hosting tiles for on-demand region download (free)

## The idea: static files, not a server

`tools/tile_server.py` generates tiles on demand from Overpass. That's great for
development, but a bad production backend (Overpass rate-limits/bans, and a live
server needs uptime + HTTPS + money).

Because **you choose which regions to offer**, you can pre-generate all their
tiles once and serve them as **plain static `.json` files** from a free static
host. The watch just fetches a URL per tile — no server logic at runtime.

Benefits: free, HTTPS included (Garmin requires SSL), no Overpass at runtime, no
uptime to babysit, CDN-fast, scales to any number of users.

## Recommended host: GitHub Pages

Free, automatic HTTPS at `https://<user>.github.io/<repo>/`, trivial to deploy.
(Cloudflare Pages is the upgrade if bandwidth ever grows — unlimited bandwidth,
same static model.)

## Pipeline

1. **Pick the regions** you want to offer (the catalog) and generate tiles for
   each into one output folder. The generator already writes per-tile JSON to
   `resources/tiles_data/`; for hosting we copy those into a `docs/tiles/`
   folder (one folder holding every region's tiles — they all share the grid).

   ```bash
   # for each region bbox you want to offer:
   python3 tools/gen_tiles.py --bbox <S> <W> <N> <E> --tile-deg 0.05 ...
   mkdir -p site/tiles && cp resources/tiles_data/*.json site/tiles/
   # (repeat for each region; tiles accumulate in site/tiles/)
   ```

   A small `tools/export_static.py` can automate "generate every catalog region
   into `site/tiles/`" in one command (see TODO below).

2. **Push `site/` to a GitHub repo** and enable Pages (Settings → Pages →
   deploy from `/site` or `/docs`). You get:
   `https://<user>.github.io/crudemaps-tiles/tiles/tile_<ix>_<iy>.json`

3. **Point the app at it.** In `source/Config.mc`:
   ```
   const SERVER_URL = "https://<user>.github.io/crudemaps-tiles";
   ```

## One small code change: static URL form

The current fetch builds a dynamic query (`/tile?ix=&iy=`). For static files it
should request the file path instead. In `TileFetcher` (two call sites:
`request` and `pump`):

```
// dynamic (current):
Config.SERVER_URL + "/tile", { "ix" => ix, "iy" => iy }, ...
// static:
Config.SERVER_URL + "/tiles/tile_" + ix + "_" + iy + ".json", {}, ...
```

The response JSON is identical, so nothing else changes. A missing tile (ocean /
no data) returns 404, which the fetcher already handles (only 200 is cached; the
retry throttle prevents re-spamming).

## Notes / limits

- **HTTPS is mandatory** for Garmin's phone-relayed requests in production.
  GitHub Pages provides a valid cert automatically — self-hosted http:// will be
  rejected on a real watch (it only "works" in the simulator).
- **Storage quota** on the watch still bounds how much a user can download at
  once; keep catalog regions reasonably sized and rely on LRU eviction
  (`Config.CACHE_CAP`).
- **Re-baking** when OSM changes is just re-running the generator + re-pushing
  `site/` — no users to migrate, the CDN picks it up.

## If you ever truly need on-demand arbitrary regions

Then you need a live backend (Cloudflare Workers free tier, or a small VPS) that
generates tiles from a real OSM source — not live Overpass. That's a bigger
project; the static approach above covers a curated region catalog for free and
is the right first step.

## TODO to implement this

- [ ] `tools/export_static.py` — generate every `RegionCatalog` region into
      `site/tiles/` in one command.
- [ ] Add a `STATIC` switch (or just change the URL form) in `TileFetcher`.
- [ ] Create the Pages repo, set `SERVER_URL`, repackage.
