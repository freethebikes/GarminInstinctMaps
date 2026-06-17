import Toybox.WatchUi;
import Toybox.Lang;

// Handles the main menu (opened by holding ENTER on the map).
class MapMenuDelegate extends WatchUi.Menu2InputDelegate {

    var mView;

    function initialize(view) {
        Menu2InputDelegate.initialize();
        mView = view;
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var id = item.getId();
        WatchUi.popView(WatchUi.SLIDE_DOWN);   // close the menu, back to the map
        if (id == :regions) {
            mView.openRegions();
        } else if (id == :download) {
            mView.startDownload();
        } else if (id == :clear) {
            mView.clearCache();
        } else if (id == :about) {
            mView.showAbout();
        }
    }

    function onBack() as Void {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }
}
