import Toybox.WatchUi;
import Toybox.Lang;

// Handles the Regions menu: selecting a place jumps the map to it.
class RegionMenuDelegate extends WatchUi.Menu2InputDelegate {

    var mView;

    function initialize(view) {
        Menu2InputDelegate.initialize();
        mView = view;
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var idx = item.getId() as Number;
        WatchUi.popView(WatchUi.SLIDE_DOWN);
        mView.goToRegion(idx);
    }

    function onBack() as Void {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }
}
