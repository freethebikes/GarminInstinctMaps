import Toybox.WatchUi;
import Toybox.Graphics;
import Toybox.Lang;

// About / attribution screen. OpenStreetMap data is ODbL-licensed, so the
// "© OpenStreetMap contributors" credit must be shown in the app.
class AboutView extends WatchUi.View {

    function initialize() {
        View.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);

        var cx = w / 2;
        // The full name is too wide for FONT_SMALL near the top of the round
        // screen, so drop to a smaller font when it doesn't fit.
        var name = WatchUi.loadResource(Rez.Strings.AppName) as String;
        var font = Graphics.FONT_SMALL;
        if (dc.getTextWidthInPixels(name, font) > w * 0.75) {
            font = Graphics.FONT_XTINY;
        }
        dc.drawText(cx, h * 0.20, font, name, Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, h * 0.36, Graphics.FONT_XTINY, "v" + Config.APP_VERSION,
            Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, h * 0.52, Graphics.FONT_XTINY, "Map data",
            Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, h * 0.64, Graphics.FONT_XTINY, "(c) OpenStreetMap",
            Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, h * 0.74, Graphics.FONT_XTINY, "contributors",
            Graphics.TEXT_JUSTIFY_CENTER);
    }
}

// Any key / back dismisses the About screen.
class AboutDelegate extends WatchUi.BehaviorDelegate {
    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onBack() as Boolean {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
        return true;
    }

    function onKey(evt as WatchUi.KeyEvent) as Boolean {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
        return true;
    }
}
