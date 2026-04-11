import ctypes.util
import os
from pathlib import Path
import shlex
import socket
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import uvicorn

from bettercode.app_meta import (
    APP_BUNDLE_ID,
    APP_ICON_PATH,
    APP_ICON_PNG_PATH,
    APP_ICNS_PATH,
    APP_NAME,
    APP_SLUG,
    APP_TRAY_ICON_PATH,
)
from .api import create_app
from .bootstrap import _start_selector_runtime_warmup, _warm_selector_runtime_best_effort


class EmbeddedServer(uvicorn.Server):
    def install_signal_handlers(self):
        return


class DirectoryPicker:
    def __init__(self, qt_app):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Bridge(QObject):
            requested = pyqtSignal()

        self._qt_app = qt_app
        self._bridge = _Bridge()
        self._bridge.requested.connect(self._choose_on_main_thread)
        self._event = None
        self._result = None

    def choose_directory(self) -> str | None:
        event = threading.Event()
        self._event = event
        self._result = None
        self._bridge.requested.emit()
        event.wait()
        return self._result

    def _choose_on_main_thread(self):
        from PyQt6.QtWidgets import QFileDialog

        self._result = QFileDialog.getExistingDirectory(
            None,
            "Choose Project Folder",
            os.getcwd(),
        ) or None

        if self._event is not None:
            self._event.set()


class SaveFilePicker:
    def __init__(self, qt_app):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Bridge(QObject):
            requested = pyqtSignal(str)

        self._qt_app = qt_app
        self._bridge = _Bridge()
        self._bridge.requested.connect(self._choose_on_main_thread)
        self._event = None
        self._result = None
        self._suggested_name = "code-review-report.html"

    def choose_html_file(self, suggested_name: str) -> str | None:
        event = threading.Event()
        self._event = event
        self._result = None
        self._suggested_name = _normalize_html_filename(suggested_name)
        self._bridge.requested.emit(self._suggested_name)
        event.wait()
        return self._result

    def _choose_on_main_thread(self, suggested_name: str):
        from PyQt6.QtWidgets import QFileDialog

        default_dir = Path.home() / "Downloads"
        if not default_dir.exists():
            default_dir = Path.home()
        default_path = str((default_dir / _normalize_html_filename(suggested_name)).resolve())
        selected_path, _ = QFileDialog.getSaveFileName(
            None,
            "Save Code Review Report",
            default_path,
            "HTML Files (*.html);;All Files (*)",
        )
        self._result = selected_path or None
        if self._event is not None:
            self._event.set()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)

    raise RuntimeError("Embedded API server did not start in time.")


def _app_icon_path() -> Path:
    """Return the best available icon for the current platform.

    Runtime Qt/Dock icon loading is more reliable with a normal raster image
    than a bundle-only .icns file, so macOS and Linux both prefer the PNG.
    """
    if (sys.platform == "darwin" or sys.platform.startswith("linux")) and APP_ICON_PNG_PATH.exists():
        return APP_ICON_PNG_PATH
    return APP_ICON_PATH


def _xdg_data_home() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    return Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"


def _linux_desktop_file_name() -> str:
    return f"{APP_SLUG}.desktop"


def _linux_desktop_file_id() -> str:
    return APP_SLUG


def _linux_desktop_entry_path() -> Path:
    return _xdg_data_home() / "applications" / _linux_desktop_file_name()


def _linux_icon_export_path() -> Path:
    icon_name = f"{APP_SLUG}.png" if APP_ICON_PNG_PATH.exists() else f"{APP_SLUG}.svg"
    theme_dir = "512x512" if APP_ICON_PNG_PATH.exists() else "scalable"
    return _xdg_data_home() / "icons" / "hicolor" / theme_dir / "apps" / icon_name


def _linux_launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]

    argv0 = (sys.argv[0] or "").strip()
    if argv0:
        argv0_path = Path(argv0)
        if argv0_path.is_absolute():
            return [str(argv0_path)]
        resolved = shutil.which(argv0) or shutil.which(APP_SLUG)
        if resolved:
            return [resolved]

    return [sys.executable, "-m", "bettercode.main"]


def _ensure_linux_desktop_entry() -> Path | None:
    if not sys.platform.startswith("linux"):
        return None

    icon_source = APP_ICON_PNG_PATH if APP_ICON_PNG_PATH.exists() else APP_ICON_PATH
    desktop_path = _linux_desktop_entry_path()
    icon_path = _linux_icon_export_path()
    exec_line = " ".join(shlex.quote(part) for part in _linux_launch_command())

    try:
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_source, icon_path)
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_path.write_text(
            "\n".join([
                "[Desktop Entry]",
                "Version=1.0",
                "Type=Application",
                f"Name={APP_NAME}",
                "Comment=Local-first coding workspace",
                f"Exec={exec_line}",
                f"Icon={APP_SLUG}",
                "Terminal=false",
                "Categories=Development;IDE;",
                "StartupNotify=true",
                f"StartupWMClass={APP_NAME}",
                "",
            ]),
            encoding="utf-8",
        )
    except OSError:
        return None

    return desktop_path


def _qt_application_argv(argv: list[str] | None = None) -> list[str]:
    qt_argv = list(argv if argv is not None else sys.argv)
    if qt_argv:
        qt_argv[0] = APP_NAME
        return qt_argv
    return [APP_NAME]


def _set_macos_dock_icon(icon_path: Path) -> None:
    """Set the macOS Dock (NSApplication) icon via the Obj-C runtime.

    This overrides the Python.app icon that macOS would otherwise inherit
    when the process is launched as a bare Python script rather than a
    bundled .app.  Uses the same ctypes bridge pattern already used
    elsewhere in this file — no PyObjC dependency required.
    """
    if sys.platform != "darwin":
        return
    if not icon_path.exists():
        return
    try:
        objc_path = ctypes.util.find_library("objc")
        appkit_path = ctypes.util.find_library("AppKit")
        if not objc_path or not appkit_path:
            return

        ctypes.CDLL(appkit_path, ctypes.RTLD_GLOBAL)
        objc = ctypes.CDLL(objc_path)

        objc_getClass = objc.objc_getClass
        objc_getClass.restype = ctypes.c_void_p
        objc_getClass.argtypes = [ctypes.c_char_p]

        sel_registerName = objc.sel_registerName
        sel_registerName.restype = ctypes.c_void_p
        sel_registerName.argtypes = [ctypes.c_char_p]

        def cls(name: str) -> int:
            return int(objc_getClass(name.encode()))

        def sel(name: str) -> int:
            return int(sel_registerName(name.encode()))

        # id objc_msgSend(id, SEL) — generic object return
        f_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_id = f_id(("objc_msgSend", objc))

        # id objc_msgSend(id, SEL, id) — one object arg
        f_id_obj = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_id_obj = f_id_obj(("objc_msgSend", objc))

        # void objc_msgSend(id, SEL, id) — setter
        f_void_obj = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_void_obj = f_void_obj(("objc_msgSend", objc))

        # Build NSString from the icon path
        ns_string_cls = cls("NSString")
        path_str = msg_id_obj(
            ns_string_cls,
            sel("stringWithUTF8String:"),
            icon_path.as_posix().encode("utf-8"),
        )
        if not path_str:
            return

        # NSImage *img = [[NSImage alloc] initWithContentsOfFile: path_str]
        ns_image_cls = cls("NSImage")
        img_alloc = msg_id(ns_image_cls, sel("alloc"))
        if not img_alloc:
            return
        ns_image = msg_id_obj(img_alloc, sel("initWithContentsOfFile:"), path_str)
        if not ns_image:
            return

        # [NSApplication sharedApplication].applicationIconImage = img
        ns_app_cls = cls("NSApplication")
        ns_app = msg_id(ns_app_cls, sel("sharedApplication"))
        if not ns_app:
            return
        msg_void_obj(ns_app, sel("setApplicationIconImage:"), ns_image)
    except Exception:
        return


def _normalize_html_filename(filename: str) -> str:
    candidate = (filename or "").strip() or "code-review-report"
    candidate = Path(candidate).name
    if not candidate.lower().endswith(".html"):
        candidate = f"{candidate}.html"
    return candidate


def _write_html_report(path: str | Path, html: str) -> str:
    target = Path(path)
    if target.suffix.lower() != ".html":
        target = target.with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return str(target)


def _check_linux_qt_prereqs():
    if not sys.platform.startswith("linux"):
        return

    if ctypes.util.find_library("xcb-cursor") is None:
        print(
            "BetterCode warning: missing Linux Qt library 'xcb-cursor'. "
            "Install your distro's xcb-cursor package if the desktop window fails to launch.",
            file=sys.stderr,
        )


def _disable_chromium_feature(feature: str):
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if not flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"--disable-features={feature}"
        return

    tokens = flags.split()
    for index, token in enumerate(tokens):
        if token.startswith("--disable-features="):
            existing = token.split("=", 1)[1]
            features = [name for name in existing.split(",") if name]
            if feature in features:
                return
            features.append(feature)
            tokens[index] = "--disable-features=" + ",".join(features)
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(tokens)
            return

    tokens.append(f"--disable-features={feature}")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(tokens)


def _spellcheck_languages(system_locale: str | None = None) -> list[str]:
    preferred = (system_locale or "").strip().replace("_", "-")
    languages: list[str] = []
    if preferred:
        languages.append(preferred)
    for fallback in ("en-US", "en"):
        if fallback.lower() not in {entry.lower() for entry in languages}:
            languages.append(fallback)
    return languages


def _spellcheck_dictionary_dir(path: str | Path | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_dir():
        return None
    try:
        has_dictionary = any(
            entry.is_file() and entry.suffix.lower() == ".bdic"
            for entry in candidate.iterdir()
        )
    except OSError:
        return None
    return candidate if has_dictionary else None


def _qt_library_info_data_path(qt_core_module) -> Path | None:
    qlibrary_info = getattr(qt_core_module, "QLibraryInfo", None)
    if qlibrary_info is None:
        return None

    library_path = getattr(qlibrary_info, "LibraryPath", None)
    data_path_enum = getattr(library_path, "DataPath", None)
    if data_path_enum is None:
        library_location = getattr(qlibrary_info, "LibraryLocation", None)
        data_path_enum = getattr(library_location, "DataPath", None)
    if data_path_enum is None:
        return None

    path_getter = getattr(qlibrary_info, "path", None)
    if callable(path_getter):
        data_path = path_getter(data_path_enum)
    else:
        location_getter = getattr(qlibrary_info, "location", None)
        if not callable(location_getter):
            return None
        data_path = location_getter(data_path_enum)

    if not data_path:
        return None
    return Path(data_path).expanduser().resolve()


def _spellcheck_dictionary_candidates(qt_core_module=None) -> list[Path]:
    candidates: list[Path] = []

    def add_candidate(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.expanduser().resolve()
        if resolved not in candidates:
            candidates.append(resolved)

    explicit_path = os.environ.get("QTWEBENGINE_DICTIONARIES_PATH")
    if explicit_path is not None:
        resolved = _spellcheck_dictionary_dir(explicit_path)
        add_candidate(resolved)

    qcore_application = getattr(qt_core_module, "QCoreApplication", None)
    if qcore_application is not None and hasattr(qcore_application, "applicationDirPath"):
        instance_getter = getattr(qcore_application, "instance", None)
        qt_app_instance = instance_getter() if callable(instance_getter) else None
        if qt_app_instance is not None:
            try:
                application_dir = qcore_application.applicationDirPath()
            except Exception:
                application_dir = ""
            if application_dir:
                base_dir = Path(application_dir)
                add_candidate(base_dir / "qtwebengine_dictionaries")
                if sys.platform == "darwin":
                    add_candidate(base_dir.parent / "Resources" / "qtwebengine_dictionaries")

    if sys.executable:
        executable_dir = Path(sys.executable).resolve().parent
        add_candidate(executable_dir / "qtwebengine_dictionaries")
        if sys.platform == "darwin":
            add_candidate(executable_dir.parent / "Resources" / "qtwebengine_dictionaries")

    data_path = _qt_library_info_data_path(qt_core_module)
    if data_path is not None:
        add_candidate(data_path / "qtwebengine_dictionaries")

    return candidates


def _discover_webengine_dictionaries_path(qt_core_module=None) -> Path | None:
    for candidate in _spellcheck_dictionary_candidates(qt_core_module):
        resolved = _spellcheck_dictionary_dir(candidate)
        if resolved is not None:
            return resolved
    return None


def _prepare_webengine_spellcheck_environment(qt_core_module=None) -> Path | None:
    if qt_core_module is None:
        qt_core_module = sys.modules.get("PyQt6.QtCore")
        if qt_core_module is None:
            try:
                from PyQt6 import QtCore as qt_core_module
            except Exception:
                qt_core_module = None

    dictionaries_path = _discover_webengine_dictionaries_path(qt_core_module)
    if dictionaries_path is None:
        return None

    os.environ["QTWEBENGINE_DICTIONARIES_PATH"] = str(dictionaries_path)
    return dictionaries_path


def _configure_webview_spellcheck(webview) -> None:
    try:
        from PyQt6.QtCore import QLocale
        from PyQt6.QtWebEngineCore import QWebEngineSettings

        qt_core_module = sys.modules.get("PyQt6.QtCore")
        if _prepare_webengine_spellcheck_environment(qt_core_module) is None:
            return

        system_locale = QLocale.system().bcp47Name()
        profile = webview.page().profile()
        if hasattr(profile, "setSpellCheckEnabled"):
            profile.setSpellCheckEnabled(True)
        if hasattr(profile, "setSpellCheckLanguages"):
            profile.setSpellCheckLanguages(_spellcheck_languages(system_locale))

        settings = webview.settings()
        web_attribute = getattr(QWebEngineSettings.WebAttribute, "SpellCheckEnabled", None)
        if web_attribute is not None and hasattr(settings, "setAttribute"):
            settings.setAttribute(web_attribute, True)
    except Exception:
        return


def _set_macos_app_identity(app_name: str):
    if sys.platform != "darwin":
        return

    try:
        from Foundation import NSProcessInfo  # type: ignore

        NSProcessInfo.processInfo().setProcessName_(app_name)
        return
    except Exception:
        pass

    try:
        objc_path = ctypes.util.find_library("objc")
        if not objc_path:
            return
        objc = ctypes.CDLL(objc_path)

        objc_getClass = objc.objc_getClass
        objc_getClass.restype = ctypes.c_void_p
        objc_getClass.argtypes = [ctypes.c_char_p]

        sel_registerName = objc.sel_registerName
        sel_registerName.restype = ctypes.c_void_p
        sel_registerName.argtypes = [ctypes.c_char_p]

        msg_send_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
        msg_send_char = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(("objc_msgSend", objc))
        msg_send_obj = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
        def cls(name: str) -> int:
            return int(objc_getClass(name.encode("utf-8")))

        def sel(name: str) -> int:
            return int(sel_registerName(name.encode("utf-8")))

        ns_string_class = cls("NSString")
        ns_process_info_class = cls("NSProcessInfo")
        if not ns_string_class or not ns_process_info_class:
            return

        app_name_ns = msg_send_char(ns_string_class, sel("stringWithUTF8String:"), app_name.encode("utf-8"))
        process_info = msg_send_id(ns_process_info_class, sel("processInfo"))
        if process_info and app_name_ns:
            msg_send_obj(process_info, sel("setProcessName:"), app_name_ns)
    except Exception:
        return


def _setup_macos_transparent_titlebar(window):
    """Extend content into the macOS titlebar for an integrated look."""
    if sys.platform != "darwin":
        return
    try:
        objc_path = ctypes.util.find_library("objc")
        if not objc_path:
            return
        objc = ctypes.CDLL(objc_path)

        sel_registerName = objc.sel_registerName
        sel_registerName.restype = ctypes.c_void_p
        sel_registerName.argtypes = [ctypes.c_char_p]

        def sel(name: str):
            return sel_registerName(name.encode())

        # id objc_msgSend(id, SEL) — returns object
        f_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_id = f_id(("objc_msgSend", objc))

        # void objc_msgSend(id, SEL, BOOL)
        f_setbool = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)
        msg_setbool = f_setbool(("objc_msgSend", objc))

        # NSUInteger objc_msgSend(id, SEL) — returns unsigned long
        f_getulong = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)
        msg_getulong = f_getulong(("objc_msgSend", objc))

        # void objc_msgSend(id, SEL, NSUInteger)
        f_setulong = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        msg_setulong = f_setulong(("objc_msgSend", objc))

        # void objc_msgSend(id, SEL, NSInteger)
        f_setlong = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
        msg_setlong = f_setlong(("objc_msgSend", objc))

        # Get the NSView from winId() then the NSWindow from the view
        ns_view = int(window.winId())
        ns_window = msg_id(ns_view, sel("window"))
        if not ns_window:
            return

        # Make titlebar visually transparent so app content shows through
        msg_setbool(ns_window, sel("setTitlebarAppearsTransparent:"), True)

        # Extend content view to fill the full window (behind the titlebar)
        NSWindowStyleMaskFullSizeContentView = 1 << 15
        current_mask = msg_getulong(ns_window, sel("styleMask"))
        msg_setulong(ns_window, sel("setStyleMask:"), current_mask | NSWindowStyleMaskFullSizeContentView)

        # Hide the title text (traffic lights stay)
        NSWindowTitleHidden = 1
        msg_setlong(ns_window, sel("setTitleVisibility:"), NSWindowTitleHidden)

    except Exception:
        return


def _should_show_completion_notification(*, is_visible: bool, is_minimized: bool, is_active: bool) -> bool:
    return bool(is_minimized or not is_visible or not is_active)


def _launch_detached_command(command: list[str]) -> bool:
    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, **popen_kwargs)
        return True
    except OSError:
        return False


def _toggle_window_maximize_restore(window) -> None:
    if sys.platform == "darwin":
        if window.isFullScreen():
            window.showNormal()
        else:
            window.showFullScreen()
        return
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


def _window_is_effectively_maximized(window) -> bool:
    if sys.platform == "darwin":
        return bool(window.isFullScreen())
    return bool(window.isMaximized())


WINDOW_FRAME_RADIUS = 8


def _apply_macos_native_window_corners(window, radius: int = WINDOW_FRAME_RADIUS) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        objc_path = ctypes.util.find_library("objc")
        appkit_path = ctypes.util.find_library("AppKit")
        quartzcore_path = ctypes.util.find_library("QuartzCore")
        if not objc_path or not appkit_path:
            return False

        ctypes.CDLL(appkit_path)
        if quartzcore_path:
            ctypes.CDLL(quartzcore_path)
        objc = ctypes.CDLL(objc_path)

        objc_getClass = objc.objc_getClass
        objc_getClass.restype = ctypes.c_void_p
        objc_getClass.argtypes = [ctypes.c_char_p]

        sel_registerName = objc.sel_registerName
        sel_registerName.restype = ctypes.c_void_p
        sel_registerName.argtypes = [ctypes.c_char_p]

        def cls(name: str) -> int:
            return int(objc_getClass(name.encode("utf-8")))

        def sel(name: str) -> int:
            return int(sel_registerName(name.encode("utf-8")))

        f_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_id = f_id(("objc_msgSend", objc))

        f_setbool = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)
        msg_setbool = f_setbool(("objc_msgSend", objc))

        f_setobj = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_setobj = f_setobj(("objc_msgSend", objc))

        f_setdouble = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double)
        msg_setdouble = f_setdouble(("objc_msgSend", objc))

        f_responds = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        msg_responds = f_responds(("objc_msgSend", objc))

        ns_view = int(window.winId())
        ns_window = msg_id(ns_view, sel("window"))
        if not ns_window:
            return False

        def responds(obj: int, selector_name: str) -> bool:
            return bool(obj and msg_responds(obj, sel("respondsToSelector:"), sel(selector_name)))

        ns_color_class = cls("NSColor")
        clear_color = msg_id(ns_color_class, sel("clearColor")) if ns_color_class else 0
        if clear_color and responds(ns_window, "setBackgroundColor:"):
            msg_setobj(ns_window, sel("setBackgroundColor:"), clear_color)
        if responds(ns_window, "setOpaque:"):
            msg_setbool(ns_window, sel("setOpaque:"), False)

        content_view = msg_id(ns_window, sel("contentView")) if responds(ns_window, "contentView") else 0
        for host_view in (content_view, ns_view):
            if not host_view:
                continue
            if not responds(host_view, "setWantsLayer:"):
                continue
            msg_setbool(host_view, sel("setWantsLayer:"), True)
            if not responds(host_view, "layer"):
                continue
            layer = msg_id(host_view, sel("layer"))
            if not layer:
                continue
            if responds(layer, "setCornerRadius:"):
                msg_setdouble(layer, sel("setCornerRadius:"), float(radius))
            if responds(layer, "setMasksToBounds:"):
                msg_setbool(layer, sel("setMasksToBounds:"), bool(radius > 0))

        return True
    except Exception:
        return False


def _apply_windows_native_window_corners(window) -> bool:
    if sys.platform != "win32":
        return False
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUNDSMALL = 3
        preference = ctypes.c_int(DWMWCP_ROUNDSMALL)
        hwnd = ctypes.c_void_p(int(window.winId()))
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            ctypes.c_int(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return int(result) == 0
    except Exception:
        return False


def _apply_window_corner_treatment(window, radius: int = WINDOW_FRAME_RADIUS) -> None:
    if _window_is_effectively_maximized(window):
        if sys.platform == "darwin":
            _apply_macos_native_window_corners(window, radius=0)
        if hasattr(window, "clearMask"):
            window.clearMask()
        return

    if _apply_macos_native_window_corners(window, radius=radius):
        if hasattr(window, "clearMask"):
            window.clearMask()
        return

    if _apply_windows_native_window_corners(window):
        if hasattr(window, "clearMask"):
            window.clearMask()
        return

    _apply_window_corner_mask(window, radius=radius)


def _apply_window_corner_mask(window, radius: int = WINDOW_FRAME_RADIUS) -> None:
    try:
        if _window_is_effectively_maximized(window):
            if hasattr(window, "clearMask"):
                window.clearMask()
            return

        rect = window.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPainterPath, QRegion

        rounded_rect = QRectF(rect.adjusted(0, 0, -1, -1))
        path = QPainterPath()
        path.addRoundedRect(rounded_rect, float(radius), float(radius))
        window.setMask(QRegion(path.toFillPolygon().toPolygon()))
    except Exception:
        return


def _install_window_corner_mask(window, radius: int = WINDOW_FRAME_RADIUS) -> None:
    try:
        from PyQt6.QtCore import QObject, QEvent

        class _RoundedWindowMaskFilter(QObject):
            def eventFilter(self, watched, event):
                if watched is window and event is not None and event.type() in (
                    QEvent.Type.Show,
                    QEvent.Type.Resize,
                    QEvent.Type.WindowStateChange,
                ):
                    _apply_window_corner_treatment(window, radius=radius)
                return False

        mask_filter = _RoundedWindowMaskFilter(window)
        window.installEventFilter(mask_filter)
        window._bettercode_window_mask_filter = mask_filter
        _apply_window_corner_treatment(window, radius=radius)
    except Exception:
        return


def _fallback_notification_command(title: str, message: str) -> list[str] | None:
    safe_title = title or APP_NAME
    safe_message = message or "A response is ready."
    if sys.platform == "darwin":
        osascript = shutil.which("osascript")
        if osascript:
            escaped_title = safe_title.replace("\\", "\\\\").replace('"', '\\"')
            escaped_message = safe_message.replace("\\", "\\\\").replace('"', '\\"')
            script = f'display notification "{escaped_message}" with title "{escaped_title}"'
            return [osascript, "-e", script]
        return None
    if sys.platform == "win32":
        powershell = shutil.which("powershell") or shutil.which("powershell.exe")
        if not powershell:
            return None
        ps_title = safe_title.replace("'", "''")
        ps_message = safe_message.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$notify = New-Object System.Windows.Forms.NotifyIcon; "
            "$notify.Icon = [System.Drawing.SystemIcons]::Information; "
            f"$notify.BalloonTipTitle = '{ps_title}'; "
            f"$notify.BalloonTipText = '{ps_message}'; "
            "$notify.Visible = $true; "
            "$notify.ShowBalloonTip(8000); "
            "Start-Sleep -Seconds 9; "
            "$notify.Dispose();"
        )
        return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    notify_send = shutil.which("notify-send")
    if notify_send:
        return [
            notify_send,
            "-a",
            APP_NAME,
            "-i",
            APP_SLUG,
            "-h",
            f"string:desktop-entry:{_linux_desktop_file_id()}",
            safe_title,
            safe_message,
        ]
    return None


def _send_completion_notification(tray_icon, title: str, message: str) -> bool:
    supports_messages = True
    if tray_icon is not None:
        supports = getattr(type(tray_icon), "supportsMessages", None)
        if callable(supports):
            try:
                supports_messages = bool(supports())
            except Exception:
                supports_messages = True
        if supports_messages:
            try:
                message_icon = getattr(getattr(tray_icon, "MessageIcon", None), "Information", 0)
                tray_icon.showMessage(
                    title or APP_NAME,
                    message or "A response is ready.",
                    message_icon,
                    8000,
                )
                return True
            except Exception:
                pass
    fallback_command = _fallback_notification_command(title, message)
    if not fallback_command:
        return False
    return _launch_detached_command(fallback_command)


def run_desktop_app(dev_mode: bool = False):
    _check_linux_qt_prereqs()
    _disable_chromium_feature("SkiaGraphite")
    _ensure_linux_desktop_entry()
    try:
        import setproctitle
        setproctitle.setproctitle(APP_NAME)
    except Exception:
        pass
    _start_selector_runtime_warmup()
    _prepare_webengine_spellcheck_environment()

    from PyQt6.QtCore import QObject, QUrl, pyqtSlot
    from PyQt6.QtGui import QDesktopServices, QIcon
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    qt_app = QApplication.instance() or QApplication(_qt_application_argv())
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationDisplayName(APP_NAME)
    qt_app.setOrganizationName(APP_NAME)
    if hasattr(qt_app, "setApplicationVersion"):
        from bettercode import __version__
        qt_app.setApplicationVersion(__version__)
    if sys.platform.startswith("linux") and hasattr(qt_app, "setDesktopFileName"):
        qt_app.setDesktopFileName(_linux_desktop_file_id())
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_BUNDLE_ID)
        except Exception:
            pass
    app_icon = None
    icon_path = _app_icon_path()
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        qt_app.setWindowIcon(app_icon)
    _set_macos_app_identity(APP_NAME)
    _set_macos_dock_icon(icon_path)
    directory_picker = DirectoryPicker(qt_app)
    save_file_picker = SaveFilePicker(qt_app)
    port = _find_free_port()
    app = create_app(dev_mode=dev_mode, directory_chooser=directory_picker.choose_directory)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = EmbeddedServer(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}/"
    _wait_for_server(base_url)

    from PyQt6.QtCore import Qt

    window = QMainWindow()
    window.setWindowTitle(APP_NAME)
    window.resize(1280, 840)
    if app_icon is not None:
        window.setWindowIcon(app_icon)

    # Frameless window on all platforms — BetterCode draws its own controls in the UI.
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    # Transparent window background so CSS border-radius produces visible rounded corners.
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    window.setStyleSheet("background: transparent;")

    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray_qicon = app_icon or qt_app.windowIcon()
        if sys.platform == "darwin" and APP_TRAY_ICON_PATH.exists():
            tray_qicon = QIcon(str(APP_TRAY_ICON_PATH))
            try:
                tray_qicon.setIsMask(True)
            except Exception:
                pass
        tray_icon = QSystemTrayIcon(tray_qicon, window)
        tray_icon.setToolTip(APP_NAME)
        tray_icon.activated.connect(lambda *_: (window.showNormal(), window.raise_(), window.activateWindow()))
        tray_icon.show()

    class DesktopBridge(QObject):
        def __init__(self, main_window, tray, save_picker):
            super().__init__()
            self._window = main_window
            self._tray = tray
            self._save_picker = save_picker
            self._drag_active = False
            self._drag_start_cursor = None
            self._drag_start_win_pos = None
            from PyQt6.QtCore import QTimer
            self._drag_timer = QTimer()
            self._drag_timer.setInterval(10)
            self._drag_timer.timeout.connect(self._poll_drag)

        def _poll_drag(self):
            if not self._drag_active:
                self._drag_timer.stop()
                return
            from PyQt6.QtGui import QCursor
            from PyQt6.QtCore import QPoint
            cur = QCursor.pos()
            delta = QPoint(cur.x() - self._drag_start_cursor.x(), cur.y() - self._drag_start_cursor.y())
            self._window.move(self._drag_start_win_pos + delta)

        @pyqtSlot(result=str)
        def getPlatform(self) -> str:
            if sys.platform == "darwin":
                return "macos"
            if sys.platform == "win32":
                return "windows"
            return "linux"

        @pyqtSlot()
        def minimizeWindow(self):
            self._window.showMinimized()

        @pyqtSlot()
        def maximizeRestoreWindow(self):
            _toggle_window_maximize_restore(self._window)

        @pyqtSlot(result=bool)
        def isWindowMaximized(self) -> bool:
            return _window_is_effectively_maximized(self._window)

        @pyqtSlot()
        def closeWindow(self):
            self._window.close()

        @pyqtSlot()
        def startWindowDrag(self):
            from PyQt6.QtGui import QCursor
            self._drag_active = True
            self._drag_start_cursor = QCursor.pos()
            self._drag_start_win_pos = self._window.pos()
            self._drag_timer.start()

        @pyqtSlot()
        def endWindowDrag(self):
            self._drag_active = False
            self._drag_timer.stop()

        @pyqtSlot(str, str)
        def notifyTurnComplete(self, title: str, message: str):
            if not _should_show_completion_notification(
                is_visible=self._window.isVisible(),
                is_minimized=self._window.isMinimized(),
                is_active=self._window.isActiveWindow(),
            ):
                return
            _send_completion_notification(self._tray, title, message)

        @pyqtSlot(str, str, result=str)
        def saveReviewReport(self, suggested_name: str, html: str) -> str:
            selected_path = self._save_picker.choose_html_file(suggested_name)
            if not selected_path:
                return ""
            try:
                return _write_html_report(selected_path, html)
            except OSError:
                return ""

        @pyqtSlot(str, result=bool)
        def openExternalUrl(self, url: str) -> bool:
            if not url:
                return False
            try:
                return bool(QDesktopServices.openUrl(QUrl(url)))
            except Exception:
                return False

    webview = QWebEngineView()
    webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    webview.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    webview.setStyleSheet("background: transparent; border: 0;")
    webview.page().setBackgroundColor(Qt.GlobalColor.transparent)
    _configure_webview_spellcheck(webview)
    channel = QWebChannel(webview.page())
    desktop_bridge = DesktopBridge(window, tray_icon, save_file_picker)
    channel.registerObject("bettercodeDesktopBridge", desktop_bridge)
    webview.page().setWebChannel(channel)
    webview.setUrl(QUrl(base_url))
    window.setCentralWidget(webview)
    _install_window_corner_mask(window)
    window._bettercode_tray_icon = tray_icon
    window._bettercode_webchannel = channel
    window._bettercode_desktop_bridge = desktop_bridge
    window.show()
    _set_macos_dock_icon(icon_path)
    _setup_macos_transparent_titlebar(window)

    try:
        qt_app.exec()
    finally:
        from bettercode.web.api import _kill_all_active_processes
        _kill_all_active_processes()
        server.should_exit = True
        server_thread.join(timeout=5)
        from bettercode.router.selector import stop_managed_ollama
        stop_managed_ollama()
