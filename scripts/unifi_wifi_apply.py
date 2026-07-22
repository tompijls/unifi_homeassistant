#!/usr/bin/env python3
"""Locked UniFi Wi-Fi writer with backup and read-after-write verification."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from unifi_common import Settings, UniFiError, UniFiSession, emit


# Replace this placeholder only in the private deployed copy. Do not commit the
# real value to a public repository.
EXPECTED_WRITE_MARKER = "<SET_A_PRIVATE_RANDOM_CONFIRMATION_VALUE>"


def write_is_enabled(settings: Settings) -> bool:
    try:
        actual = settings.write_marker_file.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return actual == EXPECTED_WRITE_MARKER


def save_backup(settings: Settings, wlan: dict) -> str:
    settings.backup_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = settings.backup_directory / f"wlan-before-write-{stamp}.json"
    path.write_text(json.dumps(wlan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("off", "on"))
    parser.add_argument("--settings")
    args = parser.parse_args()

    settings = Settings.load(args.settings)
    if EXPECTED_WRITE_MARKER.startswith("<"):
        raise UniFiError("Private write-marker value has not been configured")
    if not write_is_enabled(settings):
        raise UniFiError("Writes are locked: write-marker validation failed")

    desired = args.operation == "on"
    with UniFiSession(settings) as session:
        session.login()
        before = session.read_target()
        if bool(before["enabled"]) == desired:
            emit(
                {
                    "changed": False,
                    "write_sent": False,
                    "verified_enabled": desired,
                    "wlan_id": settings.wlan_id,
                }
            )
            return 0

        backup = save_backup(settings, before)
        session.set_enabled(desired)
        after = session.read_target()

    verified = bool(after["enabled"]) == desired
    result = {
        "backup": backup,
        "changed": verified,
        "write_sent": True,
        "verified_enabled": bool(after["enabled"]),
        "wlan_id": settings.wlan_id,
    }
    emit(result)
    if not verified:
        raise UniFiError("Write completed but read-back verification failed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UniFiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

