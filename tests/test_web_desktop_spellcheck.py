import os
from pathlib import Path
import sys
import types

from bettercode.web.desktop import (
    _configure_webview_spellcheck,
    _discover_webengine_dictionaries_path,
    _prepare_webengine_spellcheck_environment,
    _spellcheck_languages,
)


def test_spellcheck_languages_include_system_locale_and_english_fallbacks():
    assert _spellcheck_languages("en_US") == ["en-US", "en"]
    assert _spellcheck_languages("fr-CA") == ["fr-CA", "en-US", "en"]


def test_discover_webengine_dictionaries_path_uses_valid_explicit_override(tmp_path, monkeypatch):
    dictionaries_dir = tmp_path / "qtwebengine_dictionaries"
    dictionaries_dir.mkdir()
    (dictionaries_dir / "en-US.bdic").write_bytes(b"")
    monkeypatch.setenv("QTWEBENGINE_DICTIONARIES_PATH", str(dictionaries_dir))

    assert _discover_webengine_dictionaries_path() == dictionaries_dir.resolve()


def test_discover_webengine_dictionaries_path_falls_back_when_explicit_override_is_invalid(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    dictionaries_dir = app_dir / "qtwebengine_dictionaries"
    dictionaries_dir.mkdir(parents=True)
    (dictionaries_dir / "en-US.bdic").write_bytes(b"")
    monkeypatch.setenv("QTWEBENGINE_DICTIONARIES_PATH", str(tmp_path / "missing"))

    class FakeQCoreApplication:
        @staticmethod
        def instance():
            return object()

        @staticmethod
        def applicationDirPath():
            return str(app_dir)

    assert _discover_webengine_dictionaries_path(
        types.SimpleNamespace(QCoreApplication=FakeQCoreApplication)
    ) == dictionaries_dir.resolve()


def test_discover_webengine_dictionaries_path_skips_application_dir_without_qt_app(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python"))

    class FakeQCoreApplication:
        @staticmethod
        def instance():
            return None

        @staticmethod
        def applicationDirPath():
            raise AssertionError("applicationDirPath should not be used before QApplication exists")

    assert (
        _discover_webengine_dictionaries_path(types.SimpleNamespace(QCoreApplication=FakeQCoreApplication))
        is None
    )


def test_prepare_webengine_spellcheck_environment_sets_dictionary_env(monkeypatch, tmp_path):
    dictionaries_dir = tmp_path / "qtwebengine_dictionaries"
    dictionaries_dir.mkdir()
    monkeypatch.delenv("QTWEBENGINE_DICTIONARIES_PATH", raising=False)
    monkeypatch.setattr(
        "bettercode.web.desktop._discover_webengine_dictionaries_path",
        lambda qt_core_module=None: dictionaries_dir.resolve(),
    )

    assert _prepare_webengine_spellcheck_environment(object()) == dictionaries_dir.resolve()
    assert os.environ["QTWEBENGINE_DICTIONARIES_PATH"] == str(dictionaries_dir.resolve())


def test_configure_webview_spellcheck_enables_profile_and_settings(monkeypatch):
    captured = {}

    class FakeProfile:
        def setSpellCheckEnabled(self, enabled):
            captured["enabled"] = enabled

        def setSpellCheckLanguages(self, languages):
            captured["languages"] = languages

    class FakePage:
        def __init__(self):
            self._profile = FakeProfile()

        def profile(self):
            return self._profile

    class FakeSettings:
        def setAttribute(self, attr, enabled):
            captured["attribute"] = attr
            captured["attribute_enabled"] = enabled

    class FakeView:
        def __init__(self):
            self._page = FakePage()
            self._settings = FakeSettings()

        def page(self):
            return self._page

        def settings(self):
            return self._settings

    class FakeQLocale:
        @staticmethod
        def system():
            class _SystemLocale:
                @staticmethod
                def bcp47Name():
                    return "en-US"

            return _SystemLocale()

    class FakeWebAttribute:
        SpellCheckEnabled = object()

    class FakeQWebEngineSettings:
        WebAttribute = FakeWebAttribute

    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", types.SimpleNamespace(QLocale=FakeQLocale))
    monkeypatch.setitem(sys.modules, "PyQt6.QtWebEngineCore", types.SimpleNamespace(QWebEngineSettings=FakeQWebEngineSettings))
    monkeypatch.setattr(
        "bettercode.web.desktop._prepare_webengine_spellcheck_environment",
        lambda qt_core_module=None: Path("/tmp/qtwebengine_dictionaries"),
    )

    _configure_webview_spellcheck(FakeView())

    assert captured["enabled"] is True
    assert captured["languages"] == ["en-US", "en"]
    assert captured["attribute"] is FakeWebAttribute.SpellCheckEnabled
    assert captured["attribute_enabled"] is True


def test_configure_webview_spellcheck_skips_when_dictionaries_missing(monkeypatch):
    captured = {}

    class FakeProfile:
        def setSpellCheckEnabled(self, enabled):
            captured["enabled"] = enabled

        def setSpellCheckLanguages(self, languages):
            captured["languages"] = languages

    class FakePage:
        def __init__(self):
            self._profile = FakeProfile()

        def profile(self):
            return self._profile

    class FakeSettings:
        def setAttribute(self, attr, enabled):
            captured["attribute"] = attr
            captured["attribute_enabled"] = enabled

    class FakeView:
        def __init__(self):
            self._page = FakePage()
            self._settings = FakeSettings()

        def page(self):
            return self._page

        def settings(self):
            return self._settings

    class FakeQLocale:
        @staticmethod
        def system():
            class _SystemLocale:
                @staticmethod
                def bcp47Name():
                    return "en-US"

            return _SystemLocale()

    class FakeQWebEngineSettings:
        class WebAttribute:
            SpellCheckEnabled = object()

    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", types.SimpleNamespace(QLocale=FakeQLocale))
    monkeypatch.setitem(sys.modules, "PyQt6.QtWebEngineCore", types.SimpleNamespace(QWebEngineSettings=FakeQWebEngineSettings))
    monkeypatch.setattr(
        "bettercode.web.desktop._prepare_webengine_spellcheck_environment",
        lambda qt_core_module=None: None,
    )

    _configure_webview_spellcheck(FakeView())

    assert captured == {}
