import Toybox.Lang;

// App-wide configuration.
module Config {
    const APP_VERSION = "1.0";

    // Tile server URL. Empty string = fetching disabled (bundled tiles only),
    // which is how the store build ships. To enable on-demand fetching, set a
    // public HTTPS URL the phone can reach.
    //   Simulator testing: "http://127.0.0.1:8088"
    const SERVER_URL = "";

    // Max number of fetched tiles kept in Application.Storage (LRU evicted).
    const CACHE_CAP = 30;

    // "Download this area" prefetches a (2*radius+1) square of tiles. radius 1
    // = 3x3 ~ 8 km across (tiles are ~2.7 km). Keep <= CACHE_CAP.
    const DOWNLOAD_RADIUS = 1;
}
