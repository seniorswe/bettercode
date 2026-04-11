import argparse
import json
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from bettercode import __version__
from bettercode.app_meta import APP_BUNDLE_ID, APP_ICON_PATH, APP_ICON_PNG_PATH, APP_NAME, APP_SLUG


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT_PATH = PROJECT_ROOT / "bettercode" / "main.py"
PACKAGING_ROOT = PROJECT_ROOT / "packaging"
DIST_ROOT = PROJECT_ROOT / "dist" / "desktop"
BUILD_ROOT = PROJECT_ROOT / "build" / "desktop"


def normalize_platform_name(platform_name: str | None = None) -> str:
    value = (platform_name or sys.platform).strip().lower()
    if value.startswith("darwin") or value.startswith("mac"):
        return "macos"
    if value.startswith("win"):
        return "windows"
    return "linux"


def _pyinstaller_data_sep(platform_name: str) -> str:
    return ";" if platform_name == "windows" else ":"


def platform_bundle_name(platform_name: str) -> str:
    if platform_name == "windows":
        return f"{APP_NAME}.exe"
    if platform_name == "macos":
        return f"{APP_NAME}.app"
    return APP_SLUG


def platform_dist_dir(platform_name: str) -> Path:
    return DIST_ROOT / platform_name


def platform_build_dir(platform_name: str) -> Path:
    return BUILD_ROOT / platform_name


def platform_icon_path(platform_name: str) -> Path | None:
    candidates = {
        "macos": [
            PACKAGING_ROOT / "assets" / "macos" / f"{APP_NAME}.icns",
            PACKAGING_ROOT / "assets" / "shared" / f"{APP_NAME}.icns",
        ],
        "windows": [
            PACKAGING_ROOT / "assets" / "windows" / f"{APP_NAME}.ico",
            PACKAGING_ROOT / "assets" / "shared" / f"{APP_NAME}.ico",
        ],
        "linux": [
            PACKAGING_ROOT / "assets" / "linux" / f"{APP_NAME}.png",
            PACKAGING_ROOT / "assets" / "shared" / f"{APP_NAME}.png",
            APP_ICON_PNG_PATH,
        ],
    }
    for path in candidates.get(platform_name, []):
        if path.exists():
            return path
    return None


def _qtwebengine_dictionaries_dir() -> Path | None:
    try:
        from PyQt6.QtCore import QLibraryInfo
    except Exception:
        return None

    library_path = getattr(QLibraryInfo, "LibraryPath", None)
    data_path_enum = getattr(library_path, "DataPath", None)
    if data_path_enum is None:
        library_location = getattr(QLibraryInfo, "LibraryLocation", None)
        data_path_enum = getattr(library_location, "DataPath", None)
    if data_path_enum is None:
        return None

    path_getter = getattr(QLibraryInfo, "path", None)
    if callable(path_getter):
        data_path = path_getter(data_path_enum)
    else:
        location_getter = getattr(QLibraryInfo, "location", None)
        if not callable(location_getter):
            return None
        data_path = location_getter(data_path_enum)
    if not data_path:
        return None

    candidate = Path(data_path).expanduser().resolve() / "qtwebengine_dictionaries"
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


def build_pyinstaller_command(platform_name: str | None = None) -> list[str]:
    normalized_platform = normalize_platform_name(platform_name)
    build_dir = platform_build_dir(normalized_platform)
    dist_dir = platform_dist_dir(normalized_platform)
    data_sep = _pyinstaller_data_sep(normalized_platform)
    command = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir / "work"),
        "--specpath",
        str(build_dir / "spec"),
        "--paths",
        str(PROJECT_ROOT),
        "--collect-submodules",
        "bettercode",
        "--collect-data",
        "bettercode",
        "--hidden-import",
        "PyQt6.QtWebEngineWidgets",
        "--hidden-import",
        "PyQt6.QtWebChannel",
    ]
    data_entries = [(APP_ICON_PATH, "bettercode/web/static")]
    dictionaries_dir = _qtwebengine_dictionaries_dir()
    if dictionaries_dir is not None:
        data_entries.append((dictionaries_dir, "qtwebengine_dictionaries"))
    for source, destination in data_entries:
        command.extend(["--add-data", f"{source}{data_sep}{destination}"])
    if normalized_platform == "macos":
        command.extend(["--osx-bundle-identifier", APP_BUNDLE_ID])
    icon_path = platform_icon_path(normalized_platform)
    if icon_path is not None:
        command.extend(["--icon", str(icon_path)])
    command.append(str(ENTRYPOINT_PATH))
    return command


def build_plan_payload(platform_name: str | None = None) -> dict:
    normalized_platform = normalize_platform_name(platform_name)
    return {
        "platform": normalized_platform,
        "entrypoint": str(ENTRYPOINT_PATH),
        "dist_dir": str(platform_dist_dir(normalized_platform)),
        "build_dir": str(platform_build_dir(normalized_platform)),
        "bundle_name": platform_bundle_name(normalized_platform),
        "bundle_id": APP_BUNDLE_ID,
        "version": __version__,
        "icon_path": str(platform_icon_path(normalized_platform) or ""),
        "command": build_pyinstaller_command(normalized_platform),
    }


def write_build_plan(platform_name: str | None = None) -> Path:
    plan = build_plan_payload(platform_name)
    build_dir = Path(plan["build_dir"])
    build_dir.mkdir(parents=True, exist_ok=True)
    plan_path = build_dir / "build-plan.json"
    plan_path.write_text(json.dumps({
        **plan,
        "generated_at": datetime.now(UTC).isoformat(),
    }, indent=2, sort_keys=True), encoding="utf-8")
    return plan_path


def packaging_validation_payload(platform_name: str | None = None) -> dict:
    normalized_platform = normalize_platform_name(platform_name)
    icon_path = platform_icon_path(normalized_platform)
    checks = [
        {
            "name": "entrypoint",
            "ok": ENTRYPOINT_PATH.exists(),
            "detail": str(ENTRYPOINT_PATH),
        },
        {
            "name": "svg_app_icon",
            "ok": APP_ICON_PATH.exists(),
            "detail": str(APP_ICON_PATH),
        },
        {
            "name": "native_platform_icon",
            "ok": icon_path is not None,
            "detail": str(icon_path) if icon_path is not None else f"Missing native icon asset for {normalized_platform}",
        },
        {
            "name": "pyinstaller",
            "ok": shutil.which("pyinstaller") is not None,
            "detail": shutil.which("pyinstaller") or "PyInstaller not installed",
        },
    ]
    return {
        "platform": normalized_platform,
        "ready": all(check["ok"] for check in checks if check["name"] != "native_platform_icon"),
        "checks": checks,
    }


def write_release_manifest(platform_name: str | None = None) -> Path:
    plan = build_plan_payload(platform_name)
    build_dir = Path(plan["build_dir"])
    build_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = build_dir / "release-manifest.json"
    manifest = {
        "app_name": APP_NAME,
        "slug": APP_SLUG,
        "bundle_id": APP_BUNDLE_ID,
        "platform": plan["platform"],
        "bundle_name": plan["bundle_name"],
        "version": __version__,
        "entrypoint": plan["entrypoint"],
        "icon_path": plan["icon_path"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def package_desktop(platform_name: str | None = None, dry_run: bool = False) -> dict:
    plan = build_plan_payload(platform_name)
    plan_path = write_build_plan(plan["platform"])
    manifest_path = write_release_manifest(plan["platform"])
    validation = packaging_validation_payload(plan["platform"])
    if dry_run:
        return {
            **plan,
            "plan_path": str(plan_path),
            "manifest_path": str(manifest_path),
            "validation": validation,
            "built": False,
        }

    if not validation["ready"]:
        raise RuntimeError("Packaging validation failed. Run `bettercode-package --validate` for details.")

    pyinstaller_path = shutil.which("pyinstaller")
    if not pyinstaller_path:
        raise RuntimeError(
            "PyInstaller is not installed. Install packaging extras with `pip install -e .[packaging]`."
        )

    command = list(plan["command"])
    command[0] = pyinstaller_path
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return {
        **plan,
        "plan_path": str(plan_path),
        "manifest_path": str(manifest_path),
        "validation": validation,
        "built": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bettercode-package")
    parser.add_argument(
        "--platform",
        choices=["macos", "windows", "linux"],
        default=None,
        help="Target platform. Defaults to the current OS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only write the build plan and print the PyInstaller command.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Only run packaging validation checks and print the result.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.validate:
        payload = packaging_validation_payload(args.platform)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ready"] else 1
    payload = package_desktop(args.platform, dry_run=args.dry_run)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.dry_run:
        print("\nCommand:")
        print(" ".join(shlex.quote(part) for part in payload["command"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
