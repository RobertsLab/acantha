# Phone alerts

The portal can push a notification to your phone when a condition starts that may need farm
action. Alerts go through [ntfy](https://ntfy.sh), a free push service: no account, no phone
number, just an app and a topic name.

## Subscribing (growers)

1. Install the **ntfy** app from the App Store or Google Play
   ([links and details](https://docs.ntfy.sh/subscribe/phone/)).
2. Tap **+** (subscribe to topic), enter the topic name the farm gave you, and keep the
   server as `ntfy.sh`.
3. Allow notifications. Tapping an alert opens the portal.

To stop, unsubscribe from the topic in the app.

## What sends an alert

Alerts use fixed rules against the page's default thresholds (`DEFAULT_THRESHOLDS` in
`ingest/config.py`), not a model and not each viewer's own settings.

| Alert | When |
|---|---|
| NWS alert | A new weather or marine alert for the bay or zone PZZ135 |
| DOH status | The Thorndyke Bay recreational biotoxin zone or the Hood Canal #1 growing-area status changes (including reopening) |
| Rain watch | Observed past 24 h + forecast next 24 h reaches 60% of the rain threshold, then the threshold |
| Heat exposure | A workable daylight low in the next 3 days with forecast air temp at or above the heat threshold |
| Gusts | Forecast gusts at or above the gust threshold in the next 24 h (at most one per day) |
| Farm sensor | An exposed probe at or above the heat threshold, or a sensor going offline |

- Each alert is sent once when its condition starts, and again only after it has cleared and
  come back, and never twice within 12 hours (`NOTIFY_COOLDOWN_HOURS`).
- Quiet hours are 9 pm to 6 am (`NOTIFY_QUIET_HOURS`). Overnight, only NWS alerts and DOH
  changes are sent; anything else goes out in the morning if it still holds.
- The workflow runs about every 20 minutes, but GitHub can start it 5–30 minutes late. Alerts
  are for planning, not emergencies.
- The last 30 alerts are listed in [`data/notify.json`](https://robertslab.github.io/acantha/data/notify.json).

## Setup (maintainers)

1. Pick a long, hard-to-guess topic name, e.g. `acantha-thorndyke-` plus random characters.
   On ntfy.sh anyone who knows the name can read or post to it, so treat it like a password
   and share it only with growers. For a protected topic, reserve it with an ntfy account
   and add an access token as the `NTFY_TOKEN` secret.
2. Add it as the `NTFY_TOPIC` repository secret (**Settings → Secrets and variables → Actions**).

Without `NTFY_TOPIC` the alerts are still computed and logged in `notify.json`, marked
`"delivered": false`, but nothing is sent. The first run after setup records the conditions
that already hold and sends nothing, so subscribing doesn't start with a burst of old news.
