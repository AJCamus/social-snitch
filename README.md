# Social Snitch 📡

A little Python watchdog that polls your socials for new comments and tells you
which ones actually need you — so you can stay responsive to fans (and haters)
without living inside the apps.

## What it watches

- Your **Facebook Page** posts (recent 10)
- Your **personal Facebook** timeline posts (recent 5)
- Your **Instagram** posts (recent 10)

## What it tells you

Every new comment gets sorted into one of three buckets:

| Bucket | What lands here |
|---|---|
| **NEEDS YOU** | Questions, long comments, genuine conversation |
| **HATER PLAYS** | Negativity, dunk-bait — pre-sorted for your reply strategy |
| **NOISE** | Likes, emoji-only, low-key reactions (counted, not shown) |

The digest prints with tap-to-open links that jump straight to the comment on
your phone. Silence means silence — no new action, no notification.

## Setup

Needs the CLIs this was built against (`facebook-cli`, `instagram-cli`), or
adapt the `fb_comments_on` / `ig_comments_on` harvesters to your own API access.

```bash
cp config.example.json config.json   # set your page/profile IDs
python3 snitch.py --force            # test run, ignores the interval gate
```

## Scheduling

`config.json` holds the dial:

```json
{
  "interval_minutes": 5,
  "quiet_until": null
}
```

- `interval_minutes` — how often it may report (2 minutes to 3 days)
- `quiet_until` — ISO timestamp; the snitch stays silent until then (weekends!)

Run it on a cron/scheduler at your smallest granularity; the script gates
itself on `interval_minutes` and exits quietly when there's nothing new.
`state.json` tracks seen comment IDs so nothing double-reports.

Built by A.J. Camus & Ember — the first in a series of little tools.
