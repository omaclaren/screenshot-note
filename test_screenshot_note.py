import base64
from datetime import datetime
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_shortcut
import build_wiring_check
import screenshot_note as app

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1sAAAAASUVORK5CYII="
)
WHEN = datetime(2026, 10, 9, 11, 12, 13)


class ScreenshotNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "Screenshots with spaces"
        self.folder.mkdir()
        self.image = self.folder / "Screenshot 2026-10-09 at 11.12.13.png"
        self.image.write_bytes(PNG)

    def test_explicit_capture_folder_takes_precedence(self):
        with patch.dict(os.environ, {"SCREENSHOT_NOTE_FOLDER": "/unused"}), patch("screenshot_note.subprocess.run") as run:
            self.assertEqual(app.capture_folder(self.folder), self.folder)
        run.assert_not_called()

    def test_environment_capture_folder_takes_precedence(self):
        with patch.dict(os.environ, {"SCREENSHOT_NOTE_FOLDER": str(self.folder)}), patch("screenshot_note.subprocess.run") as run:
            self.assertEqual(app.capture_folder(), self.folder)
        run.assert_not_called()

    def test_capture_folder_reads_macos_preference(self):
        result = subprocess.CompletedProcess([], 0, str(self.folder) + "\n", "")
        with patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", return_value=result) as run:
            self.assertEqual(app.capture_folder(), self.folder)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/defaults", "read", "com.apple.screencapture", "location"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_capture_folder_expands_tilde(self):
        result = subprocess.CompletedProcess([], 0, "~/Pictures/Captures\n", "")
        with patch.dict(os.environ, {"SCREENSHOT_NOTE_FOLDER": ""}), patch("screenshot_note.subprocess.run", return_value=result):
            self.assertEqual(app.capture_folder(), Path.home() / "Pictures/Captures")

    def test_capture_folder_preserves_filename_spaces(self):
        result = subprocess.CompletedProcess([], 0, str(self.folder) + " \n", "")
        with patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", return_value=result):
            self.assertEqual(app.capture_folder(), Path(str(self.folder) + " "))

    def test_unset_screenshot_preference_uses_desktop(self):
        result = subprocess.CompletedProcess([], 1, "", "Preference is not set")
        with patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", return_value=result), patch("screenshot_note.Path.home", return_value=Path(self.temp.name)):
            self.assertEqual(app.capture_folder(), Path(self.temp.name) / "Desktop")

    def test_unexpected_preference_exit_is_not_treated_as_unset(self):
        result = subprocess.CompletedProcess([], 2, "", "Preference read failed")
        with patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", return_value=result):
            with self.assertRaises(app.ScreenshotError):
                app.capture_folder()

    def test_empty_or_relative_screenshot_preference_is_rejected(self):
        for value in ("\n", "relative/folder\n"):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", return_value=subprocess.CompletedProcess([], 0, value, "")):
                with self.assertRaises(app.ScreenshotError):
                    app.capture_folder()

    def test_preference_read_errors_do_not_silently_switch_folders(self):
        for error in (OSError("unavailable"), subprocess.TimeoutExpired("defaults", 5)):
            with self.subTest(error=error), patch.dict(os.environ, {}, clear=True), patch("screenshot_note.subprocess.run", side_effect=error):
                with self.assertRaises(app.ScreenshotError):
                    app.capture_folder()

    def test_newline_destination_is_rejected_before_creation(self):
        folder = Path(self.temp.name) / "bad\nfolder"
        with self.assertRaises(app.ScreenshotError):
            app.ensure_folder(folder)
        self.assertFalse(folder.exists())

    def test_cli_capture_uses_detected_destination(self):
        with patch("screenshot_note.capture_folder", return_value=self.folder), patch("screenshot_note.capture", return_value=None) as capture:
            self.assertEqual(app.main(["capture"]), 0)
        capture.assert_called_once_with(self.folder)

    def test_note_uses_image_parent_without_rereading_preferences(self):
        with patch("screenshot_note.capture_folder", side_effect=AssertionError("Must not redetect destination")), patch("sys.stdin", io.StringIO(str(self.image) + "\nNext to this image")), patch("sys.stdout", io.StringIO()):
            self.assertEqual(app.main(["write-note"]), 0)
        self.assertIn("Next to this image", self.image.with_suffix(".md").read_text())

    def test_note_follows_image_even_when_override_has_changed(self):
        with patch.dict(os.environ, {"SCREENSHOT_NOTE_FOLDER": "/different/location"}):
            sidecar = app.write_note(self.image, "Keep together")
        self.assertEqual(sidecar.parent, self.image.parent)

    def test_same_basename_and_relative_image(self):
        note = app.write_note(self.image, "Use a checkmark for the selected row.", self.folder)
        self.assertEqual(note, self.image.with_suffix(".md"))
        text = note.read_text()
        self.assertIn("Use a checkmark", text)
        self.assertIn(f"![Screenshot](<{self.image.name}>)", text)
        self.assertNotIn(str(self.folder), text)
        self.assertEqual(self.image.read_bytes(), PNG)

    def test_multiline_unicode_and_shell_text_are_literal(self):
        marker = Path(self.temp.name) / "must-not-exist"
        comment = f"First line: Māori — ✓\n\n  - Preserve indentation\n$(touch '{marker}')\n`rm -rf /`"
        note = app.write_note(self.image, comment, self.folder)
        self.assertIn(comment, note.read_text(encoding="utf-8"))
        self.assertFalse(marker.exists())

    def test_blank_note_still_links_image(self):
        text = app.write_note(self.image, "", self.folder).read_text()
        self.assertTrue(text.startswith("# Screenshot — "))
        self.assertIn("![Screenshot]", text)

    def test_windows_newlines_normalized(self):
        text = app.write_note(self.image, "One\r\nTwo", self.folder).read_text()
        self.assertIn("One\nTwo", text)

    def test_existing_note_is_not_overwritten(self):
        sidecar = self.image.with_suffix(".md")
        sidecar.write_text("Existing note")
        with self.assertRaises(app.ScreenshotError):
            app.write_note(self.image, "Replacement", self.folder)
        self.assertEqual(sidecar.read_text(), "Existing note")

    def test_missing_or_invalid_image_creates_no_sidecar(self):
        self.image.unlink()
        with self.assertRaises(app.ScreenshotError):
            app.write_note(self.image, "Note", self.folder)
        self.image.write_text("Not an image")
        with self.assertRaises(app.ScreenshotError):
            app.write_note(self.image, "Note", self.folder)
        self.assertFalse(self.image.with_suffix(".md").exists())

    def test_image_outside_folder_is_rejected(self):
        other = Path(self.temp.name) / "outside.png"
        other.write_bytes(PNG)
        with self.assertRaises(app.ScreenshotError):
            app.write_note(other, "Note", self.folder)
        self.assertFalse(other.with_suffix(".md").exists())

    def test_symlinked_screenshot_folder(self):
        link = Path(self.temp.name) / "screenshots"
        link.symlink_to(self.folder, target_is_directory=True)
        sidecar = app.write_note(link / self.image.name, "Through the symlink", link)
        self.assertEqual(sidecar.parent, link)
        self.assertTrue(self.image.with_suffix(".md").exists())

    def test_link_escapes_angle_brackets_and_percent(self):
        renamed = self.folder / "UI <test> 100%.png"
        renamed.write_bytes(PNG)
        text = app.write_note(renamed, "Note", self.folder).read_text()
        self.assertIn("<UI %3Ctest%3E 100%25.png>", text)

    def test_publish_avoids_png_and_md_collisions(self):
        source = Path(self.temp.name) / "source.png"
        source.write_bytes(PNG)
        (self.folder / "Screenshot 2026-10-09 at 11.12.13-2.md").write_text("Orphan note")
        result = app.publish_image(source, self.folder, WHEN)
        self.assertEqual(result.name, "Screenshot 2026-10-09 at 11.12.13-3.png")
        self.assertEqual(result.read_bytes(), PNG)
        self.assertEqual(self.image.read_bytes(), PNG)

    def test_publish_avoids_dangling_sidecar_symlinks(self):
        source = Path(self.temp.name) / "source.png"
        source.write_bytes(PNG)
        link = self.folder / "Screenshot 2026-10-09 at 11.12.13-2.md"
        link.symlink_to(self.folder / "missing-note.md")
        result = app.publish_image(source, self.folder, WHEN)
        self.assertEqual(result.name, "Screenshot 2026-10-09 at 11.12.13-3.png")
        self.assertTrue(link.is_symlink())

    def test_payload_keeps_multiline_comment_and_exact_path(self):
        image, note = app.parse_payload(str(self.image) + "\nLine one\nLine two\n")
        self.assertEqual(image, self.image)
        self.assertEqual(note, "Line one\nLine two\n")

    def test_invalid_payload_is_rejected(self):
        for payload in ("", "only a path", "\nComment"):
            with self.subTest(payload=payload), self.assertRaises(app.ScreenshotError):
                app.parse_payload(payload)

    def test_cli_stdin_writes_note(self):
        with patch("sys.stdin", io.StringIO(str(self.image) + "\nFrom Shortcut")), patch("sys.stdout", io.StringIO()) as out:
            result = app.main(["write-note", "--folder", str(self.folder)])
        self.assertEqual(result, 0)
        self.assertEqual(out.getvalue(), str(self.image.with_suffix(".md")))

    def test_cancel_creates_nothing(self):
        destination = Path(self.temp.name) / "cancelled"
        with patch("screenshot_note.ensure_capture_access"), patch("screenshot_note.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            self.assertIsNone(app.capture(destination))
        self.assertEqual(list(destination.iterdir()), [])

    def test_successful_capture_publishes_only_one_png(self):
        destination = Path(self.temp.name) / "captured"
        def fake_capture(args, **kwargs):
            self.assertEqual(args[:5], ["/usr/sbin/screencapture", "-i", "-x", "-t", "png"])
            Path(args[-1]).write_bytes(PNG)
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("screenshot_note.ensure_capture_access"), patch("screenshot_note.subprocess.run", side_effect=fake_capture):
            result = app.capture(destination)
        self.assertEqual(list(destination.iterdir()), [result])
        self.assertEqual(result.read_bytes(), PNG)

    def test_permission_error_is_not_mistaken_for_cancel(self):
        destination = Path(self.temp.name) / "denied"
        result = subprocess.CompletedProcess([], 1, "", "could not create image from display")
        with patch("screenshot_note.ensure_capture_access"), patch("screenshot_note.subprocess.run", return_value=result), self.assertRaises(app.ScreenshotError):
            app.capture(destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_service_does_not_require_application_output_receiver(self):
        workflow = build_shortcut.build()
        self.assertEqual(workflow["WFWorkflowOutputContentItemClasses"], [])
        self.assertIn("ServicesMenu", workflow["WFQuickActionSurfaces"])

    def test_native_shortcut_uses_exact_capture_and_multiline_input(self):
        workflow = build_shortcut.build()
        capture, condition, path_text, ask, payload, save, end = [a["WFWorkflowActionParameters"] for a in workflow["WFWorkflowActions"]]
        self.assertEqual(condition["WFCondition"], 100)
        # Conditional subjects need a picker-state wrapper; a bare token
        # imports as an unbound "Input" selector on macOS 14. Shell inputs
        # are different: the native input-probe test confirms bare tokens.
        self.assertEqual(condition["WFInput"]["Type"], "Variable")
        self.assertEqual(condition["WFInput"]["Variable"]["Value"]["OutputUUID"], capture["UUID"])
        self.assertTrue(ask["WFAllowsMultilineText"])
        snapshot = path_text["WFTextActionText"]["Value"]
        self.assertEqual(snapshot["string"], "\ufffc")
        self.assertEqual(snapshot["attachmentsByRange"]["{0, 1}"]["OutputUUID"], capture["UUID"])
        value = payload["WFTextActionText"]["Value"]
        self.assertEqual(value["string"], "\ufffc\n\ufffc")
        self.assertEqual(value["attachmentsByRange"]["{0, 1}"]["OutputUUID"], path_text["UUID"])
        self.assertEqual(value["attachmentsByRange"]["{0, 1}"]["OutputName"], "Text")
        self.assertEqual(value["attachmentsByRange"]["{2, 1}"]["OutputUUID"], ask["UUID"])
        self.assertEqual(save["Input"]["WFSerializationType"], "WFTextTokenAttachment")
        self.assertEqual(save["Input"]["Value"]["OutputUUID"], payload["UUID"])
        self.assertEqual(end["GroupingIdentifier"], condition["GroupingIdentifier"])
        self.assertFalse(save["RunAsRoot"])

    def test_no_shell_output_reference_survives_past_prompt(self):
        actions = build_shortcut.build()["WFWorkflowActions"]
        capture_id = actions[0]["WFWorkflowActionParameters"]["UUID"]
        ask_index = next(i for i, action in enumerate(actions) if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.ask")
        def references(value):
            if isinstance(value, dict):
                if value.get("Type") == "ActionOutput":
                    yield value.get("OutputUUID")
                for child in value.values():
                    yield from references(child)
            elif isinstance(value, list):
                for child in value:
                    yield from references(child)
        self.assertNotIn(capture_id, list(references(actions[ask_index:])))
        self.assertEqual(actions[ask_index - 1]["WFWorkflowActionIdentifier"], "is.workflow.actions.gettext")

    def test_delayed_native_check_uses_production_path_snapshot(self):
        workflow, image = build_wiring_check.build_check(self.folder / "native fixture", delay=180)
        actions = workflow["WFWorkflowActions"]
        self.assertEqual(image.read_bytes(), build_wiring_check.PNG)
        self.assertEqual(actions[2]["WFWorkflowActionIdentifier"], "is.workflow.actions.gettext")
        self.assertEqual(actions[3]["WFWorkflowActionIdentifier"], "is.workflow.actions.delay")
        self.assertEqual(actions[3]["WFWorkflowActionParameters"]["WFDelayTime"], 180)
        path_id = actions[2]["WFWorkflowActionParameters"]["UUID"]
        value = actions[5]["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]
        self.assertEqual(value["attachmentsByRange"]["{0, 1}"]["OutputUUID"], path_id)
        self.assertEqual(value["attachmentsByRange"]["{2, 1}"]["OutputName"], "Text")
        self.assertEqual(actions[4]["WFWorkflowActionParameters"]["WFTextActionText"], build_wiring_check.COMMENT)
        self.assertEqual(workflow["WFWorkflowTypes"], [])
        self.assertEqual(workflow["WFQuickActionSurfaces"], [])

    def test_native_check_can_retain_real_multiline_prompt(self):
        workflow, _ = build_wiring_check.build_check(self.folder / "interactive fixture", interactive=True)
        ask = workflow["WFWorkflowActions"][3]
        self.assertEqual(ask["WFWorkflowActionIdentifier"], "is.workflow.actions.ask")
        self.assertTrue(ask["WFWorkflowActionParameters"]["WFAllowsMultilineText"])

    def test_native_check_blank_note_and_empty_capture(self):
        workflow, _ = build_wiring_check.build_check(self.folder / "empty fixture", comment="", empty_capture=True)
        actions = workflow["WFWorkflowActions"]
        self.assertEqual(actions[0]["WFWorkflowActionParameters"]["Script"], ":")
        self.assertEqual(actions[3]["WFWorkflowActionParameters"]["WFTextActionText"], "")

    def test_native_check_rejects_negative_delay(self):
        with self.assertRaises(ValueError):
            build_wiring_check.build_check(self.folder / "invalid fixture", delay=-1)
        self.assertFalse((self.folder / "invalid fixture").exists())


class CapturePermissionTests(unittest.TestCase):
    def test_allowed_access_uses_read_only_preflight(self):
        with patch("screenshot_note.sys.platform", "darwin"), patch("screenshot_note.ctypes.CDLL") as load:
            preflight = load.return_value.CGPreflightScreenCaptureAccess
            preflight.return_value = True
            app.ensure_capture_access()
            preflight.assert_called_once_with()
            self.assertEqual(preflight.argtypes, [])
            self.assertEqual(preflight.restype, app.ctypes.c_bool)
            load.assert_called_once_with("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

    def test_denied_access_reports_invoking_app_and_saves_nothing(self):
        with patch("screenshot_note.sys.platform", "darwin"), patch("screenshot_note.ctypes.CDLL") as load:
            load.return_value.CGPreflightScreenCaptureAccess.return_value = False
            with self.assertRaisesRegex(app.ScreenshotError, "app invoking this Shortcut") as caught:
                app.ensure_capture_access()
            self.assertIn("No screenshot was saved", str(caught.exception))
            self.assertIn("not just Shortcuts", str(caught.exception))

    def test_unavailable_preflight_fails_closed(self):
        for error in (OSError("unavailable"), AttributeError("missing API")):
            with self.subTest(error=error), patch("screenshot_note.sys.platform", "darwin"), patch("screenshot_note.ctypes.CDLL", side_effect=error):
                with self.assertRaisesRegex(app.ScreenshotError, "no capture was started"):
                    app.ensure_capture_access()

    def test_non_macos_test_runtime_does_not_load_framework(self):
        with patch("screenshot_note.sys.platform", "linux"), patch("screenshot_note.ctypes.CDLL") as load:
            app.ensure_capture_access()
            load.assert_not_called()

    def test_denied_access_precedes_directory_creation_and_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "must not be created"
            with patch("screenshot_note.ensure_capture_access", side_effect=app.ScreenshotError("permission missing")), patch("screenshot_note.subprocess.run") as run:
                with self.assertRaisesRegex(app.ScreenshotError, "permission missing"):
                    app.capture(destination)
            run.assert_not_called()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
