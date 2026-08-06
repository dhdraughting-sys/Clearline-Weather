# Clearline Weather — GitHub Actions edition

This replaces the Windows Task Scheduler version. Instead of your PC
fetching the weather every 15 minutes, **GitHub's own servers do it now** —
so it keeps running even if your PC is off, asleep, or you're away from
home for weeks. Your dashboard link doesn't change at all:
`https://dhdraughting-sys.github.io/Clearline-Weather/`

## What's different from the old version

- The weather log (`data/meriden.csv`) now lives **inside this GitHub
  repo**, not just on your PC. That's the one real tradeoff — it's still
  just your own repo, not connected to D3D or Clearline Web in any way,
  but it's no longer purely local. If that matters to you, say so and we
  can talk about alternatives (e.g. keeping a private repo instead of
  public).
- No more Task Scheduler, no more `publish.py` — GitHub Actions checks the
  repo out, runs `capture.py`, and commits+pushes the result itself.
- `weather_lib.py` and `dashboard.py` are unchanged — same data source
  (Open-Meteo), same dashboard look, same 48-hour charts.

## One-time setup (about 5 minutes)

You already have this repo cloned at `C:\Clearline Weather\publish` from
the earlier setup — that's the perfect place to drop these new files in,
since it's already connected to GitHub.

### 1. Copy these files into your existing clone

Copy everything from this delivery into `C:\Clearline Weather\publish\`,
**overwriting** anything with the same name:

```
C:\Clearline Weather\publish\
  capture.py              (replaces the old version - no more publish.py step)
  weather_lib.py
  dashboard.py
  locations.json
  data\meriden.csv         (seeded with tonight's readings so no history is lost)
  .github\workflows\capture-weather.yml
```

Note there's no `publish.py` or `.bat` file in this delivery — you don't
need them for this repo anymore (your desktop shortcut still works exactly
as before, it just opens `dashboard.html`, unrelated to this).

### 2. Push it to GitHub

Open a terminal in `C:\Clearline Weather\publish` and run:

```
git add .
git commit -m "Switch to GitHub Actions for automatic weather capture"
git push
```

### 3. Turn on Actions and check it runs

1. On the repo's GitHub page, click the **Actions** tab. If it asks you to
   confirm you want workflows enabled for this repo, click to enable them.
2. You should see a workflow called **Capture weather** in the left-hand
   list. Click it, then click **Run workflow** (top right) to trigger one
   manually right now rather than waiting up to 15 minutes.
3. After 30-60 seconds, refresh — you should see a green tick. Click into
   the run and check the log shows something like `[meriden] logged new
   reading...` with no errors.
4. Visit `https://dhdraughting-sys.github.io/Clearline-Weather/` (or just
   refresh it if already open) — it should show the freshly-captured
   reading.

From then on it runs automatically every 15 minutes, forever, with no
further action needed from you.

**Heads up:** GitHub automatically pauses *scheduled* workflows if a repo
goes completely inactive for 60 days. Since every successful run pushes a
commit, this repo stays active on its own and this shouldn't ever bite —
just mentioning it in case you ever notice it stop and wonder why. If that
ever happens, opening the Actions tab and clicking **Run workflow** once
restarts the schedule.

### 4. Turn off the old Task Scheduler task

Now that GitHub is doing this, having your PC *also* do it would cause two
separate writers pushing to the same file every 15 minutes — the pushes
would start clashing (git would just reject the second one until it pulls
first), so switch it off:

1. Open **Task Scheduler**.
2. Find **Clearline Weather Capture** in the list.
3. Right-click → **Disable** (or **Delete** if you'd rather remove it
   entirely — up to you, disabling is enough).

## Viewing it — completely unchanged

- **On your phone, anywhere:** same link as before —
  `https://dhdraughting-sys.github.io/Clearline-Weather/`. If you already
  used "Add to Home Screen," that icon still works, no changes needed.
- **On your PC:** the desktop shortcut still opens the local
  `dashboard.html` in `C:\Clearline Weather\` — but note that file is now
  only as fresh as the last time you personally ran `capture.py` by hand
  there (which you probably won't need to anymore, since the GitHub-hosted
  page is always current). If you'd rather just always use the phone/web
  link even on your PC, that's simplest — I can also remove the local
  dashboard generation entirely if you'd like, just say so.

## Adding another location

Same as before — edit `locations.json`. With more than one location this
script currently names extra dashboards `dashboard_<slug>.html` rather
than picking which one becomes the "main" `index.html` — tell me when
you're ready to add one and I'll sort out how you'd want it laid out
(e.g. a simple menu page) rather than guessing.

## Where the data comes from

Unchanged: [Open-Meteo](https://open-meteo.com/), free, no API key,
CC-BY 4.0 (explicitly permits storing results, which is exactly what this
does). Same note as before — it's Open-Meteo's best current estimate for
that latitude/longitude (blending real observations and model data), not a
physical sensor at CV7 7HT.
