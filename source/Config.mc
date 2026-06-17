import Toybox.Lang;

// App-wide configuration.
module Config {
    const APP_VERSION = "1.0";

    // Tile source URL. Empty string = fetching disabled (bundled tiles only).
    // For static hosting (GitHub Pages), this is the folder holding the tile
    // files; for the dynamic dev server it's the server root.
    //   Static (Pages): "https://<user>.github.io/<repo>/site/tiles"
    //   Dynamic dev server: "http://127.0.0.1:8088"  (set STATIC_TILES = false)
    const SERVER_URL = "https://freethebikes.github.io/GarminInstinctMaps/site/tiles";

    // true  -> request static files:  <SERVER_URL>/tile_<ix>_<iy>.json
    // false -> dynamic dev server:    <SERVER_URL>/tile?ix=&iy=
    const STATIC_TILES = true;

    // Max number of fetched tiles kept in Application.Storage (LRU evicted).
    const CACHE_CAP = 30;

    // "Download this area" prefetches a (2*radius+1) square of tiles. radius 1
    // = 3x3 ~ 8 km across (tiles are ~2.7 km). Keep <= CACHE_CAP.
    const DOWNLOAD_RADIUS = 1;
}
