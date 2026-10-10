#!/bin/sh
# Install a stable runtime copy; no shell profiles or macOS preferences change.
set -eu

if [ "$(uname -s)" != Darwin ]; then
    printf '%s\n' 'Screenshot with Note requires macOS.' >&2
    exit 1
fi
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
    printf '%s\n' 'Install the Apple Command Line Tools before running this installer.' >&2
    exit 1
fi
/usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else "Python 3.9 or newer is required")'

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_dir="$HOME/.local/share/screenshot-note"
bin_dir="$HOME/.local/bin"
mkdir -p "$data_dir" "$bin_dir"

cp "$source_dir/screenshot_note.py" "$data_dir/screenshot_note.py.tmp"
chmod 644 "$data_dir/screenshot_note.py.tmp"
mv "$data_dir/screenshot_note.py.tmp" "$data_dir/screenshot_note.py"

cat > "$bin_dir/screenshot-note.tmp" <<'LAUNCHER'
#!/bin/sh
export PYTHONUTF8=1
exec /usr/bin/python3 "$HOME/.local/share/screenshot-note/screenshot_note.py" "$@"
LAUNCHER
chmod 755 "$bin_dir/screenshot-note.tmp"
mv "$bin_dir/screenshot-note.tmp" "$bin_dir/screenshot-note"

printf 'Installed helper: %s\nInstalled launcher: %s\n' "$data_dir/screenshot_note.py" "$bin_dir/screenshot-note"
printf '%s\n' 'Next: build and import the Shortcut, then assign its keyboard shortcut in Shortcuts.'
