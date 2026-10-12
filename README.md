# Screenshot with Note

Capture an area or window, add a comment, and save a PNG with a matching Markdown
note. A macOS Shortcut provides the prompt; a small Python helper writes the
files. No screenshot library database, Python packages, or upload service is
required.

```text
Screenshot 2026-01-02 at 10.30.15.png
Screenshot 2026-01-02 at 10.30.15.md
```

The note contains a timestamp, the comment, and a relative image link. Moving
both files together preserves the link.

## Where the files go

By default, captures use the folder already configured for macOS screenshots
(**Shift–Command–5 → Options → Save to**). The helper reads the
`com.apple.screencapture` location preference without changing it. If no folder
preference is set, it uses the macOS default: `~/Desktop`.

Each Markdown note is saved **beside the exact image**, with the same basename.
The note writer does not search for the newest screenshot or re-read the current
save location. Changing that setting while the comment prompt is open will not
separate the note from its image.

Optional capture overrides, in order of precedence:

1. `capture --folder "/path/to/folder"`
2. The `SCREENSHOT_NOTE_FOLDER` environment variable
3. The macOS screenshot-folder preference
4. `~/Desktop`

For a Shortcut-specific override, edit its first shell action to:

```sh
"$HOME/.local/bin/screenshot-note" capture --folder "$HOME/Pictures/Captures"
```

An environment variable set in a terminal may not reach Shortcuts, so use the
explicit argument when configuring the GUI workflow.

This tool always saves a PNG file. Clipboard, Mail and other non-folder capture
targets are not destinations for Markdown notes. It does not monitor ordinary
screenshots taken outside this Shortcut.

## Install

Requires macOS with Shortcuts and Apple's Command Line Tools, including
`/usr/bin/python3` (Python 3.9 or newer). The workflow has been exercised on
macOS 14; Apple's workflow serialization can change between OS versions.

From a checkout:

```bash
./install.sh
mkdir -p build
/usr/bin/python3 build_shortcut.py "build/Screenshot with Note.unsigned.shortcut"
shortcuts sign --mode anyone \
  --input "build/Screenshot with Note.unsigned.shortcut" \
  --output "build/Screenshot with Note.shortcut"
open "build/Screenshot with Note.shortcut"
```

The installer copies the helper to `~/.local/share/screenshot-note/` and creates
`~/.local/bin/screenshot-note`. It does not change your PATH, screenshot settings,
keyboard bindings or macOS permissions. Re-run it after updating the source.
The installed helper does not depend on keeping the checkout at a particular
path, and does not require an AI assistant to be running.

In Shortcuts:

1. Import the workflow as **Screenshot with Note**.
2. Open **Details / ⓘ**, enable **Use as Quick Action → Services Menu**, and leave
   **Provide Output** unchecked. The files are the output; returning text to the
   invoking app can prevent the Service from running in some contexts.
3. Assign a keyboard shortcut. **Command–Option–Shift–4** preserves the normal
   screenshot keys and avoids Control's clipboard behaviour. macOS may display
   the shifted digit as `$`. Test the actual keypress in the apps you use; the
   display alone does not verify the binding, and applications can intercept
   shortcuts.
4. If required, enable **Shortcuts → Settings → Advanced → Allow Running
   Scripts** yourself. This is an app-wide permission, not permission for this
   one Shortcut. Handle any macOS screen-recording permission prompt yourself.

The helper checks Screen Recording access before starting capture; it does not
request or grant access. When invoked through an app's Services menu or hotkey,
macOS may attribute capture to **the invoking app**, rather than Shortcuts. If
it reports missing access, enable that app under **System Settings → Privacy &
Security → Screen Recording** only if you wish to grant it permission. Quit and
reopen the app if macOS requires it. Without access, macOS can otherwise save
only wallpaper while omitting application windows, even when capture appears
to succeed.

Signing makes the local workflow importable; it does not publish your screenshots
or comments. The repository excludes generated signed workflows because they
may contain signing metadata. Build yours locally.

Opening a rebuilt workflow with the same name may reopen the existing Shortcut
rather than update its actions. Check that its condition reads **If Shell Script
Result has any value**, not **If Input**. Preserve a working copy before replacing
an installed workflow.

The current workflow has seven actions. Inside the conditional, a **Text**
action converts the captured path to plain text **before Ask for Input**; the
later payload uses that Text result, not the original Shell Script Result.
This avoids re-reading Shortcuts' temporary shell-output file after a long-open
dialog. Updating the helper alone does not add this action: rebuild and update
the installed workflow too.

## Use

Invoke the Shortcut. Drag an area, or press Space to select a window. Release the
hotkey before finishing the selection. Enter your comment and confirm it.

- **Escape during capture:** no image or note; no comment prompt.
- **Cancel the comment:** keep the PNG, with no Markdown note.
- **Blank comment:** create a timestamp and image-link-only note.
- **Filename collision:** add `-2`, `-3`, etc.; do not overwrite existing files.
- **Comment text:** preserve multiline UTF-8 text without interpreting shell
  expressions, backticks or other content as code.
- **Note-writing failure:** report the error and leave the captured image intact.
- **Missing Screen Recording access:** report an error before capture; no
  screenshot or note is saved.

Holding Control during native capture can send the image to the clipboard. No
note is created if no image file was captured.

## Manual commands

```bash
"$HOME/.local/bin/screenshot-note" capture
"$HOME/.local/bin/screenshot-note" capture --folder "$HOME/Pictures/Captures"
"$HOME/.local/bin/screenshot-note" write-note \
  "$HOME/Pictures/Captures/Screenshot 2026-01-02 at 10.30.15.png" \
  --text "The selected row needs a clearer indicator."
```

`write-note` can also read the image path, a newline, and the comment from stdin;
this is how the Shortcut passes its values. Its optional `--folder` argument
checks that the image is in that folder; it does not relocate the note.

## Development and tests

```bash
/usr/bin/python3 -m unittest -v
/bin/sh -n install.sh
```

Tests mock capture instead of taking screenshots. They cover destination
preferences and overrides, cancellation, collisions, symlinks, UTF-8 and
multiline comments, relative image links, read-only permission preflight, and
the generated workflow wiring.
They do not replace a real keypress/capture/comment test on your macOS version.

`build_wiring_check.py` can generate a native Shortcuts regression check using a
synthetic PNG and known multiline text in a temporary folder. It does not capture
the screen, and substitutes text for the interactive prompt:

```bash
/usr/bin/python3 build_wiring_check.py "build/Screenshot Note Wiring Check.unsigned.shortcut"
shortcuts sign --mode anyone \
  --input "build/Screenshot Note Wiring Check.unsigned.shortcut" \
  --output "build/Screenshot Note Wiring Check.shortcut"
open "build/Screenshot Note Wiring Check.shortcut"
# After importing:
shortcuts run "Screenshot Note Wiring Check"
```

The builder prints the fixture folder. Check its PNG/Markdown pair and remove the
temporary Shortcut and fixture folder when finished. Use a distinct filename
and matching `--name` when retesting to avoid running an older installed check.

For a path-lifetime check, add `--delay 180` to pause after the path has been
materialised but before the synthetic note. Generate two checks with distinct
names and run them concurrently to exercise overlapping executions. Use
`--interactive` to retain the real multiline prompt with the synthetic image,
leave it open for at least three minutes, and submit a test comment. Neither
mode takes a screen capture. `--empty-capture` checks that the cancelled-capture
branch never reaches the note writer; `--comment ""` checks blank comments.

## Privacy

The helper reads the screenshot-folder preference and only writes the requested
capture and its note. It makes no network requests and records no comments in
logs. A folder already synced by iCloud, OneDrive, Dropbox or another service
continues to use that service; this tool adds no separate upload.

Keep personal images, notes, machine-specific backups and diagnostic records
outside version control. `local/`, `build/`, generated `.shortcut` files and
capture filenames are ignored by this repository.

## License

MIT. See [LICENSE](LICENSE).
