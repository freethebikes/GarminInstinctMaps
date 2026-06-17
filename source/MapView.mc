import Toybox.WatchUi;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.Position;
import Toybox.Timer;

// Renders OSM vector tiles (coastline/water/roads) projected to the screen
// relative to a centre point, with button-driven zoom/pan. White lines on a
// black background to match the Instinct's 1-bit transflective display.
//
// Geometry is projected straight from each tile's integer arrays at draw time;
// we never expand tiles into [lat,lon] objects, to keep within the 96 KB RAM.
class MapView extends WatchUi.View {

    const MIN_SPAN = 100.0;     // closest zoom: metres across screen height
    const MAX_SPAN = 16000.0;   // furthest zoom (overview layer handles this)
    const LOD_SPAN = 2200.0;    // above this span -> overview layer, else detail
                                // (keeps detail loads to <= 2x2 tiles)

    var mStore;        // TileStore: view-based tile loading + eviction
    var mShowLabels;   // toggle for the whole label layer
    var mCenterLat;    // current view centre
    var mCenterLon;
    var mGpsLat;       // last GPS fix
    var mGpsLon;
    var mHasFix;
    var mManual;       // true once the user pans/zooms away from GPS
    var mSpanMeters;   // zoom level
    var mMode;         // 0=ZOOM, 1=TILT (N/S), 2=PAN (E/W)

    // Hold-to-repeat with acceleration.
    var mHoldDir;      // 0=idle, +1/-1 = direction of the held key
    var mHoldTicks;    // ticks since the hold started (drives acceleration)
    var mTimer;        // repeat timer while a key is held

    // Transient status overlay (download progress, "cache cleared", etc).
    var mStatusMsg;    // text to show, or null
    var mStatusTimer;  // auto-clear timer
    var mHintShown;    // one-time "hold GPS = menu" hint shown yet?

    // Download progress shown as a filling ring in the upper-right sub-circle.
    var mDlActive;
    var mDlDone;
    var mDlTotal;

    // Upper-right sub-circle, sized per device in onLayout (the smaller Instinct
    // screens place it differently). Derived from personality.mss sub-windows.
    var mSubCx;
    var mSubCy;
    var mSubR;

    function initialize() {
        View.initialize();
        mStore = new TileStore();
        mShowLabels = true;
        mCenterLat = TileIndex.HOME_LAT;   // centre of the generated data
        mCenterLon = TileIndex.HOME_LON;
        mGpsLat = mCenterLat;
        mGpsLon = mCenterLon;
        mHasFix = false;
        mManual = false;
        mSpanMeters = 1200.0;
        mMode = 0;
        mHoldDir = 0;
        mHoldTicks = 0;
        mTimer = null;
        mStatusMsg = null;
        mStatusTimer = null;
        mHintShown = false;
        mDlActive = false;
        mDlDone = 0;
        mDlTotal = 0;
    }

    function onLayout(dc as Graphics.Dc) as Void {
        var w = dc.getWidth();
        if (w <= 163) {            // Instinct 2S (163x156)
            mSubCx = 136; mSubCy = 27; mSubR = 22;
        } else if (w <= 166) {     // Instinct E 40mm (166x166)
            mSubCx = 138; mSubCy = 26; mSubR = 22;
        } else {                   // 176x176 family
            mSubCx = 145; mSubCy = 31; mSubR = 28;
        }
    }

    function onShow() as Void {
        Position.enableLocationEvents(Position.LOCATION_CONTINUOUS, method(:onPosition));
        if (!mHintShown) {
            mHintShown = true;
            setStatus("Hold GPS = menu", 4000);
        }
    }

    function onHide() as Void {
        endHold();
        Position.enableLocationEvents(Position.LOCATION_DISABLE, method(:onPosition));
    }

    function onPosition(info as Position.Info) as Void {
        if (info != null && info.position != null) {
            var deg = info.position.toDegrees();
            mGpsLat = deg[0];
            mGpsLon = deg[1];
            mHasFix = true;
            if (!mManual) {
                mCenterLat = mGpsLat;
                mCenterLon = mGpsLon;
            }
            WatchUi.requestUpdate();
        }
    }

    // ---- actions invoked by the input delegate ----

    // A key was pressed: apply one step immediately, then start the repeat
    // timer so holding the key keeps moving (and accelerating).
    function beginHold(dir as Number) as Void {
        mHoldDir = dir;
        mHoldTicks = 0;
        applyStep(dir, 1.0);
        WatchUi.requestUpdate();
        if (mTimer == null) {
            mTimer = new Timer.Timer();
        } else {
            mTimer.stop();
        }
        mTimer.start(method(:onHoldTick), 200, true);
    }

    // Repeat tick: step again, faster the longer the key is held.
    function onHoldTick() as Void {
        if (mHoldDir == 0) { return; }
        mHoldTicks += 1;
        var accel = 1.0 + mHoldTicks * 0.6;
        if (accel > 6.0) { accel = 6.0; }
        applyStep(mHoldDir, accel);
        WatchUi.requestUpdate();
    }

    // Key released: stop repeating.
    function endHold() as Void {
        mHoldDir = 0;
        mHoldTicks = 0;
        if (mTimer != null) {
            mTimer.stop();
        }
    }

    // Applies one movement step in the current mode, scaled by `accel`.
    function applyStep(dir as Number, accel as Float) as Void {
        if (mMode == 0) {
            var f = (dir > 0) ? (1.0 / (1.0 + 0.12 * accel)) : (1.0 + 0.12 * accel);
            zoom(f);
        } else if (mMode == 1) {
            panMeters(0.0, dir * panStep() * accel);   // TILT: north/south
        } else {
            panMeters(dir * panStep() * accel, 0.0);    // PAN: east/west
        }
    }

    // ENTER/GPS: cycle ZOOM -> TILT -> PAN.
    function cycleMode() as Void {
        mMode = (mMode + 1) % 3;
        WatchUi.requestUpdate();
    }

    // CTRL/light: jump straight between the two move axes (TILT <-> PAN),
    // or into TILT if currently zooming. The "easy pan/tilt switch".
    function toggleAxis() as Void {
        if (mMode == 0) {
            mMode = 1;
        } else {
            mMode = (mMode == 1) ? 2 : 1;
        }
        WatchUi.requestUpdate();
    }

    function recenter() as Void {
        mManual = false;
        mCenterLat = mGpsLat;
        mCenterLon = mGpsLon;
        WatchUi.requestUpdate();
    }

    // ---- main menu / "download this area" ----

    // Opened by holding ENTER on the map.
    function openMenu() as Void {
        endHold();
        var menu = new WatchUi.Menu2({ :title => "CrudeMaps" });
        menu.addItem(new WatchUi.MenuItem("Regions", "jump to a place", :regions, {}));
        if (mStore.fetchEnabled()) {
            menu.addItem(new WatchUi.MenuItem("Download area", "tiles near here", :download, {}));
            menu.addItem(new WatchUi.MenuItem("Clear cache", null, :clear, {}));
        }
        menu.addItem(new WatchUi.MenuItem("About", null, :about, {}));
        WatchUi.pushView(menu, new MapMenuDelegate(self), WatchUi.SLIDE_UP);
    }

    // Opens the list of named regions to jump to.
    function openRegions() as Void {
        var menu = new WatchUi.Menu2({ :title => "Go to region" });
        for (var i = 0; i < RegionCatalog.REGIONS.size(); i++) {
            var r = RegionCatalog.REGIONS[i] as Dictionary;
            menu.addItem(new WatchUi.MenuItem(r[:name] as String, null, i, {}));
        }
        WatchUi.pushView(menu, new RegionMenuDelegate(self), WatchUi.SLIDE_UP);
    }

    // Recenters the map on a catalog region. Works offline for bundled data;
    // also prefetches the area into Storage when a tile server is configured.
    function goToRegion(idx as Number) as Void {
        var r = RegionCatalog.REGIONS[idx] as Dictionary;
        mManual = true;
        mCenterLat = r[:lat] as Float;
        mCenterLon = r[:lon] as Float;
        if (mSpanMeters > LOD_SPAN) {
            mSpanMeters = 1500.0;   // drop into detail so the place is visible
        }
        if (mStore.fetchEnabled()) {
            startDownload();        // pull this area in for offline use
        }
        WatchUi.requestUpdate();
    }

    function showAbout() as Void {
        WatchUi.pushView(new AboutView(), new AboutDelegate(), WatchUi.SLIDE_UP);
    }

    function startDownload() as Void {
        mDlActive = true;
        mDlDone = 0;
        mDlTotal = 0;
        mStore.prefetch(mCenterLat, mCenterLon, Config.DOWNLOAD_RADIUS,
            method(:onDownloadProgress));
    }

    function onDownloadProgress(done as Number, total as Number, finished as Boolean) as Void {
        mDlDone = done;
        mDlTotal = total;
        if (finished) {
            mDlActive = false;
            setStatus("Saved " + done + "/" + total, 2500);
        }
        WatchUi.requestUpdate();
    }

    function clearCache() as Void {
        mStore.clearCache();
        setStatus("Cache cleared", 2500);
    }

    // Show a transient overlay message; clearMs == 0 means "until replaced".
    function setStatus(msg as String, clearMs as Number) as Void {
        mStatusMsg = msg;
        if (mStatusTimer == null) {
            mStatusTimer = new Timer.Timer();
        }
        mStatusTimer.stop();
        if (clearMs > 0) {
            mStatusTimer.start(method(:clearStatus), clearMs, false);
        }
        WatchUi.requestUpdate();
    }

    function clearStatus() as Void {
        mStatusMsg = null;
        WatchUi.requestUpdate();
    }

    function panStep() as Float {
        return mSpanMeters * 0.12;
    }

    function zoom(factor as Float) as Void {
        mSpanMeters = mSpanMeters * factor;
        if (mSpanMeters < MIN_SPAN) { mSpanMeters = MIN_SPAN; }
        if (mSpanMeters > MAX_SPAN) { mSpanMeters = MAX_SPAN; }
    }

    function panMeters(dxMeters as Float, dyMeters as Float) as Void {
        mManual = true;
        var mPerDegLat = 111320.0;
        var mPerDegLon = 111320.0 * Math.cos(toRad(mCenterLat));
        mCenterLat += dyMeters / mPerDegLat;
        mCenterLon += dxMeters / mPerDegLon;
    }

    function toRad(deg as Float) as Float {
        return deg * Math.PI / 180.0;
    }

    // Roads only show fairly zoomed in; coastline/water names stay visible.
    function labelMaxSpan(cls as Number) as Float {
        return (cls == 2) ? 2500.0 : 99999.0;
    }

    // ---- rendering ----

    function onUpdate(dc as Graphics.Dc) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var cx = w / 2;
        var cy = h / 2;

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        // Equirectangular projection around the current centre latitude.
        var pxPerM = h / mSpanMeters;
        var mPerDegLat = 111320.0;
        var mPerDegLon = 111320.0 * Math.cos(toRad(mCenterLat));

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(1);

        // Pick the layer by zoom: a small overview when zoomed out (crash-free
        // and useful), detailed tiles when zoomed in.
        var tiles;
        if (mSpanMeters > LOD_SPAN) {
            mStore.clearDetail();
            tiles = mStore.overviewTiles();
        } else {
            mStore.clearOverview();
            tiles = mStore.tilesFor(mCenterLat, mCenterLon, mSpanMeters, w, h);
        }
        var labels = [];

        for (var ti = 0; ti < tiles.size(); ti++) {
            var t = tiles[ti] as Dictionary;
            var lat0 = t["lat0"] as Float;
            var lon0 = t["lon0"] as Float;
            var invsc = 1.0 / (t["sc"] as Number).toFloat();

            var lines = t["lines"] as Array;
            for (var li = 0; li < lines.size(); li++) {
                var arr = lines[li] as Array;
                var havePrev = false;
                var prevX = 0.0;
                var prevY = 0.0;
                for (var j = 1; j < arr.size(); j += 2) {
                    var lon = lon0 + (arr[j] as Number) * invsc;
                    var lat = lat0 + (arr[j + 1] as Number) * invsc;
                    var sx = cx + (lon - mCenterLon) * mPerDegLon * pxPerM;
                    var sy = cy - (lat - mCenterLat) * mPerDegLat * pxPerM;
                    if (havePrev) {
                        dc.drawLine(prevX, prevY, sx, sy);
                    }
                    prevX = sx;
                    prevY = sy;
                    havePrev = true;
                }
            }

            // Collect labels (drawn after all lines so plates sit on top).
            if (mShowLabels) {
                var tlabels = t["labels"] as Array;
                for (var bi = 0; bi < tlabels.size(); bi++) {
                    var a = tlabels[bi] as Array;
                    var cls = a[0] as Number;
                    var lon = lon0 + (a[1] as Number) * invsc;
                    var lat = lat0 + (a[2] as Number) * invsc;
                    labels.add([lat, lon, a[3] as String, labelMaxSpan(cls)]);
                }
            }
        }

        if (mShowLabels) {
            drawLabels(dc, cx, cy, pxPerM, mPerDegLat, mPerDegLon, w, h, labels);
        }

        // GPS position marker (white ring with a black centre).
        if (mHasFix) {
            var gx = cx + ((mGpsLon - mCenterLon) * mPerDegLon) * pxPerM;
            var gy = cy - ((mGpsLat - mCenterLat) * mPerDegLat) * pxPerM;
            dc.fillCircle(gx, gy, 4);
            dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_TRANSPARENT);
            dc.fillCircle(gx, gy, 2);
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        }

        // Centre crosshair (the point the view is locked to).
        dc.drawLine(cx - 5, cy, cx + 5, cy);
        dc.drawLine(cx, cy - 5, cx, cy + 5);

        // Status overlay: control mode + current scale.
        var modeStr = ["ZOOM", "TILT", "PAN"][mMode];
        dc.drawText(cx, h - 24, Graphics.FONT_XTINY,
            modeStr + "  " + formatScale(mSpanMeters),
            Graphics.TEXT_JUSTIFY_CENTER);

        // Transient text status (hint, cache cleared, saved) on a plate in the
        // lower band, clear of the upper-right sub-circle.
        if (mStatusMsg != null) {
            var dims = dc.getTextDimensions(mStatusMsg, Graphics.FONT_XTINY);
            var bw = dims[0] + 8;
            var bh = dims[1] + 4;
            var by = h - 48;
            dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_TRANSPARENT);
            dc.fillRectangle(cx - bw / 2, by, bw, bh);
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawRectangle(cx - bw / 2, by, bw, bh);
            dc.drawText(cx, by + bh / 2, Graphics.FONT_XTINY, mStatusMsg,
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }

        // Download progress: a filling ring in the upper-right sub-circle.
        if (mDlActive) {
            drawSubProgress(dc);
        }
    }

    // Draws the download ring (thick arc = done) inside the sub-circle, with the
    // count in the centre. Cheap: a disk, a ring, an arc, and a little text.
    function drawSubProgress(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(mSubCx, mSubCy, mSubR);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(1);
        dc.drawCircle(mSubCx, mSubCy, mSubR - 2);          // empty track

        if (mDlTotal > 0 && mDlDone > 0) {
            var frac = mDlDone.toFloat() / mDlTotal;
            dc.setPenWidth(5);
            if (frac >= 0.999) {
                dc.drawCircle(mSubCx, mSubCy, mSubR - 5);
            } else {
                var endDeg = 90.0 - frac * 360.0;          // clockwise from top
                if (endDeg < 0.0) { endDeg += 360.0; }
                dc.drawArc(mSubCx, mSubCy, mSubR - 5,
                    Graphics.ARC_CLOCKWISE, 90, endDeg);
            }
            dc.setPenWidth(1);
        }

        var label = (mDlTotal > 0) ? (mDlDone + "/" + mDlTotal) : "...";
        dc.drawText(mSubCx, mSubCy, Graphics.FONT_XTINY, label,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    // Draws zoom-gated labels with a black background plate and rejects any
    // label whose box overlaps one already placed this frame.
    // Each label is [lat, lon, text, maxSpan].
    function drawLabels(dc as Graphics.Dc, cx as Number, cy as Number,
                        pxPerM as Float, mPerDegLat as Float, mPerDegLon as Float,
                        w as Number, h as Number, labels as Array) as Void {
        var font = Graphics.FONT_XTINY;
        var placed = [];
        var margin = 2;
        for (var i = 0; i < labels.size(); i++) {
            var lab = labels[i] as Array;
            if (mSpanMeters > (lab[3] as Float)) { continue; }

            var x = cx + ((lab[1] as Float) - mCenterLon) * mPerDegLon * pxPerM;
            var y = cy - ((lab[0] as Float) - mCenterLat) * mPerDegLat * pxPerM;
            var text = lab[2] as String;
            var dims = dc.getTextDimensions(text, font);
            var tw = dims[0];
            var th = dims[1];
            var x0 = x - tw / 2 - margin;
            var y0 = y - th / 2 - margin;
            var x1 = x + tw / 2 + margin;
            var y1 = y + th / 2 + margin;

            if (x1 < 0 || x0 > w || y1 < 0 || y0 > h) { continue; }

            var clash = false;
            for (var k = 0; k < placed.size(); k++) {
                var r = placed[k];
                if (x0 <= r[2] && x1 >= r[0] && y0 <= r[3] && y1 >= r[1]) {
                    clash = true;
                    break;
                }
            }
            if (clash) { continue; }
            placed.add([x0, y0, x1, y1]);

            dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_TRANSPARENT);
            dc.fillRectangle(x0, y0, x1 - x0, y1 - y0);
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(x, y, font, text,
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    function formatScale(span as Float) as String {
        var s = span.toNumber();
        if (s >= 1000) {
            return (s / 1000).toString() + "km";
        }
        return s.toString() + "m";
    }
}
