import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

// Application entry point. Hands the system the map view + its input delegate.
class MapApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Dictionary?) as Void {
    }

    function onStop(state as Dictionary?) as Void {
    }

    function getInitialView() {
        var view = new MapView();
        var delegate = new MapInputDelegate(view);
        return [view, delegate];
    }
}
