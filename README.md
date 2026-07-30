# ota-prober-sooner

A small, read-only prober for two check-in protocol generations from the
original Android framework:

- The transitional protocol from build 29386 (`--protocol 29386`)
- The later 2008 protocol (`--protocol 2008`, the default)

Both modes default to:

```text
http://android.clients.google.com/checkin
```

It only reports OTA URLs returned by the server. It does **not** download an
OTA, broadcast an intent, reboot a device, or install anything.

## What was reverse engineered

The later implementation in this source tree shows the complete 2008 wire
contract:

- `CheckinService.sendCheckin()` POSTs UTF-8 JSON with media type
  `org/x-json`.
- `CheckinProtocol.formatRequest()` emits optional top-level `imei`, `digest`,
  `id` (Android ID), and `desired_build` fields plus
  `checkin.build.{product,carrier,id}`.
- A successful reply has boolean `stats_ok`.
- Server commands are returned in an `intent` array.
- An OTA is an intent whose action is
  `android.server.checkin.FOTA_UPDATE`; its `data_uri` is the OTA URL.
- The old framework hands that URL to `UpdateDownloader`, but this tool stops
  after displaying it.

The relevant originals are:

- `sources/android/server/checkin/CheckinService.java`
- `sources/android/server/checkin/CheckinProtocol.java`
- `sources/android/server/checkin/UpdateReceiver.java`

Build 29386 retains the `StatisticsService` name but introduces its own
`android.server.checkin` package. Its differences are:

- The request is an `application/x-www-form-urlencoded` form with one
  `payload` field containing JSON.
- Build properties use the nested `buildinfo` object and keys such as
  `buildinfo.id`.
- A successful reply uses `statsok`.
- Commands are returned in an `intents` array.
- An OTA intent carries its URL in `data`.

The corresponding originals are under:

- `29386-build/sources/android/server/StatisticsService.java`
- `29386-build/sources/android/server/checkin/`

## Run

No third-party dependencies are needed:

```sh
cd ota-prober-sooner
PYTHONPATH=src python3 -m ota_prober_sooner --dry-run
```

Probe the endpoint as the default `sooner` product:

```sh
PYTHONPATH=src python3 -m ota_prober_sooner \
  --build-id TC4-RC29 \
  --carrier T-Mobile
```

Probe as build 29386:

```sh
PYTHONPATH=src python3 -m ota_prober_sooner \
  --protocol 29386 \
  --product sooner \
  --build-id htc-29386.0.9.0.0 \
  --build-date '三  8月 29 18:03:11 CST 2007' \
  --build-type release \
  --build-user root \
  --build-host sfchiou-desktop \
  --json
```

The 29386 protocol did not transmit `ro.build.carrier`. Without `--imei`, this
mode sends the historical fallback value `Unknown`. Its `stats` array is left
empty so the probe does not manufacture device telemetry.

Ask for a particular build, if the server still honors the old field:

```sh
PYTHONPATH=src python3 -m ota_prober_sooner \
  --build-id TC4-RC29 \
  --desired-build TC5 \
  --json
```

Only pass an IMEI or Android ID if it is actually necessary. They are sent to
the remote service and may be sensitive:

```sh
PYTHONPATH=src python3 -m ota_prober_sooner \
  --android-id 0x12345678 \
  --imei 000000000000000
```

For an installed command:

```sh
python3 -m pip install -e .
ota-prober-sooner --help
```

## Test

The transport test uses an in-memory HTTP double:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

No sockets are opened, and the real Google endpoint is never contacted by the
test suite.
