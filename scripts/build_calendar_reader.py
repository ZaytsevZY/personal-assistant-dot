"""Build an owner-only ad-hoc signed app. Does not launch or request access."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "Personal Assistant Calendar Reader"
APP_ID = "org.personalassistantdot.calendarreader"
SOURCES = ("scripts/calendar_bridge.swift", "native/calendar-reader/main.swift")


def default_directory():
    return Path("/Users") / "Shared" / ("PersonalAssistantDot-" + str(os.getuid()))


def source_hashes(project=ROOT):
    return {path: hashlib.sha256((Path(project) / path).read_bytes()).hexdigest() for path in SOURCES}


def build(output):
    if sys.platform != "darwin":
        raise RuntimeError("calendar app requires macOS")
    target = Path(output).expanduser()
    if target.name != APP_NAME + ".app" or target.is_symlink() or target.exists():
        raise RuntimeError("expected a new named app; existing apps are never overwritten")
    parent = target.parent
    if (parent.is_symlink() or not parent.is_dir() or parent.resolve() != parent.absolute()
            or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077):
        raise RuntimeError("app parent must be an existing owned real directory")
    if target.resolve().is_relative_to(ROOT) or any((p / ".git").exists() for p in [parent, *parent.parents]):
        raise RuntimeError("compiled apps must remain outside Git worktrees")
    receipt_path = parent / (APP_NAME + ".receipt.json")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise RuntimeError("existing receipt will not be overwritten")
    sources = source_hashes()
    with tempfile.TemporaryDirectory(prefix="calendar-reader-build-", dir=parent) as directory:
        workspace = Path(directory)
        bundle = workspace / target.name
        binary = bundle / "Contents/MacOS/CalendarReader"
        binary.parent.mkdir(parents=True, mode=0o700)
        resources = bundle / "Contents/Resources"
        resources.mkdir(mode=0o700)
        info = {"CFBundleIdentifier": APP_ID, "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
                "CFBundleExecutable": "CalendarReader", "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
                "CFBundleShortVersionString": "0.8.0", "LSMinimumSystemVersion": "14.0", "LSUIElement": True,
                "NSCalendarsFullAccessUsageDescription": "读取你明确选择的日历以核对安排。项目代码不包含新增、修改或删除日程功能；macOS 的完整访问权限本身包含读写能力。"}
        (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
        (resources / "source-manifest.json").write_text(json.dumps({"bundle_id": APP_ID, "sources": sources}, indent=2) + "\n")
        subprocess.run(["/usr/bin/xcrun", "swiftc", "-module-cache-path", str(workspace / "modules"),
                        "-framework", "AppKit", "-framework", "EventKit", *[str(ROOT / path) for path in SOURCES],
                        "-o", str(binary)], check=True, timeout=60, capture_output=True)
        if source_hashes() != sources:
            raise RuntimeError("sources changed during build; nothing installed")
        for path in [bundle, *bundle.rglob("*")]:
            path.chmod(0o700 if path.is_dir() or path == binary else 0o600)
        subprocess.run(["/usr/bin/codesign", "--sign", "-", "--identifier", APP_ID, "--timestamp=none", str(bundle)],
                       check=True, timeout=20, capture_output=True)
        for path in [bundle, *bundle.rglob("*")]:
            path.chmod(0o700 if path.is_dir() or path == binary else 0o600)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(bundle)], check=True, timeout=10, capture_output=True)
        receipt = {"schema_version": 1, "bundle_id": APP_ID, "sources": sources,
                   "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "signing": "local_ad_hoc"}
        # The app is complete and verified before it becomes the installed target.
        os.rename(bundle, target)
        descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        # Normal application discovery only; no TCC or Gatekeeper changes.
        subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister",
                        "-f", str(target)], check=True, timeout=10, capture_output=True)
    return {"status": "built", "bundle_id": APP_ID, "app_name": APP_NAME, "requested_access": False,
            "signing": "local_ad_hoc", "source_sha256": sources}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(default_directory() / (APP_NAME + ".app")))
    args = parser.parse_args()
    try:
        # Only the default, dedicated owner-only directory may be created.
        # Custom locations must already exist and pass build's checks.
        if Path(args.output) == default_directory() / (APP_NAME + ".app"):
            default_directory().mkdir(mode=0o700, exist_ok=True)
        print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({"status": "build_failed", "error_type": type(error).__name__, "requested_access": False}))
        sys.exit(2)
