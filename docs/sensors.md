# Farm sensors: adding gateways and nodes

How to put a new LoRaWAN gateway or temperature sensor on the site. Written after the first
node (`little-dragon-01`, a Dragino D20-LB) went live on 2026-10-27; the troubleshooting table
lists every problem we hit getting there.

## How the data gets to the page

```
sensor ──LoRa──> any TTN gateway in range ──> The Things Network (nam1)
                                                 application my-tracker-320
                                                 └─ Message storage (keeps recent uplinks)
GitHub Actions, every ~20 min
  └─ ingest/sources/sensors.py reads Message storage with TTN_API_KEY
       └─ merges with the last published sensors.json, runs QC, keeps 7 days
            └─ web/data/sensors.json ──> map markers + "Farm sensors" card
```

Gateways are not tied to an application. Any TTN gateway that hears a sensor forwards its uplinks,
and TTN routes them to whichever application the sensor is registered in. So adding a gateway
needs no change in this repo; adding a sensor needs one entry in `ingest/config.py`.

## What is already set up (once per project)

| Where | Setting | Value |
|---|---|---|
| TTN console (nam1) | Application | `my-tracker-320` ("Temperature Tester") |
| TTN, application | Message storage | Activated |
| TTN, application → API keys | Key for this site | Right: **Read application traffic (uplink and downlink)** only |
| GitHub → Settings → Secrets and variables → Actions | Variable `TTN_APP_ID` | `my-tracker-320` |
| same | Secret `TTN_API_KEY` | the key above (`NNSXS.…`, about 98 characters, two dots) |

If you move the sensors to a new application, repeat all of these in it: Message storage and
API keys are per application. Replace the key with `gh secret set TTN_API_KEY --repo RobertsLab/acantha`
and paste it at the prompt. Never paste a key into chat, an issue, or a file in the repo.

## Choosing hardware for the farm

Models checked against the makers' docs on 2026-10-27; specs and prices change, so confirm
before ordering, and always buy the **US915** version. Stick to one or two makers where you
can: Dragino nodes share the button, LED, Bluetooth config tool and decoder conventions, which
makes a fleet much easier to run.

**Only temperature plugs into the site today.** `ingest/sources/sensors.py` reads one
temperature (and battery) per node. Water level, salinity, oxygen or weather nodes will reach
TTN Message storage as soon as they're registered, but showing them needs a small extension:
another value key per node and a chart or card for it.

### Sensors

| Measure | Unit | Why it's useful on the farm | Notes |
|---|---|---|---|
| In-bag / intertidal temperature | **Dragino D20-LB** (1 probe, what we run now), **D22-LB** (2), **D23-LB** (3) | Heat stress during daytime low tides, summer mortality, spawning timing; the core of the in-bag heat flags | DS18B20 probes, -55 to 125 °C, ±0.5 °C; 1.5 m cable per probe; 20-min default interval; 8500 mAh Li-SOCl₂, up to ~5 years. The housing is IP66 (splash-proof, not submersible): mount it on a post or float above the water and run only the probes down. A D23-LB can cover three elevations or bag/sediment/air from one node. `-LS` variants add solar. |
| Water level (observed tide, surge) | **Dragino PS-LB-I** immersion pressure sensor (**PS-LS** = solar) | Checks the Lofall predictions against what actually happens in the bay; storm surge; lets exposure flags use real water levels | IP68 316 stainless probe; range set by the variant (e.g. 10 m cable, 0–10 m); one reseller listed it at about $200. Check whether the probe cable is vented; if not, correct with barometric pressure from the weather station. |
| Salinity / conductivity | **Dragino WQS-LB** (or solar **WQS-LS**) main unit + **DR-EC200** probe | Freshwater events after heavy rain (ties to the DOH rain closure watch), salinity stress | Use the **DR-EC200** (1–200,000 µS/cm, 0–70 PSU). The cheaper DR-ECK1.0 / ECK10.0 probes top out at 2,000 / 20,000 µS/cm, below seawater (~40,000–50,000). Confirm with Dragino that the EC200 is supported on the WQS before buying. Needs a fouling-cleaning schedule. |
| Dissolved oxygen, pH | Same **WQS-LB** with Dragino DO / pH probes (up to 3 probes per unit) | Low-DO events in Hood Canal; ocean acidification | Highest upkeep on the list: probes foul and drift in seawater and need regular calibration. PLAN.md's dedicated sonde (e.g. PME miniDOT) is more reliable but isn't LoRaWAN; consider it for DO if WQS probes don't hold up. |
| Weather (air temp, humidity, wind, rain, light, UV, pressure) | **Seeed SenseCAP S2120** 8-in-1 | Heat and wind for work planning; on-site rain for the closure watch; barometric correction for water level | Solar plus AA batteries. Alternative already in PLAN.md: WeatherFlow Tempest (Wi-Fi, has its own API, no gateway needed). |
| Anything with an industrial interface | **Seeed SenseCAP S2100** data logger | Lets you use a research-grade probe (Modbus RS485, analog, GPIO) over LoRaWAN | Use when a Dragino probe isn't good enough; you'll need the probe's Modbus register map to set it up. |

A sensible first deployment: D23-LB nodes across the beach at upper, mid and low elevations, one
PS-LB-I for water level, one S2120 on shore, then a WQS-LB with an EC200 probe once the basics
have run through a season.

### Gateways

The lab's indoor gateway (`sr320-indoor-01`) covers a building. For the farm you want an
**outdoor gateway mounted high** with clear line of sight over the beach:

- **RAK WisGate Edge Pro (RAK7289V2 / RAK7289CV2 with LTE):** IP67, Ethernet / Wi-Fi / LTE
  backhaul, GPS. It needs regulated 12 V DC; RAK warns that connecting a solar charger directly
  can damage it, so use RAK's battery/solar kit or a regulated supply. Check that the US915 SKU
  is in stock.
- **Dragino DLOS8N:** outdoor gateway with Wi-Fi / Ethernet and an optional 4G module. Check
  the current datasheet for the US915 version and its power input.
- **Coverage check:** a LoRaWAN field tester (e.g. RAK10701-P) shows signal at each planned
  sensor spot before you mount anything.

### Sources

- Dragino D20/D22/D23-LB: https://docs.dragino.com/docs/LoRaWAN-End-Node/temperature-humidity-sensors/d20-d22-d23-lb/
- Dragino PS-LB/LS: https://docs.dragino.com/docs/LoRaWAN-End-Node/flow-pressure-weight-sensors/ps-lb-ps-ls/
- Dragino WQS-LB: https://docs.dragino.com/docs/LoRaWAN-End-Node/air-quality-water-quality-environmental/wqs-lb/
- Dragino EC probes (ECK1.0, ECK10.0, EC200): https://docs.dragino.com/docs/Non-Wireless-Sensors/water-quality/dr-eck1.0-dr-eck10.0-ec200-ec-digital-electrode-sensor
- SenseCAP S2120: https://thepihut.com/products/sensecap-s2120-8-in-1-lorawan-weather-sensor
- SenseCAP S2100: https://wiki.seeedstudio.com/Sensor/SenseCAP/SenseCAP_Data_Logger/Data_Logger
- RAK WisGate Edge Pro: https://store.rakwireless.com/products/wisgate-edge-pro-rak7289
- Dragino DLOS8: https://dragino.com/products/lora-lorawan-gateway/item/160-dlos8.html

## Adding a gateway

1. In the TTN console (https://nam1.cloud.thethings.network/console), **Gateways → Register gateway**.
   Enter the Gateway EUI from the label and, if it has one, the claim/authentication code.
2. **Frequency plan:** `United States 902-928 MHz, FSB 2 (used by TTN)`, the same as the lab
   gateway `sr320-indoor-01`. Sensors default to sub-band 2, and a gateway on another sub-band
   won't hear them.
3. Power it up and wait for the console to show **Connected**. "Last seen" should keep updating
   every minute or so.
4. **Placement:** height and line of sight matter more than anything else. An indoor gateway
   covers a building; a mast-mounted outdoor gateway over open water can reach several km.
   On the beach, plan for solar plus battery and a cellular backhaul if there is no Wi-Fi.
5. Optional: set the gateway's status to public (gateway → General settings) so its online state
   shows on Packet Broker's mapper. The lab-status page monitors the lab gateway that way; copy
   that panel if you want the new one watched too.

Check: with a registered sensor in range, the gateway's **Live data** shows uplinks, and the
sensor's **Live data** lists the new gateway under its rx metadata.

## Adding a sensor

### 1. Register it in TTN

1. Open application `my-tracker-320` → **End devices → Register end device**.
2. Choose **Select the end device in the LoRaWAN Device Repository** and pick the brand and model
   (e.g. Dragino → D20-LB). This installs the vendor's payload decoder. Frequency plan: US915 FSB 2.
3. Enter the **DevEUI**, **JoinEUI/AppEUI** and **AppKey** from the sticker or the box.
4. **End device ID** is what the site matches on, and it can't be changed later. Pick a scheme and
   stick to it, for example `thorndyke-upper-01`, `thorndyke-mid-01`, `thorndyke-float-01`.
   If you leave the default, it's `eui-` plus the lowercase DevEUI.

### 2. Make it join and check the payload

1. Press the sensor's button for **1–3 seconds** (Dragino "ACT" button). Holding it longer than
   3 seconds resets it instead. A Dragino node lights green solidly for about 5 s after it joins.
2. In the device's **Live data**, wait for **Forward uplink data message**. "Join request" and
   "Accept join request" are not data and are not stored.
3. Open that message and note the **name of the temperature field** in the decoded payload.
   Our D20-LB reports `TempC1`; other decoders use `Temp_C1`, `TempC_DS`, `temperature`, etc.
   A value of `3276.7` or `"NULL"` means no probe on that channel.
4. In **Message storage**, the uplink should appear within a minute. If it shows in Live data but
   never in Message storage, storage is off for this application.

### 3. Add it to `ingest/config.py`

Add one entry to `SENSORS`:

```python
{"id": "thorndyke-upper-01",           # TTN end device ID, exactly
 "name": "Upper beach",                # label on the map and card
 "lat": 47.8072, "lon": -122.7372,     # WGS84, from a phone GPS is fine
 "elevation_ft": 5.0,                  # probe height, ft above MLLW (see below)
 "placement": "In-bag, upper intertidal"},
```

Optional keys:

- `"temp_field": "TempC1"` if the decoded field isn't one of the names tried by default
  (`TEMP_KEYS` in `ingest/sources/sensors.py`: `temp_c`, `TempC1`, `Temp_C1`, `TempC_DS`,
  `TempC_SHT`, `temperature`, `temp`).
- `"battery_field": "..."` likewise for battery voltage (defaults: `battery_v`, `BatV`, `Bat_V`, `battery`).

Remove entries for sensors that are retired; a listed sensor that never reports shows as "offline".

### 4. Test, then push

Locally (Python 3.9 or newer; the Anaconda `python3` 3.8 on Steven's Mac fails with
`No module named 'zoneinfo'`, use `/opt/homebrew/bin/python3.12`):

```bash
read -s TTN_API_KEY && export TTN_API_KEY
```

```bash
TTN_APP_ID=my-tracker-320 /opt/homebrew/bin/python3.12 ingest/fetch.py --only tides sensors
```

Then look at the notes (see troubleshooting below) and run `python3 serve.py` to view the page.
Commit and push `ingest/config.py`; the push triggers the workflow, or use **Actions → Fetch data
and deploy site → Run workflow**.

## Measuring `elevation_ft`

The site compares the probe height with the predicted tide at Lofall (NOAA 9445088) to flag
readings taken out of the water; the chart shades those periods. A wrong elevation doesn't change
the temperatures, only the in/out-of-water labels and the in-bag heat flags.

- **Good enough:** on a rising tide, note the time the water first covers the probe. Look up the
  predicted height at that minute on the site's Tides page or NOAA's Lofall predictions. That
  height is the probe's elevation. Average two or three tides.
- **Better:** survey it with RTK GPS against a tidal benchmark.
- Subtidal or float-mounted probes: use a negative number (e.g. `-4.0`) so they always read as submerged.
- Land or test units: use a high number (e.g. `20.0`) so they always read as exposed.

## Sensor settings worth knowing

- **Uplink interval.** The D20-LB sends every 20 minutes by default. The site calls a sensor
  "stale" after 60 minutes without an uplink and "offline" after 6 hours (`SENSOR_STALE_MIN`,
  `SENSOR_OFFLINE_MIN` in `ingest/config.py`). If you lengthen the interval, raise those too.
  Dragino sets the interval with downlink command `0x01` plus 3 bytes of seconds
  (e.g. `01 00 04 B0` = 1200 s) on any FPort; check the model's manual before sending.
- **Battery.** Reported as `battery_v` on the card. A Dragino Li-SOCl₂ pack reads about 3.6 V
  when fresh; plan replacements when it drops toward 3.3 V.
- **Fouling and mounts.** See PLAN.md risks: rugged mounts, a cleaning schedule, a spare unit.

## Limits to keep in mind

- **History is 7 days.** TTN's Message storage only keeps a short window, and the site keeps
  7 days in `sensors.json` (`SENSOR_RETENTION_DAYS`). There is no long-term archive yet; that's
  the Phase 2 database in PLAN.md. If the workflow stops running for longer than storage keeps
  data, those readings are lost.
- **Storage starts empty.** Message storage only keeps uplinks received after it was activated.
- **GitHub delays scheduled runs.** The 20-minute cron sometimes runs an hour late, so a sensor
  can briefly show "stale" on the site while it's fine in TTN.
- **Chart colors.** The card's chart cycles through 4 series colors (`SENSOR_SERIES` in
  `web/js/common.js`). Past 4 sensors, colors repeat; group sensors by site or add colors then.
- **Many sensors.** The fetch pages through storage 1000 uplinks at a time, so volume isn't a
  problem: 20 sensors at 20-minute intervals is about 1,440 uplinks a day.

## Troubleshooting

Every fetch writes notes into `web/data/sensors.json` (`notes`), and the workflow log has one
`[ok]` or `[FAIL] sensors` line. Read them in CI with:

```bash
gh run view <run-id> --log | grep -E "\]\s+sensors|TTN HTTP"
```

| Symptom | Cause | Fix |
|---|---|---|
| `TTN HTTP 400: ... token (invalid token)` | API key is malformed: partial paste, extra text, quotes | Re-set the secret with only the `NNSXS.…` key |
| `TTN HTTP 400: ... limit_exceeded` | Request asked for too many uplinks | Fixed in code (`TTN_PAGE = 1000`); only returns if that's raised |
| `TTN HTTP 401: API key not found` | Key deleted, or from another TTN account/cluster | Make a new application key |
| `TTN HTTP 403` or `404` | Key lacks "Read application traffic", key is from another application, or `TTN_APP_ID` is wrong | Use the ID shown under the application name (`my-tracker-320`) and a key made in that application with that right |
| `TTN returned 0 uplinks` | Message storage off, just activated, or the sensor is in another application | Check Message storage lists uplinks |
| `Ignored uplinks from devices not in config.SENSORS: X` | Device ID in config doesn't match TTN | Set `id` to `X` |
| `<name>: N uplinks had no temperature (... decoded ...)` | Decoder uses another field name, probe unplugged, or no decoder | Set `temp_field`, check the probe, or pick the device from the repository |
| `<name>: offline, last seen never` and no other note | No uplinks for that device in the last 7 days | Check the sensor's Live data and gateway coverage |
| Variable not picked up in CI | Saved under another name (we once had `SENSORID` = `TTN_APP_ID = ...`) | Variable name must be exactly `TTN_APP_ID`, value just the ID |

Mock data for UI work, no hardware or key needed:

```bash
SENSORS_MOCK=1 /opt/homebrew/bin/python3.12 ingest/fetch.py --only tides sensors
```
