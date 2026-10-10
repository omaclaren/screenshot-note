#!/usr/bin/env python3
"""Build an importable native Shortcut using macOS's bundled action schema.

Sign the generated plist with `shortcuts sign` before importing it. The helper
is intentionally referenced through ~/.local/bin rather than an npm/venv path.
"""

import argparse
from pathlib import Path
import plistlib
import uuid

NAME = "Screenshot with Note"


def output(uuid_value, name):
    return {"Type": "ActionOutput", "OutputUUID": uuid_value, "OutputName": name}


def attachment(uuid_value, name):
    return {"WFSerializationType": "WFTextTokenAttachment", "Value": output(uuid_value, name)}


def action(identifier, parameters):
    return {"WFWorkflowActionIdentifier": identifier, "WFWorkflowActionParameters": parameters}


def build():
    info_path = Path("/System/Applications/Shortcuts.app/Contents/Info.plist")
    client_version = "2607.1.12"
    if info_path.exists():
        with info_path.open("rb") as file:
            client_version = plistlib.load(file)["CFBundleVersion"]
    capture_id, ask_id, text_id, group_id = (str(uuid.uuid4()).upper() for _ in range(4))
    shell = {"Shell": "/bin/zsh", "InputMode": "to stdin", "RunAsRoot": False}
    capture = action("is.workflow.actions.runshellscript", {
        **shell, "UUID": capture_id,
        "Script": '"$HOME/.local/bin/screenshot-note" capture',
    })
    condition = action("is.workflow.actions.conditional", {
        "GroupingIdentifier": group_id, "WFControlFlowMode": 0,
        "WFInput": {"Type": "Variable", "Variable": attachment(capture_id, "Shell Script Result")},
        "WFCondition": 100,  # Has Any Value; cancelled captures have no output.
    })
    ask = action("is.workflow.actions.ask", {
        "UUID": ask_id, "WFAskActionPrompt": "Note for this screenshot?",
        "WFInputType": "Text", "WFAskActionDefaultAnswer": "",
        "WFAllowsMultilineText": True,
    })
    payload = action("is.workflow.actions.gettext", {
        "UUID": text_id,
        "WFTextActionText": {
            "WFSerializationType": "WFTextTokenString",
            "Value": {
                "string": "\ufffc\n\ufffc",
                "attachmentsByRange": {
                    "{0, 1}": output(capture_id, "Shell Script Result"),
                    "{2, 1}": output(ask_id, "Provided Input"),
                },
            },
        },
    })
    save = action("is.workflow.actions.runshellscript", {
        **shell, "Script": '"$HOME/.local/bin/screenshot-note" write-note',
        "Input": attachment(text_id, "Text"),
    })
    end = action("is.workflow.actions.conditional", {
        "GroupingIdentifier": group_id, "WFControlFlowMode": 2,
    })
    return {
        "WFWorkflowName": NAME,
        "WFWorkflowClientVersion": client_version,
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59503},
        "WFWorkflowTypes": ["QuickActions"],
        "WFQuickActionSurfaces": ["ServicesMenu"],
        "WFWorkflowInputContentItemClasses": [],
        # Save files without returning text to the invoking app. Declaring a
        # text output can disable this Service when that app has no text
        # receiver (e.g. a browser page rather than an editable text field).
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowActions": [capture, condition, ask, payload, save, end],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as file:
        plistlib.dump(build(), file, fmt=plistlib.FMT_BINARY)
    print(args.output)


if __name__ == "__main__":
    main()
