#!/usr/bin/env python3
"""Shared, local-only UniFi API client used by the example tools."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


DEFAULT_SETTINGS = "/config/unifi_api/settings.json"


class UniFiError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UniFiError(f"Unable to read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UniFiError(f"Expected a JSON object in {path}")
    return value


@dataclass(frozen=True)
class Settings:
    base_url: str
    site: str
    wlan_id: str
    credentials_file: Path
    pinned_public_key_file: Path
    backup_directory: Path
    write_marker_file: Path

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        settings_path = Path(
            path or os.environ.get("UNIFI_WIFI_SETTINGS", DEFAULT_SETTINGS)
        )
        raw = load_json(settings_path)
        required = {
            "base_url",
            "site",
            "wlan_id",
            "credentials_file",
            "pinned_public_key_file",
            "backup_directory",
            "write_marker_file",
        }
        missing = sorted(required.difference(raw))
        if missing:
            raise UniFiError(f"Missing settings: {', '.join(missing)}")

        base_url = str(raw["base_url"]).rstrip("/")
        if not base_url.startswith("https://"):
            raise UniFiError("base_url must use https://")
        return cls(
            base_url=base_url,
            site=str(raw["site"]),
            wlan_id=str(raw["wlan_id"]),
            credentials_file=Path(str(raw["credentials_file"])),
            pinned_public_key_file=Path(str(raw["pinned_public_key_file"])),
            backup_directory=Path(str(raw["backup_directory"])),
            write_marker_file=Path(str(raw["write_marker_file"])),
        )


def minimal_payload(wlan_id: str, enabled: bool) -> dict[str, Any]:
    if not wlan_id:
        raise UniFiError("Refusing to create a payload with an empty WLAN ID")
    return {"_id": wlan_id, "enabled": enabled}


class UniFiSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._tmp = tempfile.TemporaryDirectory(prefix="unifi-wifi-")
        tmp = Path(self._tmp.name)
        self.cookie_file = tmp / "cookies.txt"
        self.header_file = tmp / "headers.txt"
        self.body_file = tmp / "body.json"
        self.csrf_token: str | None = None

    def close(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "UniFiSession":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _curl(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        include_csrf: bool = False,
    ) -> Any:
        self.header_file.write_text("", encoding="utf-8")
        self.body_file.write_text("", encoding="utf-8")
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "5",
            "--max-time",
            "25",
            "--insecure",
            "--pinnedpubkey",
            str(self.settings.pinned_public_key_file),
            "--cookie",
            str(self.cookie_file),
            "--cookie-jar",
            str(self.cookie_file),
            "--request",
            method,
            "--header",
            "Accept: application/json",
            "--dump-header",
            str(self.header_file),
            "--output",
            str(self.body_file),
            "--write-out",
            "%{http_code}",
        ]
        if payload is not None:
            command.extend(
                [
                    "--header",
                    "Content-Type: application/json",
                    "--data-binary",
                    json.dumps(payload, separators=(",", ":")),
                ]
            )
        if include_csrf:
            if not self.csrf_token:
                raise UniFiError("A CSRF token is required but was not received")
            command.extend(["--header", f"X-CSRF-Token: {self.csrf_token}"])
        command.append(f"{self.settings.base_url}{path}")

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise UniFiError(f"curl failed: {result.stderr.strip()}")
        try:
            status = int(result.stdout.strip())
        except ValueError as exc:
            raise UniFiError("curl did not return a valid HTTP status") from exc
        body_text = self.body_file.read_text(encoding="utf-8").strip()
        if status < 200 or status >= 300:
            raise UniFiError(f"UniFi returned HTTP {status}: {body_text[:500]}")
        if not body_text:
            return None
        try:
            return json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise UniFiError("UniFi returned invalid JSON") from exc

    def login(self) -> None:
        credentials = load_json(self.settings.credentials_file)
        username = credentials.get("username")
        password = credentials.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise UniFiError("Credential file requires string username/password")
        self._curl(
            "POST",
            "/api/auth/login",
            {"username": username, "password": password},
        )
        for line in self.header_file.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition(":")
            if separator and name.strip().lower() == "x-csrf-token":
                self.csrf_token = value.strip()
                break
        if not self.csrf_token:
            raise UniFiError("Login succeeded but no CSRF token was returned")

    @property
    def wlan_collection_path(self) -> str:
        site = quote(self.settings.site, safe="")
        return f"/proxy/network/api/s/{site}/rest/wlanconf"

    def read_target(self) -> dict[str, Any]:
        response = self._curl("GET", self.wlan_collection_path)
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise UniFiError("Unexpected WLAN response structure")
        matches = [
            item
            for item in response["data"]
            if isinstance(item, dict) and str(item.get("_id")) == self.settings.wlan_id
        ]
        if len(matches) != 1:
            raise UniFiError(
                f"Expected exactly one WLAN with ID {self.settings.wlan_id}; "
                f"found {len(matches)}"
            )
        if not isinstance(matches[0].get("enabled"), bool):
            raise UniFiError("Target WLAN has no boolean enabled field")
        return matches[0]

    def set_enabled(self, enabled: bool) -> Any:
        wlan_id = quote(self.settings.wlan_id, safe="")
        path = f"{self.wlan_collection_path}/{wlan_id}"
        return self._curl(
            "PUT",
            path,
            minimal_payload(self.settings.wlan_id, enabled),
            include_csrf=True,
        )


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))

