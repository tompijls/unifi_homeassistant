# Safe staged test procedure

This reproduces the validation sequence used during development. Stop after any
unexpected result. Do not proceed to the next stage merely because a command
returned output.

## 1. Network reachability — no authentication

From the Home Assistant execution environment, request the UniFi console's
local HTTPS root with a short timeout.

Expected result: the console is reachable and returns an HTTP response. No
credentials are sent and no configuration is changed.

## 2. Confirm the local API requires authentication

Request the WLAN collection without credentials.

Expected result: HTTP `401`. This confirms that the endpoint exists and is not
open anonymously.

## 3. Authenticate only

Use the dedicated local UniFi account to call the local authentication
endpoint. Store cookies and response headers in temporary files.

Expected result:

- HTTP `200`.
- A session cookie is returned.
- An anti-forgery/CSRF token is returned.
- No WLAN write occurs.

If authentication returns `403`, verify the account type and console access.
Do not broaden permissions until the read-only tests are understood.

## 4. Read and identify the target WLAN

Use the authenticated session to read the WLAN collection. Locate the target by
SSID for discovery, then record its immutable internal `_id`.

Verify all three values manually:

- Expected SSID is shown.
- Internal ID matches the intended WLAN.
- `enabled` is a Boolean with the expected current value.

Save the complete original WLAN object to a protected backup and set its
permissions to `0600`.

## 5. Validate minimal payloads offline

Create separate enable and disable payloads containing only:

```json
{
  "_id": "<TARGET_WLAN_ID>",
  "enabled": false
}
```

and:

```json
{
  "_id": "<TARGET_WLAN_ID>",
  "enabled": true
}
```

Confirm that the ID in both files exactly matches the discovered target ID.

## 6. Install and verify the TLS public-key pin

Capture the console certificate's public key while physically connected to the
trusted local network. Configure the scripts to use both the locally required
certificate-validation exception and `--pinnedpubkey`.

Expected result:

- Correct pin: authenticated read succeeds.
- Deliberately incorrect test pin: connection fails before credentials are
  accepted.

Restore the verified correct pin after the negative test.

## 7. Run offline unit tests

These tests make no network calls:

```sh
python3 -m unittest discover -s tests -v
```

Expected result: all tests pass. They validate minimal payloads, HTTPS-only
settings, and fail-closed write-marker behavior.

## 8. Test the read-only tool

```sh
python3 scripts/unifi_wifi.py status --settings <PRIVATE_SETTINGS_FILE>
python3 scripts/unifi_wifi.py plan-off --settings <PRIVATE_SETTINGS_FILE>
python3 scripts/unifi_wifi.py plan-on --settings <PRIVATE_SETTINGS_FILE>
```

Expected result:

- Commands exit with code `0`.
- Output is valid JSON.
- Target ID and current state are correct.
- Every result contains `"write_sent": false`.

## 9. Confirm that the writer fails closed

Keep the write marker absent and run both writer operations:

```sh
python3 scripts/unifi_wifi_apply.py off --settings <PRIVATE_SETTINGS_FILE>
python3 scripts/unifi_wifi_apply.py on --settings <PRIVATE_SETTINGS_FILE>
```

Expected result: both commands fail before authentication or any write.

Repeat with an incorrect marker value. Both commands must still fail.

## 10. Verify the dedicated account's permission boundary

With the account still read-only, a direct write attempt should return HTTP
`403`. This is a permission test, not a state-change test.

Only after all read-only and safety tests pass, grant the dedicated account the
minimum Network-management permission needed for WLAN changes. Do not grant
Owner, Super Admin, or unrelated application access.

## 11. Enable the private writer

In the private deployed copy only:

1. Replace the placeholder `EXPECTED_WRITE_MARKER` with a private random value.
2. Create the private marker file containing exactly that value.
3. Protect the scripts, settings, credentials, pin, marker, and backups from
   untrusted modification or disclosure.

Never commit the real marker value.

## 12. Perform a no-op writer test

If the WLAN is currently enabled, request `on`. If it is disabled, request
`off`.

Expected result resembles:

```json
{
  "changed": false,
  "write_sent": false,
  "verified_enabled": true
}
```

The exact verified state depends on the requested no-op. No PUT request should
be sent.

## 13. Test through Home Assistant

Add the read and write tools as `shell_command` actions, reload Shell Command,
and run:

1. Status.
2. Plan off.
3. Plan on.
4. The same-state no-op writer action.

Check `returncode`, `stdout`, and `stderr` after every action.

## 14. Supervised real change

Only after every earlier stage passes:

1. Connect through Ethernet or a different SSID.
2. Request `off` for the target WLAN.
3. Wait approximately 30 seconds.
4. Request `on`.
5. Wait approximately 5 seconds.
6. Run status and confirm the WLAN is enabled.

The writer must save a pre-write backup and verify both resulting states by
reading them back from UniFi.

## 15. Sensor test

Enable the command-line binary sensor with a 120-second polling interval.

Expected result:

- State agrees with UniFi.
- Generic display is **On** or **Off**.
- No `connectivity` device class is assigned if Connected/Disconnected labels
  are not desired.

## Regression test after updates

After significant UniFi or Home Assistant updates, repeat stages 7, 8, 9, and
12 before allowing a real change. If the public-key pin changes, independently
verify the new console key before updating it.
