#!/usr/bin/env python3
"""Generate a temporary native Shortcuts regression check (no real capture).

Import the signed result and run it with `shortcuts run`. This exercises the
production wiring using a synthetic PNG and known multiline text in /tmp.
Use --delay to test the captured path's lifetime, or --interactive to retain the
real multiline prompt. No screen or user notes are read. Remove the temporary
Shortcut and fixture folder after testing.
"""

import argparse
import base64
from pathlib import Path
import plistlib
import shlex
import tempfile

from build_shortcut import action, build

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1sAAAAASUVORK5CYII="
)
COMMENT = "Native wiring check ✓\nSecond line preserved."


def build_check(folder, name="Screenshot Note Wiring Check", delay=0,
                interactive=False, comment=COMMENT, empty_capture=False):
    if delay < 0:
        raise ValueError("Delay must not be negative")
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "Screenshot wiring check.png"
    image.write_bytes(PNG)
    workflow = build()
    workflow["WFWorkflowName"] = name
    workflow["WFWorkflowTypes"] = []
    workflow["WFQuickActionSurfaces"] = []
    capture, condition, path_text, ask, payload, save, end = workflow["WFWorkflowActions"]
    capture["WFWorkflowActionParameters"]["Script"] = (
        ":" if empty_capture else "printf %s " + shlex.quote(str(image))
    )
    if not interactive:
        ask_id = ask["WFWorkflowActionParameters"]["UUID"]
        ask["WFWorkflowActionIdentifier"] = "is.workflow.actions.gettext"
        ask["WFWorkflowActionParameters"] = {
            "UUID": ask_id,
            "WFTextActionText": comment,
        }
        payload["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["attachmentsByRange"]["{2, 1}"]["OutputName"] = "Text"
    if delay:
        # Wait after the early string conversion and before obtaining the note.
        workflow["WFWorkflowActions"].insert(3, action("is.workflow.actions.delay", {
            "WFDelayTime": delay,
        }))
    save["WFWorkflowActionParameters"]["Script"] = (
        '"$HOME/.local/bin/screenshot-note" write-note --folder ' + shlex.quote(str(folder))
    )
    return workflow, image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--name", default="Screenshot Note Wiring Check")
    parser.add_argument("--delay", type=int, default=0, help="Pause this many seconds before the note")
    parser.add_argument("--interactive", action="store_true", help="Keep the real multiline note prompt")
    parser.add_argument("--comment", default=COMMENT, help="Synthetic note when not interactive")
    parser.add_argument("--empty-capture", action="store_true", help="Exercise the cancelled-capture branch")
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must not be negative")
    folder = Path(tempfile.mkdtemp(prefix="screenshot-note-wiring-"))
    workflow, image = build_check(folder, args.name, args.delay, args.interactive,
                                  args.comment, args.empty_capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as file:
        plistlib.dump(workflow, file, fmt=plistlib.FMT_BINARY)
    print(image.parent)


if __name__ == "__main__":
    main()
