# Home Assistant to UniFi Wi-Fi Control

Sanitized implementation and maintenance guide.

> This shareable edition intentionally omits addresses, software versions,
> account names, WLAN identifiers, certificate pins, credentials, SSID names,
> private paths, and the write-enable value.

## Purpose

This setup lets Home Assistant read and control one selected UniFi Wi-Fi
network through the UniFi console's local Network API. It was created as a
local workaround where the normal Home Assistant UniFi control path was not
usable.

It can:

- Read whether the selected Wi-Fi network is enabled.
- Show the state in Home Assistant as **On** or **Off**.
- Enable or disable the network from Home Assistant automations.
- Avoid unnecessary writes when the network already has the requested state.
- Read the state back after every change and fail if verification does not
  match.
- Require an explicit local safety marker before any write is permitted.

## System overview

```text
Home Assistant automation
  -> shell_command action
  -> local Python safety wrapper
  -> HTTPS connection to <UNIFI_LOCAL_ADDRESS>
  -> authenticate, read/change WLAN, then verify
```

The connection remains on the local network. No cloud relay is required.

## Repository contents

- [`scripts/unifi_common.py`](scripts/unifi_common.py) — shared authenticated
  local API client, TLS pin enforcement, WLAN lookup, and minimal writes.
- [`scripts/unifi_wifi.py`](scripts/unifi_wifi.py) — read-only `status`,
  `plan-off`, and `plan-on` operations.
- [`scripts/unifi_wifi_apply.py`](scripts/unifi_wifi_apply.py) — locked writer,
  pre-write backup, and read-after-write verification.
- [`examples/`](examples/) — sanitized settings, credentials, and payload
  templates.
- [`tests/test_safety.py`](tests/test_safety.py) — offline fail-closed safety
  tests that never contact UniFi.
- [`TESTING.md`](TESTING.md) — the complete staged test procedure, from
  unauthenticated reachability through a supervised off/on test.

The exported scripts are sanitized, functional reconstructions of the tested
implementation. They are not byte-for-byte copies of the private deployed
files. Compare them with the deployed copies before replacing anything in Home
Assistant.

## Configuration inventory

The working installation stores persistent material beneath a private
directory under Home Assistant's `/config` directory. The exact directory and
filenames are omitted here.

- Credential file for a dedicated local UniFi account.
- Pinned TLS public-key file for the intended UniFi console.
- Read-only status and planning tool.
- Locked write tool accepting only `on` or `off`.
- Minimal enable and disable JSON payloads.
- Backup of the original WLAN object.
- Private write-enable marker containing an exact confirmation value.

### UniFi account

A dedicated local UniFi account is used. It was initially read-only during
discovery and validation. The writer requires permission to manage the Network
application, but the account should not be an Owner, Super Admin, or
administrator of unrelated UniFi applications.

The credential file should be readable only by the Home Assistant execution
environment. Never embed the password in an automation, dashboard field,
notification, log, or public repository.

```sh
chmod 600 <PRIVATE_CREDENTIAL_FILE>
```

### TLS identity protection

The UniFi console uses a locally issued or otherwise untrusted HTTPS
certificate. The scripts therefore bypass normal certificate-authority and
hostname validation, but also require the server certificate's public key to
match a locally stored pin.

A mismatched key stops the connection before credentials are transmitted. The
actual public-key pin is deliberately excluded from this document.

### Sensitive WLAN backup

Before writes were enabled, the complete target WLAN object was saved. It may
contain security-related Wi-Fi fields, so it must be protected like a
credential and must not be included in public examples.

```sh
chmod 600 <PRIVATE_WLAN_BACKUP>
```

## Local API behavior

The implementation performs three operations through the UniFi console's local
API:

1. Authenticate and retain the resulting session cookies and anti-forgery
   token.
2. Read the WLAN collection for `<UNIFI_SITE>` and locate
   `<TARGET_WLAN_ID>`.
3. For a requested change, update only the `enabled` property and then read the
   WLAN again to verify the result.

The endpoint paths are omitted from this public copy. They are not credentials,
but omitting them keeps this guide independent of a specific deployment.

These local endpoints are not guaranteed to be a stable public interface. A
future UniFi update may change authentication, token handling, response fields,
or paths.

## Read-only tool

The read-only tool supports three fixed operations:

- `status` — authenticate, find the target WLAN, and return its current enabled
  state as JSON.
- `plan-off` — show what disabling would do without sending a write.
- `plan-on` — show what enabling would do without sending a write.

Both planning operations must explicitly report that no write was sent. They
should be tested before any write capability is enabled.

## Writer and safety controls

The write tool accepts only the literal operations `on` and `off`. It refuses
all changes unless a private marker file exists and contains the exact private
confirmation value. Neither the marker's name nor its value is included here.

For every accepted request, the writer:

1. Authenticates with UniFi.
2. Reads the current WLAN object and confirms the configured ID exists.
3. Returns success without writing if the WLAN is already in the requested
   state.
4. Saves a pre-write copy of the current WLAN object.
5. Sends a minimal payload containing only the WLAN ID and enabled state.
6. Reads the WLAN again and confirms that the resulting state matches the
   request.
7. Returns an error if any prerequisite, write, or verification step fails.

Removing or renaming the private marker disables all write capability while
preserving the tools for later use.

## Home Assistant actions

Home Assistant exposes five local shell-command actions. The private script
paths are represented by placeholders:

```yaml
shell_command:
  unifi_wifi_status: "python3 <PRIVATE_PATH>/wifi_read.py status"
  unifi_wifi_plan_off: "python3 <PRIVATE_PATH>/wifi_read.py plan-off"
  unifi_wifi_plan_on: "python3 <PRIVATE_PATH>/wifi_read.py plan-on"
  unifi_wifi_off: "python3 <PRIVATE_PATH>/wifi_write.py off"
  unifi_wifi_on: "python3 <PRIVATE_PATH>/wifi_write.py on"
```

After editing these definitions, reload Shell Command from Home Assistant's
Developer Tools. Home Assistant limits shell commands to 60 seconds, so every
script should use short connection and request timeouts.

See the official [Home Assistant Shell Command documentation][ha-shell].

## Status sensor

A command-line binary sensor polls the read-only status tool every two minutes:

```yaml
command_line:
  - binary_sensor:
      name: "UniFi Target WiFi"
      unique_id: unifi_target_wifi_status
      command: "python3 <PRIVATE_PATH>/wifi_read.py status"
      value_template: >-
        {{ 'ON' if value_json.current_enabled else 'OFF' }}
      payload_on: "ON"
      payload_off: "OFF"
      scan_interval: 120
      command_timeout: 25
```

Do not assign `device_class: connectivity` if the desired dashboard text is
**On** and **Off**. That device class intentionally changes the visible labels
to **Connected** and **Disconnected**.

After editing the sensor:

1. Check the Home Assistant configuration.
2. Reload the Command Line integration.
3. Wait up to two minutes for the next poll.
4. Confirm the sensor agrees with the UniFi interface.

See the official [Home Assistant binary-sensor documentation][ha-binary].

## Safe validation sequence

1. Run `status`. Confirm return code `0`, valid JSON, the intended WLAN, and the
   expected current state.
2. Run `plan-off` and `plan-on`. Confirm both explicitly report that no write
   was sent.
3. Request the state that is already active. Confirm the writer reports no
   change, no write, and a verified final state.
4. Only then perform a supervised real test: switch off briefly, switch on
   again, and confirm the final read-back state.

Perform any disruptive test while connected through Ethernet or a different
SSID so loss of the target Wi-Fi cannot also remove access to Home Assistant.

## Automation pattern

An automation calls the relevant shell command and captures its response. A
nonzero return code creates a notification:

```yaml
actions:
  - action: shell_command.unifi_wifi_off
    response_variable: unifi_result

  - if:
      - condition: template
        value_template: "{{ unifi_result.returncode != 0 }}"
    then:
      - action: persistent_notification.create
        data:
          title: "UniFi Wi-Fi change failed"
          message: "{{ unifi_result.stderr or unifi_result.stdout }}"
```

## Certificate and key-pin maintenance

There is no scheduled certificate-expiry maintenance for this design. Normal
certificate expiry is not enforced because ordinary certificate validation is
bypassed. Server identity is instead constrained by the pinned public key.

- **New certificate using the same key:** the existing public-key pin continues
  to work.
- **New certificate using a new key:** the connection fails safely with a key
  mismatch.

A key change may occur after certificate replacement, firmware or console
changes, a factory reset, a restore, or hardware replacement. Never automate
acceptance of a new pin.

If the pin fails:

1. Confirm that `<UNIFI_LOCAL_ADDRESS>` still belongs to the intended UniFi
   console.
2. Check whether a firmware update, reset, restore, or certificate change
   occurred.
3. Inspect the new certificate and public key over a trusted local connection.
4. Replace the stored pin only after independently confirming the change is
   legitimate.
5. Run `status` and both planning operations before allowing any write.

`curl --pinnedpubkey` requires the server certificate to contain the expected
public key. See the official [curl documentation][curl-pin].

## Ongoing maintenance

### After a UniFi update

1. Run `status`.
2. Run both planning operations.
3. Run a no-op request for the already active state.
4. Use a supervised short off/on test only if needed.

If the API response changes, diagnose it before weakening validation or TLS
safety checks.

### After renaming or recreating the SSID

A recreated WLAN may receive a different internal ID even when its visible
name is unchanged. Repeat discovery and validate:

- SSID name.
- Internal WLAN ID.
- Current enabled state.
- IDs in both minimal payloads.
- Target ID used by both tools.

Do not identify the network by display name alone.

### After changing the UniFi account

Update the private credential file, then test `status` and both plans before any
write. Confirm that the account has only the necessary Network permissions.

### Periodic review

- Confirm that the sensor updates and agrees with the UniFi interface.
- Run a planning operation and confirm no write is sent.
- Review the dedicated account's permissions.
- Confirm the write marker exists only when writes are intentionally allowed.
- Protect credentials, pins, WLAN backups, and Home Assistant backups.
- Review errors after major Home Assistant, Python, curl, or UniFi updates.

## Troubleshooting

### Authentication failure

Check the local account, credentials, login behavior, and whether UniFi changed
its authentication requirements.

### Permission denied

Authentication may work while writes are refused. Confirm that the dedicated
account can manage the Network application without granting broader console
ownership.

### Pinned-key failure

The certificate key changed, the wrong host answered, or the pin file is
damaged. Verify the device and refresh the pin deliberately. Do not permanently
bypass pinning.

### Sensor unavailable or unknown

Run the underlying status operation and inspect its return code and JSON.
Common causes include:

- Offline UniFi console.
- Changed credentials.
- Changed TLS public key.
- Altered API response.
- Missing or replaced WLAN ID.
- Command timeout.
- Invalid JSON output.

### Dashboard shows Connected

Remove `device_class: connectivity` and reload the Command Line integration.
Generic binary sensors display **On** and **Off**.

### Write appears accepted but state does not change

Treat the operation as failed if the final read-back does not match. Inspect
the command result, WLAN ID, account permission, and whether UniFi reverted the
setting.

## Security summary

The important controls are:

- Local-network communication.
- Dedicated, least-privilege UniFi account.
- Credentials kept outside automation YAML.
- TLS public-key pinning.
- Fixed command arguments and separate read/write tools.
- Private write-enable marker.
- Minimal write payloads.
- Pre-write backup and read-after-write verification.
- No automatic acceptance of certificate-key changes.

The principal compatibility risk is reliance on a local UniFi API that may
change. The principal certificate-related maintenance task is verifying a
legitimate public-key change, not monitoring the certificate expiry date.

## Information intentionally removed

This public version excludes:

- Local and public IP addresses.
- Exact product and software-version identifiers.
- SSID, site, account, and entity names tied to the installation.
- WLAN internal IDs.
- Credentials, cookies, anti-forgery tokens, and Wi-Fi secrets.
- The actual certificate public-key pin.
- Exact private filenames, directory names, and write-enable phrase.

Do not attach live scripts, configuration directories, console output, or Home
Assistant backups without a separate secrets review.

[ha-shell]: https://www.home-assistant.io/integrations/shell_command/
[ha-binary]: https://www.home-assistant.io/integrations/binary_sensor/
[curl-pin]: https://curl.se/docs/manpage.html#--pinnedpubkey
