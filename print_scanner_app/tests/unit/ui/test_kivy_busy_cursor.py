from unittest.mock import MagicMock

from print_scanner_app.ui.kivy_busy_cursor import KivyBusyCursor


def test_busy_cursor_schedules_wait_and_arrow():
    clock = MagicMock()
    window = MagicMock()
    busy = KivyBusyCursor(clock, window)
    busy.show_wait()
    busy.clear()
    assert clock.schedule_once.call_count == 2
