#!/usr/bin/env python3
"""Offline safety checks. No network calls and no UniFi writes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from unifi_common import Settings, UniFiError, minimal_payload  # noqa: E402
import unifi_wifi_apply  # noqa: E402


class SafetyTests(unittest.TestCase):
    def test_minimal_off_payload(self) -> None:
        self.assertEqual(
            minimal_payload("example-id", False),
            {"_id": "example-id", "enabled": False},
        )

    def test_minimal_on_payload(self) -> None:
        self.assertEqual(
            minimal_payload("example-id", True),
            {"_id": "example-id", "enabled": True},
        )

    def test_empty_wlan_id_is_rejected(self) -> None:
        with self.assertRaises(UniFiError):
            minimal_payload("", True)

    def test_writer_is_locked_when_marker_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                base_url="https://example.invalid",
                site="default",
                wlan_id="example-id",
                credentials_file=Path(directory) / "credentials.json",
                pinned_public_key_file=Path(directory) / "pin",
                backup_directory=Path(directory) / "backups",
                write_marker_file=Path(directory) / "missing-marker",
            )
            self.assertFalse(unifi_wifi_apply.write_is_enabled(settings))

    def test_wrong_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            marker.write_text("wrong-value\n", encoding="utf-8")
            settings = Settings(
                base_url="https://example.invalid",
                site="default",
                wlan_id="example-id",
                credentials_file=Path(directory) / "credentials.json",
                pinned_public_key_file=Path(directory) / "pin",
                backup_directory=Path(directory) / "backups",
                write_marker_file=marker,
            )
            self.assertFalse(unifi_wifi_apply.write_is_enabled(settings))

    def test_exact_private_marker_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            marker.write_text("private-test-value\n", encoding="utf-8")
            settings = Settings(
                base_url="https://example.invalid",
                site="default",
                wlan_id="example-id",
                credentials_file=Path(directory) / "credentials.json",
                pinned_public_key_file=Path(directory) / "pin",
                backup_directory=Path(directory) / "backups",
                write_marker_file=marker,
            )
            with patch.object(
                unifi_wifi_apply,
                "EXPECTED_WRITE_MARKER",
                "private-test-value",
            ):
                self.assertTrue(unifi_wifi_apply.write_is_enabled(settings))

    def test_settings_reject_plain_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "base_url": "http://example.invalid",
                        "site": "default",
                        "wlan_id": "example-id",
                        "credentials_file": "/tmp/credentials",
                        "pinned_public_key_file": "/tmp/pin",
                        "backup_directory": "/tmp/backups",
                        "write_marker_file": "/tmp/marker",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(UniFiError):
                Settings.load(str(path))


if __name__ == "__main__":
    unittest.main()

