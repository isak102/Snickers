"""
League of Legends Black Bars Script

Creates a black background behind the League of Legends game window when it's focused,
and hides the Windows taskbar. Restores everything when League loses focus or is minimized.
"""

from __future__ import annotations

import ctypes
import signal
import sys
import time
from typing import Any

import win32api
import win32con
import win32gui

# Constants
LEAGUE_WINDOW_TITLE = "League of Legends (TM) Client"
POLL_INTERVAL_MS = 100
TASKBAR_CLASS = "Shell_TrayWnd"
START_BUTTON_CLASS = "Button"

# Global state
black_window_hwnd = None
black_bars_active = False


# =============================================================================
# Window Detection
# =============================================================================


def get_foreground_window() -> int:
    """Get the handle of the currently focused window."""
    return win32gui.GetForegroundWindow()


def get_window_title(hwnd: int) -> str:
    """Get the title of a window by its handle."""
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return ""


def is_window_minimized(hwnd: int) -> bool:
    """Check if a window is minimized."""
    try:
        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def is_league_game_window(hwnd: int) -> bool:
    """Check if the given window handle is the League of Legends game window."""
    return get_window_title(hwnd) == LEAGUE_WINDOW_TITLE


def find_league_window() -> int | None:
    """Find the League of Legends game window handle."""
    return win32gui.FindWindow(None, LEAGUE_WINDOW_TITLE) or None


# =============================================================================
# Monitor Detection
# =============================================================================


def get_monitor_info(hwnd: int) -> Any:
    """Get information about the monitor containing the specified window."""
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        monitor_info = win32api.GetMonitorInfo(monitor)
        return monitor_info
    except Exception:
        return None


def get_monitor_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Get the full screen rectangle of the monitor containing the window.

    Returns (left, top, right, bottom) or None if unable to determine.
    """
    monitor_info = get_monitor_info(hwnd)
    if monitor_info:
        # Use 'Monitor' rect (full screen) instead of 'Work' rect (excludes taskbar)
        return monitor_info["Monitor"]
    return None


# =============================================================================
# Black Background Window
# =============================================================================


def create_window_class() -> str:
    """Register a window class for the black background window."""
    class_name = "LeagueBlackBarsWindow"

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = {  # type: ignore[assignment]
        win32con.WM_DESTROY: lambda hwnd,
        msg,
        wparam,
        lparam: ctypes.windll.user32.PostQuitMessage(0),  # type: ignore[attr-defined]
    }
    wc.lpszClassName = class_name  # type: ignore[assignment]
    wc.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)  # type: ignore[assignment]
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)  # type: ignore[assignment]

    try:
        win32gui.RegisterClass(wc)
    except Exception:
        # Class may already be registered
        pass

    return class_name


def create_black_window(monitor_rect: tuple[int, int, int, int]) -> int:
    """Create a fullscreen black window on the specified monitor.

    Args:
        monitor_rect: (left, top, right, bottom) coordinates of the monitor

    Returns:
        Window handle of the created window
    """
    class_name = create_window_class()

    left, top, right, bottom = monitor_rect
    width = right - left
    height = bottom - top

    # Create a layered, tool window (no taskbar entry) that's also transparent to input
    ex_style = (
        win32con.WS_EX_LAYERED
        | win32con.WS_EX_TOOLWINDOW
        | win32con.WS_EX_TRANSPARENT  # Click-through
        | win32con.WS_EX_NOACTIVATE  # Don't take focus
    )

    style = win32con.WS_POPUP  # Borderless window

    hwnd = win32gui.CreateWindowEx(
        ex_style,
        class_name,
        "Black Background",
        style,
        left,
        top,
        width,
        height,
        0,
        0,
        0,
        None,
    )

    # Set the window to be fully opaque black
    # For layered windows, we need to set the layered attributes
    ctypes.windll.user32.SetLayeredWindowAttributes(  # type: ignore[attr-defined]
        hwnd,
        0,  # Color key (not used)
        255,  # Alpha (fully opaque)
        win32con.LWA_ALPHA,
    )

    return hwnd


def show_black_window(hwnd: int, league_hwnd: int) -> None:
    """Show the black window and position it just below the League window in z-order."""
    # Position the black window just below League in the z-order
    # This ensures it's behind League but in front of everything else
    win32gui.SetWindowPos(
        hwnd,
        league_hwnd,  # Insert after (below) League window
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE
        | win32con.SWP_SHOWWINDOW,
    )


def hide_black_window(hwnd: int) -> None:
    """Hide the black background window."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    except Exception:
        pass


def destroy_black_window(hwnd: int) -> None:
    """Destroy the black background window."""
    try:
        win32gui.DestroyWindow(hwnd)
    except Exception:
        pass


# =============================================================================
# Taskbar Management
# =============================================================================


def find_taskbar() -> int | None:
    """Find the Windows taskbar window handle."""
    return win32gui.FindWindow(TASKBAR_CLASS, None) or None


def find_start_button() -> int | None:
    """Find the Windows Start button window handle."""
    taskbar = find_taskbar()
    if taskbar:
        # The Start button is usually a child or nearby window
        start = win32gui.FindWindowEx(0, 0, START_BUTTON_CLASS, "Start")
        return start or None
    return None


def hide_taskbar() -> None:
    """Hide the Windows taskbar."""
    taskbar = find_taskbar()
    if taskbar:
        win32gui.ShowWindow(taskbar, win32con.SW_HIDE)

    # Also try to hide the Start button (Windows 10+)
    start = find_start_button()
    if start:
        win32gui.ShowWindow(start, win32con.SW_HIDE)


def show_taskbar() -> None:
    """Show the Windows taskbar."""
    taskbar = find_taskbar()
    if taskbar:
        win32gui.ShowWindow(taskbar, win32con.SW_SHOW)

    # Also restore the Start button
    start = find_start_button()
    if start:
        win32gui.ShowWindow(start, win32con.SW_SHOW)


# =============================================================================
# Main Logic
# =============================================================================


def activate_black_bars(league_hwnd: int) -> None:
    """Activate black bars mode for the given League window."""
    global black_window_hwnd, black_bars_active

    # Get the monitor where League is displayed
    monitor_rect = get_monitor_rect(league_hwnd)
    if not monitor_rect:
        print("Warning: Could not determine monitor for League window")
        return

    # Create and show the black background window
    if black_window_hwnd is None:
        black_window_hwnd = create_black_window(monitor_rect)

    show_black_window(black_window_hwnd, league_hwnd)
    hide_taskbar()
    black_bars_active = True
    print(f"Black bars activated on monitor: {monitor_rect}")


def deactivate_black_bars() -> None:
    """Deactivate black bars mode."""
    global black_window_hwnd, black_bars_active

    if black_window_hwnd:
        hide_black_window(black_window_hwnd)

    show_taskbar()
    black_bars_active = False
    print("Black bars deactivated")


def cleanup() -> None:
    """Clean up resources and restore system state."""
    global black_window_hwnd

    print("\nCleaning up...")

    # Always restore the taskbar
    show_taskbar()

    # Destroy the black window if it exists
    if black_window_hwnd:
        destroy_black_window(black_window_hwnd)
        black_window_hwnd = None

    print("Cleanup complete")


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    cleanup()
    sys.exit(0)


def main() -> None:
    """Main entry point."""
    global black_bars_active

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("League of Legends Black Bars Script")
    print("=" * 40)
    print(f"Monitoring for window: '{LEAGUE_WINDOW_TITLE}'")
    print(f"Poll interval: {POLL_INTERVAL_MS}ms")
    print("Press Ctrl+C to exit")
    print("=" * 40)

    try:
        while True:
            foreground_hwnd = get_foreground_window()

            # Check if League is the focused window and not minimized
            if is_league_game_window(foreground_hwnd) and not is_window_minimized(
                foreground_hwnd
            ):
                if not black_bars_active:
                    activate_black_bars(foreground_hwnd)
            else:
                if black_bars_active:
                    deactivate_black_bars()

            time.sleep(POLL_INTERVAL_MS / 1000)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
