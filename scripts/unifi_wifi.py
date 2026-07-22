#!/usr/bin/env python3
"""Read-only UniFi Wi-Fi status and change planner."""

from __future__ import annotations

import argparse
import sys

from unifi_common import Settings, UniFiError, UniFiSession, emit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("status", "plan-off", "plan-on"))
    parser.add_argument("--settings")
    args = parser.parse_args()

    settings = Settings.load(args.settings)
    with UniFiSession(settings) as session:
        session.login()
        wlan = session.read_target()

    current = bool(wlan["enabled"])
    result = {
        "wlan_id": settings.wlan_id,
        "ssid": wlan.get("name"),
        "current_enabled": current,
        "write_sent": False,
    }
    if args.operation != "status":
        desired = args.operation == "plan-on"
        result.update(
            {
                "operation": args.operation,
                "desired_enabled": desired,
                "would_change": current != desired,
            }
        )
    emit(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UniFiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

