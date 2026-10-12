#!/usr/bin/env python3
"""Capture a screenshot or write its same-basename Markdown sidecar.

The native macOS Shortcut handles the multiline comment prompt. Its final shell
step passes the exact capture path, a newline, and the comment on stdin. Nothing
in a comment is evaluated as shell code. Uses only Python's standard library.
"""

import argparse
import ctypes
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional
from urllib.parse import quote

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


class ScreenshotError(Exception):
    pass


def capture_folder(folder: Optional[Path] = None) -> Path:
    """Use an override, the macOS screenshot location, or its Desktop default."""
    if folder is not None:
        return folder.expanduser()
    override = os.environ.get("SCREENSHOT_NOTE_FOLDER")
    if override:
        return Path(override).expanduser()
    try:
        proc = subprocess.run(
            ["/usr/bin/defaults", "read", "com.apple.screencapture", "location"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScreenshotError("Cannot read the macOS screenshot destination; use --folder") from error
    if proc.returncode == 1:
        # defaults exits 1 when this preference is not set (Desktop is default).
        return Path.home() / "Desktop"
    if proc.returncode:
        raise ScreenshotError("Cannot read the macOS screenshot destination; use --folder")
    location = proc.stdout.rstrip("\r\n")
    if not location:
        raise ScreenshotError("The macOS screenshot destination is empty; use --folder")
    result = Path(location).expanduser()
    if not result.is_absolute():
        raise ScreenshotError("The macOS screenshot destination is not an absolute path; use --folder")
    return result


def ensure_folder(folder: Path) -> Path:
    folder = folder.expanduser().absolute()
    if "\n" in str(folder) or "\r" in str(folder):
        raise ScreenshotError("Screenshot destination must not contain newlines")
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        raise ScreenshotError("Screenshot destination is not a directory")
    return folder


def is_png(image: Path) -> bool:
    if not image.is_file():
        return False
    with image.open("rb") as file:
        return file.read(len(PNG_HEADER)) == PNG_HEADER


def publish_image(source: Path, folder: Path, captured_at: datetime) -> Path:
    """Use exclusive creation, avoiding both PNG and MD filename collisions."""
    stem = captured_at.strftime("Screenshot %Y-%m-%d at %H.%M.%S")
    number = 1
    while True:
        suffix = "" if number == 1 else f"-{number}"
        image = folder / f"{stem}{suffix}.png"
        number += 1
        sidecar = image.with_suffix(".md")
        if sidecar.exists() or sidecar.is_symlink():
            continue
        try:
            out = image.open("xb")
        except FileExistsError:
            continue
        try:
            with out, source.open("rb") as incoming:
                shutil.copyfileobj(incoming, out)
        except BaseException:
            image.unlink(missing_ok=True)
            raise
        return image


def ensure_capture_access() -> None:
    """Check access without capturing, requesting, or changing permissions."""
    if sys.platform != "darwin":
        # Runtime capture is macOS-only; tests may mock it on other platforms.
        return
    try:
        graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        preflight = graphics.CGPreflightScreenCaptureAccess
        preflight.argtypes = []
        preflight.restype = ctypes.c_bool
        allowed = preflight()
    except (OSError, AttributeError) as error:
        raise ScreenshotError("Cannot check Screen Recording permission; no capture was started") from error
    if not allowed:
        raise ScreenshotError(
            "Screen Recording permission is missing for the app invoking this Shortcut. "
            "Open System Settings > Privacy & Security > Screen Recording and enable "
            "that app if you wish to grant access. When invoked from an app's Services "
            "menu or hotkey, macOS may require that app (not just Shortcuts). "
            "You may need to quit and reopen it. No screenshot was saved."
        )


def capture(folder: Path) -> Optional[Path]:
    """Return the captured path, or None when the user cancels/uses clipboard."""
    ensure_capture_access()
    folder = ensure_folder(folder)
    with tempfile.TemporaryDirectory(prefix="screenshot-note-") as staging:
        image = Path(staging) / "capture.png"
        proc = subprocess.run(
            ["/usr/sbin/screencapture", "-i", "-x", "-t", "png", str(image)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode and proc.stderr.strip():
            raise ScreenshotError("Screen capture failed: " + proc.stderr.strip())
        if not image.exists() or image.stat().st_size == 0:
            # Escape normally exits 1 without stderr; Control sends the image
            # to the clipboard instead. In either case, do not ask for a note.
            return None
        if proc.returncode or not is_png(image):
            raise ScreenshotError("Screen capture did not produce a valid PNG")
        return publish_image(image, folder, datetime.now().astimezone())


def parse_payload(payload: str):
    path, separator, note = payload.partition("\n")
    if not separator or not path:
        raise ScreenshotError("Expected the capture path followed by a newline and note")
    return Path(path.rstrip("\r")), note


def write_note(image: Path, note: str, folder: Optional[Path] = None) -> Path:
    """Create the sidecar beside this exact image, not a newly detected folder."""
    image = image.expanduser().absolute()
    folder = (folder if folder is not None else image.parent).expanduser().absolute()
    if image.resolve().parent != folder.resolve():
        raise ScreenshotError("The screenshot is outside the configured screenshots folder")
    if image.suffix.lower() != ".png" or not is_png(image):
        raise ScreenshotError("The selected screenshot is missing or is not a PNG")
    captured_at = datetime.fromtimestamp(image.stat().st_mtime).astimezone()
    title = captured_at.strftime("# Screenshot — %Y-%m-%d %H:%M:%S")
    # Angle brackets support spaces; escape characters that could terminate or
    # alter a Markdown link, including <, >, %, and non-ASCII filename bytes.
    target = quote(image.name, safe=" -_.()")
    note = note.replace("\r\n", "\n")
    body = title + "\n\n"
    if note:
        body += note + ("" if note.endswith("\n") else "\n") + "\n"
    body += f"![Screenshot](<{target}>)\n"
    sidecar = image.with_suffix(".md")
    try:
        out = sidecar.open("x", encoding="utf-8", newline="\n")
    except FileExistsError:
        raise ScreenshotError("A Markdown note already exists; it has not been overwritten")
    try:
        with out:
            out.write(body)
    except BaseException:
        sidecar.unlink(missing_ok=True)
        raise
    return sidecar


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    take = commands.add_parser("capture", help="Interactive capture; Escape cancels cleanly")
    take.add_argument("--folder", type=Path, help="Override the macOS screenshot destination")
    save = commands.add_parser("write-note", help="Write the matching Markdown file")
    save.add_argument("image", nargs="?", type=Path, help="Omit to read path + note from stdin")
    save.add_argument("--text", help="Note text when an image path is supplied")
    save.add_argument("--folder", type=Path, help="Optionally require the image to be in this folder")
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            result = capture(capture_folder(args.folder))
        elif args.image is not None:
            if args.text is None:
                raise ScreenshotError("Supply --text when providing an image path")
            result = write_note(args.image, args.text, args.folder)
        else:
            image, note = parse_payload(sys.stdin.read())
            result = write_note(image, note, args.folder)
        if result is not None:
            # No trailing newline: the Shortcut adds its own payload separator.
            sys.stdout.write(str(result))
        return 0
    except (ScreenshotError, OSError) as error:
        print(f"Screenshot with Note: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
