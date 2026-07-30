# Early Android check-in protocols

This document describes three check-in protocol generations recovered from
early Android framework builds:

1. Build 20645, dated May 15, 2007
2. Build 29386, dated August 29, 2007
3. The later Checkin implementation represented by the January 15, 2008
   Sooner engineering build

These protocols are not interchangeable. They use different request
encodings, JSON field names, response shapes, and OTA mechanisms.

## Quick comparison

| Property | Build 20645 | Build 29386 | January 2008 |
|---|---|---|---|
| Framework service | `statistics` | `statistics` | `checkin` |
| Service class | `StatisticsService` | `StatisticsService` | `CheckinService` |
| Endpoint source | Hard-coded host | Gservices setting | Gservices setting |
| Check-in/statistics endpoint | `http://dm17.google.com/statistics` | `http://jmt17.google.com/checkin` | `http://android.clients.google.com/checkin` |
| Request encoding | Form fields | Form field containing JSON | Raw JSON |
| Success indicator | HTTP 200 | `statsok` | `stats_ok` |
| Commands | Separate `/intent` request | `intents` array | `intent` array |
| OTA URL field | None | `data` | `data_uri` |
| Built-in OTA support | Not found | Yes | Yes |
| Prober mode | Not implemented | `--protocol 29386` | `--protocol 2008` |

The prober uses protocol-specific historical defaults:

```text
Build 29386:  http://jmt17.google.com/checkin
January 2008: http://android.clients.google.com/checkin
```

Both frameworks obtain their URL from the `checkin_service_url` Gservices
setting. For build 29386, the system image preserves its configured value in
the compiled `res/xml/gservices.xml` inside `javalib/framework-res.apk`:

```xml
<gservice name="checkin_service_url"
          value="http://jmt17.google.com/checkin" />
```

The January 2008 system image also preserves its configured value, as
plaintext in `system/etc/gservices-conf.xml`:

```xml
<gservice label="checkin_service_url"
          value="http://android.clients.google.com/checkin" />
```

## Remote brick command

All three framework generations recognize the exact intent action:

```text
SHES_A_BRICK_HOUSE
```

This is not the name of an OTA package, Java service, or Binder service. It is
a server command that causes the framework to start an Android init service
named `brick`.

### Command path

The complete path is:

1. The check-in or command response is parsed into an Android `Intent`.
2. The framework compares the intent action with `SHES_A_BRICK_HOUSE`.
3. On an exact match, it does not broadcast the intent or process it as an
   OTA. It calls `SystemService.start("brick")` directly.
4. Android init resolves the service name `brick` and launches its configured
   executable.

The init-control transport changed between builds:

| Build | `SystemService.start("brick")` implementation |
|---|---|
| 20645 | Native `SystemService.sendMessage()` sends `start brick` over the local `android-init` socket |
| 29386 | Sets the init control property `ctl.start` to `brick` |
| January 2008 | Sets the init control property `ctl.start` to `brick` |

For build 20645, the Java side is visible in
`20645-build/sources/android/os/SystemService.java`. Its native implementation
is in the full image's `lib/libjava_runtime.so`: the exported
`send_init_msg(char const*)` routine connects to `android-init`, writes the
NUL-terminated control message, and closes the socket. Builds 29386 and 2008
use the later property-based init-control mechanism visible directly in their
`android/os/SystemService.java`.

There is no confirmation prompt or intermediate application component. The
special action is intercepted inside `StatisticsService` or `CheckinService`
and sent straight to init.

### Init service

The corresponding historical Android init definition is:

```rc
service brick /system/bin/wipe nuke
    disabled
```

`disabled` means the service is not started automatically with its service
class; it can still be started explicitly by name. With no `user` option, the
service runs as root.

The supplied system directories do not contain their boot ramdisk, so their
exact device-specific `init.rc` files are unavailable. The definition above
comes from the matching historical Android platform init configuration. The
January 2008 image does contain the `wipe nuke` implementation inside
`system/bin/toolbox`; the extracted directory does not preserve the
`/system/bin/wipe` toolbox symlink. The 20645 and 29386 system dumps omit both
the ramdisk definition and the wipe executable, so their final native hop is
supported by the shared platform implementation but cannot be proven solely
from those two directories.

### What `wipe nuke` does

The historical toolbox implementation performs these operations in order:

1. Recursively removes the contents of `/system`.
2. Recursively removes the contents of `/data`.
3. Calls `android_reboot(ANDROID_RB_RESTART, 0, 0)`.

The recursive deletion:

- Skips `.`, `..`, and every `lost+found` directory.
- Unlinks files and symlinks.
- Removes directories after emptying them.
- Leaves certain init-created directory nodes in place to preserve their
  special permissions, while still deleting their contents:
  `/system/etc/ppp`, `/data/misc`, `/data/local`, `/data/local/tmp`,
  `/data/data`, `/data/app_private`, and `/data/app`.

This is recursive file deletion, not a cryptographic or block-level secure
erase. It does not target `/cache`, the SD card, bootloader, radio, boot, or
recovery partitions. Individual `opendir`, `lstat`, `unlink`, and `rmdir`
errors are printed but do not abort the overall sequence; the reboot is still
attempted after both trees. The actual amount deleted therefore depends on
mount state and filesystem permissions. In particular, a read-only `/system`
mount can turn the `/system` phase into a series of failures while `/data`
remains writable.

The historical platform sources that define the final two stages are:

- [Android init `brick` service](https://android.googlesource.com/platform/build/+/cf28b80398f36e5a3e67f803458e07442a2b9364/target/board/generic_x86/init.rc)
- [Toolbox `wipe nuke` implementation](https://android.googlesource.com/platform/system/core/+/e3aeeb4de34dbb93e832e6554f494122ba633f3b/toolbox/wipe.c)

The prober never follows this command path. It reports
`dangerous_action_present: true` and ignores the action without broadcasting
it or contacting init.

## Build 20645: Statistics protocol version 1

Build 20645 predates the `android.server.checkin` package. The system service
is registered as `statistics`, and `StatisticsService` communicates with the
hard-coded host:

```text
dm17.google.com
```

The complete image at `~/stuff/google/android-1.0/20645` contains no
`checkin_service_url` Gservices key. Its `javalib/framework.jar` DEX contains
the hard-coded host and the `/statistics`, `/intent`, and `/crash` paths. This
matches `20645-build/sources/android/server/StatisticsService.java`.

It uses three independent HTTP endpoints.

### Statistics upload

```http
POST http://dm17.google.com/statistics
Content-Type: application/x-www-form-urlencoded
```

Form fields:

| Name | Value |
|---|---|
| `stats` | Literal string `stats` |
| `imei` | Value of the telephony IMEI system property |
| `data` | Protocol-version-1 statistics JSON |
| `ro.build.id` | Raw system property |
| `ro.build.date` | Raw system property |
| `ro.build.type` | Raw system property |
| `ro.build.product` | Raw system property |
| `ro.build.user` | Raw system property |
| `ro.build.host` | Raw system property |

`ro.build.carrier` and `ro.build.date.utc` are not transmitted.

The `data` form value has this structure:

```json
{
  "version": 1,
  "data": [
    {
      "tag": "example-tag",
      "value": "example-value",
      "date": 1179222411000
    }
  ]
}
```

Rows loaded from the statistics database serialize `date` and `value` as
strings. Values collected from a live report broadcast may retain their JSON
number or boolean type.

For the supplied 20645 build, the build fields are:

```text
ro.build.id=htc-20645.0.8.0.0
ro.build.date=二  5月 15 17:46:51 CST 2007
ro.build.type=
ro.build.product=
ro.build.user=tony
ro.build.host=tony-ubuntu
```

Only HTTP status `200` marks the upload as successful. The response body is
not parsed as a check-in response.

### Server command fetch

Commands are fetched separately after a statistics report:

```http
POST http://dm17.google.com/intent
Content-Type: application/x-www-form-urlencoded

imei=<device IMEI>
```

The response is a top-level JSON array:

```json
[
  {
    "action": "example.intent.ACTION",
    "extras": [
      {
        "key": "example",
        "value": "value"
      }
    ]
  }
]
```

Each command becomes an Android broadcast. The special action
`SHES_A_BRICK_HOUSE` starts the `brick` system service instead.

This schema has no intent data URI or MIME type. No FOTA constants,
downloader, recovery installer, or built-in OTA receiver were found in the
20645 framework. A separate package outside the framework dump could still
have implemented an update mechanism.

### Crash upload

Crash records are sent as raw binary request bodies:

```http
POST http://dm17.google.com/crash
```

This endpoint is independent of the statistics and command protocols.

## Build 29386: transitional Checkin protocol

Build 29386 still registers `StatisticsService` under the `statistics` binder
name, but introduces:

- `android.server.checkin.CheckinRequest`
- `android.server.checkin.CheckinResponse`
- `android.server.checkin.UpdateDownloader`
- The first built-in `FOTA_UPDATE`, `FOTA_READY`, and `FOTA_INSTALL` actions

### Request transport

The URL comes from the `checkin_service_url` Gservices setting. In the full
29386 system image at `~/stuff/google/android-1.0/29386`, resource ID
`0x01070004` resolves to the compiled `res/xml/gservices.xml` inside
`javalib/framework-res.apk`. Its configured value is:

```text
http://jmt17.google.com/checkin
```

The value is stored in a compressed APK entry and compiled binary XML with a
UTF-16 string pool, which is why a plain recursive `grep` of the system image
does not find it.

The client sends a normal HTML-style form with one parameter:

```http
POST <checkin_service_url>
Content-Type: application/x-www-form-urlencoded

payload=<URL-encoded JSON>
```

The JSON inside `payload` is:

```json
{
  "imei": "Unknown",
  "buildinfo": {
    "buildinfo.id": "htc-29386.0.9.0.0",
    "buildinfo.date": "三  8月 29 18:03:11 CST 2007",
    "buildinfo.type": "release",
    "buildinfo.product": "sooner",
    "buildinfo.user": "root",
    "buildinfo.host": "sfchiou-desktop"
  },
  "stats": [
    {
      "tag": "uptime",
      "value": "12345",
      "date": 1188381791000
    }
  ]
}
```

The unusual qualified keys such as `buildinfo.id` really are nested inside
the `buildinfo` object.

`ro.build.carrier=generic` and `ro.build.date.utc` are not sent. The literal
build ID is used without the later engineering-build transformation.

The original client always included its IMEI system property and accumulated
statistics. The prober uses the historical fallback `Unknown` when no IMEI is
given and sends an empty `stats` array to avoid manufacturing telemetry.

### Form character encoding

The 29386 implementation uses Commons HttpClient's default form encoding,
ISO-8859-1. Characters outside that repertoire are replaced during encoding.
For the supplied build date, the actual historical wire value is therefore:

```text
?  8? 29 18:03:11 CST 2007
```

The prober preserves the original Unicode text in dry-run output and applies
the historical replacement only when constructing the HTTP form body.

### Response

The response is a JSON object:

```json
{
  "statsok": true,
  "intents": [
    {
      "action": "android.server.checkin.FOTA_UPDATE",
      "data": "http://example.invalid/sooner-update.zip",
      "extras": {
        "sha1": "example"
      }
    }
  ]
}
```

Both `statsok` and `intents` are required by the original parser.

Intent fields:

| Name | Type | Meaning |
|---|---|---|
| `action` | String | Android intent action |
| `data` | String or `null` | Intent data URI; the OTA download URL for `FOTA_UPDATE` |
| `extras` | Object or `null` | String-to-string intent extras |

If any intent has malformed JSON or an invalid data URI, the response is
marked as having an intent parse error and `StatisticsService` does not
broadcast any intents from that response.

### OTA lifecycle

When a valid `FOTA_UPDATE` intent is received, build 29386 immediately starts
`UpdateDownloader` with the intent's `data` URI.

The downloader:

1. Stores the file under `/data/download/update/`.
2. Uses an HTTP `Range` header to resume partial downloads.
3. Treats HTTP `206` as a resumed download.
4. Treats HTTP `416` as an already-complete download.
5. Deletes the partial file after HTTP `502`.
6. Retries failures indefinitely after a randomized 5–10 minute delay.
7. Broadcasts `FOTA_READY` with a file URI when complete.

An `FOTA_INSTALL` broadcast causes the file to be moved to:

```text
/data/download/update.install
```

The framework then executes:

```text
/sbin/reboot recovery:install_package=/data/download/update.install
```

This generation has no `FOTA_CANCEL` or `FOTA_RESTART` action and performs no
visible URL-scheme validation before starting the download.

The prober only extracts and displays the OTA URL. It never reproduces this
download or installation behavior.

## January 2008: CheckinService JSON protocol

By January 2008, the service has been renamed to `CheckinService` and is
registered under the `checkin` binder name. Check-in storage moves from the
private `stats.db` design to the Checkin content provider.

### Request transport

The URL comes from the `checkin_service_url` Gservices setting. In the
engineering system image at `~/stuff/google/android-1.0/system`, the
bootstrapping configuration is plaintext in
`etc/gservices-conf.xml`:

```xml
<gservice label="provisioning_url"
          value="http://android.clients.google.com/provisioning" />
<gservice label="checkin_service_url"
          value="http://android.clients.google.com/checkin" />
<gservice label="crash_report_url"
          value="http://android.clients.google.com/crash" />
```

The same file contains
`gsync_sub_server=http://jmt17.google.com/gsync/sub`. That `jmt17` URL belongs
to GSync and is not the January 2008 Checkin endpoint.

```http
POST http://android.clients.google.com/checkin
Content-Type: org/x-json; charset=UTF-8
```

Unlike build 29386, the request body is raw JSON rather than a form parameter.

Representative request:

```json
{
  "imei": "optional IMEI",
  "digest": "optional provisioning digest",
  "id": 123456789,
  "desired_build": "optional desired build",
  "checkin": {
    "build": {
      "product": "sooner",
      "carrier": "generic",
      "id": "ficus@dropzone.corp.google.com 2008-01-15 12:15:55"
    },
    "last_checkin_msec": 1200428155000,
    "event": [
      {
        "tag": "SYSTEM_BOOT",
        "time_msec": 1200428155000
      }
    ],
    "stat": [
      {
        "tag": "ELAPSED_UPTIME_SEC",
        "count": 0,
        "sum": 123.0
      }
    ]
  }
}
```

Top-level fields:

| Name | Required | Meaning |
|---|---|---|
| `imei` | No | Device IMEI |
| `digest` | No | Provisioning digest |
| `id` | No | Numeric Android ID |
| `desired_build` | No | Requested target build |
| `checkin` | Yes | Build identity and telemetry |

The `event`, `stat`, and `last_checkin_msec` members are conditional in the
formatter and are omitted when there is no corresponding local data.

### Engineering build IDs

When `ro.build.id` is not `engineering`, its literal value is sent as the
build ID.

When it is exactly `engineering`, the framework constructs:

```text
<ro.build.user>@<ro.build.host> yyyy-MM-dd kk:mm:ss
```

For the supplied January build, this becomes:

```text
ficus@dropzone.corp.google.com 2008-01-15 12:15:55
```

The timestamp is derived from `ro.build.date.utc` and formatted in the
device's timezone.

### Response

```json
{
  "stats_ok": true,
  "intent": [
    {
      "action": "android.server.checkin.FOTA_UPDATE",
      "data_uri": "http://example.invalid/sooner-update.zip",
      "mime_type": "application/zip",
      "extra": [
        {
          "name": "sha1",
          "value": "example"
        }
      ]
    }
  ]
}
```

`stats_ok` must exist and be true. The `intent` array is optional.

Intent fields:

| Name | Type | Meaning |
|---|---|---|
| `action` | String | Android intent action |
| `data_uri` | String | Optional intent data URI |
| `mime_type` | String | Optional MIME type |
| `extra` | Array | Optional string name/value extras |

Special actions:

- `SHES_A_BRICK_HOUSE` starts the `brick` system service.
- `android.intent.action.PROVISIONING_CHECK` begins provisioning retrieval.
- `android.server.checkin.FOTA_UPDATE` begins the OTA flow.
- If no FOTA update is returned, the service broadcasts `FOTA_CANCEL`.

Compared with build 29386, the later downloader adds explicit cancellation,
restart scheduling, status reporting, and an HTTP-scheme check in the update
receiver.

## Prober normalization and safety

The prober normalizes both supported response generations into:

```json
{
  "stats_ok": true,
  "ota_offers": [
    {
      "url": "http://example.invalid/sooner-update.zip"
    }
  ],
  "intents": [
    {
      "action": "android.server.checkin.FOTA_UPDATE",
      "data_uri": "http://example.invalid/sooner-update.zip"
    }
  ],
  "dangerous_action_present": false
}
```

It deliberately does not:

- Broadcast returned intents
- Start Android services
- Follow OTA URLs
- Download packages
- Verify or install packages
- Reboot a device

Unknown server actions are reported and ignored. The brick action is surfaced
as `dangerous_action_present` and ignored.

## Command examples

Build 29386:

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

January 2008:

```sh
PYTHONPATH=src python3 -m ota_prober_sooner \
  --protocol 2008 \
  --product sooner \
  --carrier generic \
  --build-id 'ficus@dropzone.corp.google.com 2008-01-15 12:15:55' \
  --json
```

Add `--dry-run` to either command to inspect the generated JSON without
opening a network connection.
