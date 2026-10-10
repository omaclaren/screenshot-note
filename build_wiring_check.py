#!/usr/bin/env python3
"""Generate a temporary native Shortcuts regression check (no real capture).

Import the signed result and run it with `shortcuts run`. This exercises the
same conditional/payload/shell-input wiring as the real shortcut, but uses a
synthetic PNG and a known multiline comment in /tmp. No screen or user notes
are read. The native Shortcut must be removed after testing.
"""

import argparse
import base64
from pathlib import Path
import plistlib
import shlex
import tempfile

from build_shortcut import build

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1sAAAAASUVORK5CYII="
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix="screenshot-note-wiring-"))
    image = folder / "Screenshot wiring check.png"
    image.write_bytes(PNG)
    workflow = build()
    workflow["WFWorkflowName"] = "Screenshot Note Wiring Check"
    workflow["WFWorkflowTypes"] = []
    workflow["WFQuickActionSurfaces"] = []
    capture, condition, ask, payload, save, end = workflow["WFWorkflowActions"]
    capture["WFWorkflowActionParameters"]["Script"] = "printf %s " + shlex.quote(str(image))
    ask_id = ask["WFWorkflowActionParameters"]["UUID"]
    ask["WFWorkflowActionIdentifier"] = "is.workflow.actions.gettext"
    ask["WFWorkflowActionParameters"] = {
        "UUID": ask_id,
        "WFTextActionText": "Native wiring check ✓\nSecond line preserved.",
    }
    payload["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["attachmentsByRange"]["{2, 1}"]["OutputName"] = "Text"
    save["WFWorkflowActionParameters"]["Script"] = (
        '"$HOME/.local/bin/screenshot-note" write-note --folder ' + shlex.quote(str(folder))
    )
    with args.output.open("wb") as file:
        plistlib.dump(workflow, file, fmt=plistlib.FMT_BINARY)
    print(folder)


if __name__ == "__main__":
    main()
