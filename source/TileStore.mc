import Toybox.Lang;
import Toybox.Math;
import Toybox.WatchUi;

// Loads the map tiles that overlap the current view and evicts the rest, so RAM
// is spent only on what's visible. Tiles are kept in their raw decoded form
// (Dictionary with flat integer arrays) and projected directly at draw time —
// we never build a parallel [lat,lon] structure, which would cost far more RAM.
class TileStore {

    var mCache;      // "ix_iy" => tile Dictionary (loaded tiles only)
    var mOverview;   // cached whole-region overview layer
    var mFetcher;    // fetch + Storage cache for non-bundled tiles

    function initialize() {
        mCache = {};
        mOverview = null;
        mFetcher = new TileFetcher(method(:onTileFetched));
    }

    // Called by the fetcher when a tile arrives from the network.
    function onTileFetched(key as String, tile as Dictionary) as Void {
        mCache.put(key, tile);
        WatchUi.requestUpdate();
    }

    // Resolve a tile: bundled first, then the fetch/Storage cache (which kicks
    // off a network fetch on a miss and returns null until it arrives).
    function loadTile(ix as Number, iy as Number) as Dictionary? {
        var bundled = TileIndex.load(ix, iy);
        if (bundled != null) {
            return bundled as Dictionary;
        }
        return mFetcher.get(ix, iy);
    }

    // The single overview layer, loaded once and kept (it is small by design).
    function overviewTiles() as Array {
        if (mOverview == null) {
            mOverview = TileIndex.loadOverview();
        }
        return (mOverview == null) ? [] : [mOverview];
    }

    // Returns the Array of in-view tile Dictionaries, loading new ones and
    // dropping any that have scrolled out of view.
    function tilesFor(centerLat as Float, centerLon as Float, spanM as Float,
                      w as Number, h as Number) as Array {
        var mPerDegLat = 111320.0;
        var mPerDegLon = 111320.0 * Math.cos(centerLat * Math.PI / 180.0);
        var dLat = (spanM * 0.5) / mPerDegLat;
        var dLon = (spanM * 0.5 * w.toFloat() / h) / mPerDegLon;

        var ix0 = TileIndex.tileX(centerLon - dLon);
        var ix1 = TileIndex.tileX(centerLon + dLon);
        var iy0 = TileIndex.tileY(centerLat - dLat);
        var iy1 = TileIndex.tileY(centerLat + dLat);

        // Safety cap: never load more than a 3x3 block around the centre tile,
        // so we can't run out of memory however far the view is stretched.
        var cix = TileIndex.tileX(centerLon);
        var ciy = TileIndex.tileY(centerLat);
        if (ix0 < cix - 1) { ix0 = cix - 1; }
        if (ix1 > cix + 1) { ix1 = cix + 1; }
        if (iy0 < ciy - 1) { iy0 = ciy - 1; }
        if (iy1 > ciy + 1) { iy1 = ciy + 1; }

        var result = [];
        var keep = {};
        for (var ix = ix0; ix <= ix1; ix++) {
            for (var iy = iy0; iy <= iy1; iy++) {
                var key = ix + "_" + iy;
                keep.put(key, true);
                var t = mCache.get(key);
                if (t == null) {
                    t = loadTile(ix, iy);   // bundled, cached, or kicks off fetch
                    if (t != null) {
                        mCache.put(key, t);
                    }
                }
                if (t != null) {
                    result.add(t);
                }
            }
        }
        evictExcept(keep);
        return result;
    }

    // Whether on-demand fetching is enabled (false in the bundled-only build).
    function fetchEnabled() as Boolean {
        return mFetcher.mEnabled;
    }

    // "Download this area": prefetch tiles around the given centre into Storage.
    function prefetch(centerLat as Float, centerLon as Float,
                      radius as Number, progressCb as Method) as Void {
        var cix = TileIndex.tileX(centerLon);
        var ciy = TileIndex.tileY(centerLat);
        mFetcher.prefetchArea(cix, ciy, radius, progressCb);
    }

    // Wipe all fetched/cached tiles from Storage and memory.
    function clearCache() as Void {
        mFetcher.clearCache();
        mCache = {};
    }

    // Free the detail tiles (called when switching to the overview layer).
    function clearDetail() as Void {
        if (mCache.size() > 0) {
            mCache = {};
        }
    }

    // Free the overview layer (called when switching to detail tiles).
    function clearOverview() as Void {
        mOverview = null;
    }

    // Drop cached tiles whose key is not in `keep` to release their memory.
    function evictExcept(keep as Dictionary) as Void {
        var keys = mCache.keys();
        var nc = {};
        for (var i = 0; i < keys.size(); i++) {
            var k = keys[i];
            if (keep.hasKey(k)) {
                nc.put(k, mCache.get(k));
            }
        }
        mCache = nc;
    }
}
