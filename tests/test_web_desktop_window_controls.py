import sys

from bettercode.web.desktop import _toggle_window_maximize_restore, _window_is_effectively_maximized


def test_toggle_window_maximize_restore_uses_fullscreen_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)

    class FakeWindow:
        def __init__(self):
            self.calls = []
            self.fullscreen = False

        def isFullScreen(self):
            return self.fullscreen

        def showFullScreen(self):
            self.calls.append("fullscreen")
            self.fullscreen = True

        def showNormal(self):
            self.calls.append("normal")
            self.fullscreen = False

    window = FakeWindow()
    _toggle_window_maximize_restore(window)
    _toggle_window_maximize_restore(window)

    assert window.calls == ["fullscreen", "normal"]


def test_toggle_window_maximize_restore_uses_maximize_on_non_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)

    class FakeWindow:
        def __init__(self):
            self.calls = []
            self.maximized = False

        def isMaximized(self):
            return self.maximized

        def showMaximized(self):
            self.calls.append("max")
            self.maximized = True

        def showNormal(self):
            self.calls.append("normal")
            self.maximized = False

    window = FakeWindow()
    _toggle_window_maximize_restore(window)
    _toggle_window_maximize_restore(window)

    assert window.calls == ["max", "normal"]


def test_window_is_effectively_maximized_uses_platform_specific_state(monkeypatch):
    class MacWindow:
        def isFullScreen(self):
            return True

    class LinuxWindow:
        def isMaximized(self):
            return True

    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    assert _window_is_effectively_maximized(MacWindow()) is True

    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    assert _window_is_effectively_maximized(LinuxWindow()) is True
