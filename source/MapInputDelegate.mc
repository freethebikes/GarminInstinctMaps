import Toybox.WatchUi;
import Toybox.Lang;
import Toybox.Timer;

// Maps the Instinct 2's physical buttons onto map actions. The watch's buttons
// are CTRL/MENU/ABC (left, top-to-bottom) and GPS/SET (right); Connect IQ
// reports them as the KEY_* / behaviours below.
//   MENU  (KEY_UP),  ABC (KEY_DOWN) -> step+accelerate in the current mode
//   GPS   (KEY_ENTER/START)         -> tap: cycle ZOOM->TILT->PAN;  hold: menu
//   CTRL  (KEY_LIGHT)               -> flip directly between TILT and PAN
//   SET   (KEY_ESC / onBack)        -> recenter if panned, else leave the app
//   MENU held (onMenu)              -> also opens the menu (Garmin convention)
//
// MENU/ABC/GPS are handled at the raw key level so we can tell press from
// release (for hold-acceleration, and for the GPS tap-vs-hold menu).
class MapInputDelegate extends WatchUi.BehaviorDelegate {

    const MENU_HOLD_MS = 450;

    var mView;
    var mEnterTimer;
    var mMenuOpened;   // true if the current ENTER press already opened the menu

    function initialize(view) {
        BehaviorDelegate.initialize();
        mView = view;
        mEnterTimer = null;
        mMenuOpened = false;
    }

    function onKeyPressed(evt as WatchUi.KeyEvent) as Boolean {
        var key = evt.getKey();
        if (key == WatchUi.KEY_UP) {
            mView.beginHold(1);
            return true;
        } else if (key == WatchUi.KEY_DOWN) {
            mView.beginHold(-1);
            return true;
        } else if (key == WatchUi.KEY_ENTER || key == WatchUi.KEY_START) {
            mMenuOpened = false;
            if (mEnterTimer == null) {
                mEnterTimer = new Timer.Timer();
            }
            mEnterTimer.start(method(:onEnterLong), MENU_HOLD_MS, false);
            return true;
        } else if (key == WatchUi.KEY_LIGHT) {
            mView.toggleAxis();
            return true;
        }
        return false;
    }

    function onKeyReleased(evt as WatchUi.KeyEvent) as Boolean {
        var key = evt.getKey();
        if (key == WatchUi.KEY_UP || key == WatchUi.KEY_DOWN) {
            mView.endHold();
            return true;
        } else if (key == WatchUi.KEY_ENTER || key == WatchUi.KEY_START) {
            if (mEnterTimer != null) {
                mEnterTimer.stop();
            }
            if (!mMenuOpened) {
                mView.cycleMode();   // it was a tap, not a hold
            }
            return true;
        }
        return false;
    }

    // ENTER held past the threshold: open the menu instead of cycling.
    function onEnterLong() as Void {
        mMenuOpened = true;
        mView.openMenu();
    }

    // Holding the MENU button (Garmin's standard menu gesture) also opens it,
    // when the system delivers it as a behaviour rather than a raw KEY_UP.
    function onMenu() as Boolean {
        mView.openMenu();
        return true;
    }

    function onBack() as Boolean {
        if (mView.mManual) {
            mView.recenter();
            return true;
        }
        return false; // allow the system to exit the app
    }
}
