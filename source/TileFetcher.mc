import Toybox.Lang;
import Toybox.Communications;
import Toybox.Application.Storage;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

// Fetches tiles that aren't bundled, over the phone, and caches them in
// Application.Storage with simple LRU eviction. All network work is async;
// callers get a tile back later via the onFetched callback.
//
// Storage layout:
//   "t_<ix>_<iy>" => tile Dictionary
//   "lru"         => Array of keys, oldest first
class TileFetcher {

    var mEnabled;     // false when SERVER_URL is empty (bundled-only build)
    var mStatic;      // true = fetch static files, false = dynamic dev server
    var mOnFetched;   // method(key, tile) called when a passive fetch succeeds
    var mPending;     // "ix_iy" => time(ms) of last attempt (throttle/dedupe)

    // "Download this area" prefetch state (sequential queue).
    var mQueue;       // Array of [ix, iy] still to fetch
    var mDownDone;
    var mDownTotal;
    var mProgressCb;  // method(done, total, finished)

    const RETRY_MS = 8000;   // don't re-request a failing tile faster than this

    function initialize(onFetched as Method) {
        mEnabled = !Config.SERVER_URL.equals("");
        mStatic = Config.STATIC_TILES;
        mOnFetched = onFetched;
        mPending = {};
        mQueue = [];
        mDownDone = 0;
        mDownTotal = 0;
        mProgressCb = null;
    }

    // Returns the cached tile for (ix,iy), or null. On a miss it kicks off an
    // async fetch (if online) and still returns null for now.
    function get(ix as Number, iy as Number) as Dictionary? {
        var key = ix + "_" + iy;
        var cached = Storage.getValue("t_" + key);
        if (cached != null) {
            return cached as Dictionary;
        }
        request(ix, iy, key);
        return null;
    }

    // Issue a web request for a tile unless one is in flight / recently tried,
    // we're offline, or fetching is disabled.
    function request(ix as Number, iy as Number, key as String) as Void {
        if (!mEnabled) {
            return;
        }
        var now = System.getTimer();
        var last = mPending.get(key);
        if (last != null && (now - last) < RETRY_MS) {
            return;
        }
        if (!System.getDeviceSettings().connectionAvailable) {
            return;
        }
        mPending.put(key, now);
        requestTile(ix, iy, method(:onResponse));
    }

    // Issues the tile web request in whichever URL form is configured.
    function requestTile(ix as Number, iy as Number, cb as Method) as Void {
        var url;
        var params;
        if (mStatic) {
            url = Config.SERVER_URL + "/tile_" + ix + "_" + iy + ".json";
            params = {};
        } else {
            url = Config.SERVER_URL + "/tile";
            params = { "ix" => ix, "iy" => iy };
        }
        Communications.makeWebRequest(url, params, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, cb);
    }

    // makeWebRequest callback. We don't know ix/iy here directly, so the tile
    // carries lat0/lon0 and we recompute its key from the shared grid.
    function onResponse(code as Number, data as Dictionary?) as Void {
        if (code != 200 || data == null) {
            return; // leave it in mPending so RETRY_MS throttles re-tries
        }
        var key = keyFromData(data);
        Storage.setValue("t_" + key, data);
        touchLru(key);
        mPending.remove(key);
        mOnFetched.invoke(key, data);
    }

    // A tile carries its SW origin; recover its grid key from that.
    function keyFromData(data as Dictionary) as String {
        var ix = TileIndex.tileX((data["lon0"] as Float) + TileIndex.TILE_DEG * 0.5);
        var iy = TileIndex.tileY((data["lat0"] as Float) + TileIndex.TILE_DEG * 0.5);
        return ix + "_" + iy;
    }

    // ---- "Download this area": prefetch a square of tiles into Storage ----

    function prefetchArea(cix as Number, ciy as Number, radius as Number,
                          progressCb as Method) as Void {
        mQueue = [];
        for (var dx = -radius; dx <= radius; dx++) {
            for (var dy = -radius; dy <= radius; dy++) {
                mQueue.add([cix + dx, ciy + dy]);
            }
        }
        mDownTotal = mQueue.size();
        mDownDone = 0;
        mProgressCb = progressCb;
        pump();
    }

    // Fetch the next queued tile (skipping ones already cached). One request is
    // in flight at a time, advanced by onPrefetchResponse.
    function pump() as Void {
        var offline = !mEnabled
            || !System.getDeviceSettings().connectionAvailable;
        while (mQueue.size() > 0) {
            var pair = mQueue[0];
            mQueue = mQueue.slice(1, null);
            var key = pair[0] + "_" + pair[1];
            if (Storage.getValue("t_" + key) != null || offline) {
                mDownDone += 1;          // already have it (or can't fetch)
                continue;
            }
            requestTile(pair[0], pair[1], method(:onPrefetchResponse));
            notifyProgress(false);
            return;
        }
        notifyProgress(true);            // queue drained -> done
    }

    function onPrefetchResponse(code as Number, data as Dictionary?) as Void {
        if (code == 200 && data != null) {
            var key = keyFromData(data);
            Storage.setValue("t_" + key, data);
            touchLru(key);
        }
        mDownDone += 1;
        pump();
    }

    function notifyProgress(finished as Boolean) as Void {
        if (mProgressCb != null) {
            mProgressCb.invoke(mDownDone, mDownTotal, finished);
        }
    }

    // Delete every cached tile and the LRU index.
    function clearCache() as Void {
        var lru = Storage.getValue("lru") as Array?;
        if (lru != null) {
            for (var i = 0; i < lru.size(); i++) {
                Storage.deleteValue("t_" + (lru[i] as String));
            }
        }
        Storage.deleteValue("lru");
    }

    // Move key to the most-recent end of the LRU list and evict the oldest
    // entries beyond the cap.
    function touchLru(key as String) as Void {
        var lru = Storage.getValue("lru") as Array?;
        if (lru == null) {
            lru = [];
        }
        lru.removeAll(key);
        lru.add(key);
        while (lru.size() > Config.CACHE_CAP) {
            var old = lru[0] as String;
            lru.remove(old);
            Storage.deleteValue("t_" + old);
        }
        Storage.setValue("lru", lru);
    }
}
