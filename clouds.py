"""
Builds clouds.html - the "Cloud Guide" learning portal: a reference to
the ten main cloud genera, grouped by how high up they form, with:

  - a "Right now" strip that takes each location's live weather_code +
    cloud_pct (from the same Open-Meteo reading every dashboard already
    uses) and guesses which genus you're probably looking at outside,
    via classify_conditions() below - deliberately a rough, for-fun
    heuristic, not a meteorological instrument.
  - a "Cloud of the day" spotlight that rotates deterministically by UTC
    date, so it changes once a day without needing any extra state file.
  - a personal "spotted this one" checklist per cloud type, saved in the
    browser's localStorage (no account, no server - just this device),
    with a small progress bar across the top.

One page shared by every location, same pattern as globe.html.
"""

import json

# The ten WMO cloud genera, grouped by the family they form in. Altitudes
# are the typical UK/mid-latitude ranges - the same cloud sits lower in
# winter or at high latitude, higher in summer or near the tropics.
CLOUD_TYPES = [
    {
        "id": "cirrus", "name": "Cirrus", "abbr": "Ci", "family": "High cloud",
        "altitude": "5,000-13,000 m", "made_of": "Ice crystals",
        "looks_like": "Thin, wispy white streaks or filaments, sometimes hooked at one end into "
                       "“mares’ tails” by strong high-altitude wind.",
        "means": "Usually fair weather right now, but thickening, spreading cirrus is often the first "
                 "sign a warm front - and rain - is on the way in the next day or two.",
    },
    {
        "id": "cirrocumulus", "name": "Cirrocumulus", "abbr": "Cc", "family": "High cloud",
        "altitude": "5,000-13,000 m", "made_of": "Ice crystals (sometimes supercooled water)",
        "looks_like": "Small white ripples or tufts in orderly rows, giving a dappled “mackerel sky”.",
        "means": "Fair for now, but a classic sign of unsettled, changeable weather moving in.",
    },
    {
        "id": "cirrostratus", "name": "Cirrostratus", "abbr": "Cs", "family": "High cloud",
        "altitude": "5,000-13,000 m", "made_of": "Ice crystals",
        "looks_like": "A thin, milky veil covering most or all of the sky - often only obvious because it "
                       "puts a halo ring around the sun or moon.",
        "means": "Rain or snow within 12-24 hours is a common follow-up once this thickens.",
    },
    {
        "id": "altocumulus", "name": "Altocumulus", "abbr": "Ac", "family": "Middle cloud",
        "altitude": "2,000-7,000 m", "made_of": "Mostly water droplets",
        "looks_like": "Grey-white patches or rolls in clusters or lines - the classic “flock of sheep” sky.",
        "means": "Generally settled, but altocumulus on a warm, humid morning can signal thunderstorms "
                 "building later that same day.",
    },
    {
        "id": "altostratus", "name": "Altostratus", "abbr": "As", "family": "Middle cloud",
        "altitude": "2,000-7,000 m", "made_of": "Water droplets and ice crystals",
        "looks_like": "A featureless grey or blue-grey sheet across the whole sky - the sun looks like it's "
                       "behind frosted glass, no halo, no sharp shadows.",
        "means": "Usually the lead-in to a spell of continuous rain or snow, thickening from here into "
                 "nimbostratus.",
    },
    {
        "id": "nimbostratus", "name": "Nimbostratus", "abbr": "Ns", "family": "Middle cloud",
        "altitude": "Surface-3,000 m (thick, deep layer)", "made_of": "Water droplets and ice crystals",
        "looks_like": "A thick, dark grey, featureless blanket that blots out the sun completely.",
        "means": "Steady, prolonged rain or snow - the least dramatic-looking cloud, but the one that "
                 "actually soaks you all day.",
    },
    {
        "id": "stratocumulus", "name": "Stratocumulus", "abbr": "Sc", "family": "Low cloud",
        "altitude": "Surface-2,000 m", "made_of": "Water droplets",
        "looks_like": "Low, lumpy grey-and-white patches or rolls, usually with some blue sky breaking "
                       "through between them.",
        "means": "The everyday “bit cloudy” sky - generally dry, maybe the odd spot of light drizzle.",
    },
    {
        "id": "stratus", "name": "Stratus", "abbr": "St", "family": "Low cloud",
        "altitude": "Surface-2,000 m", "made_of": "Water droplets",
        "looks_like": "A flat, featureless grey layer, often low enough to sit on hilltops as mist or fog.",
        "means": "Drizzle, fine mist, or murky, dull conditions rather than heavy rain.",
    },
    {
        "id": "cumulus", "name": "Cumulus", "abbr": "Cu", "family": "Low cloud",
        "altitude": "Surface-2,000 m base (can build much higher)", "made_of": "Water droplets",
        "looks_like": "Puffy, cotton-wool clouds with a flat base and a bulging, sunlit top - the classic "
                       "“fair weather” cloud drawn in every kid's sky.",
        "means": "Fine weather while small. If they keep growing taller through the day (“cumulus "
                 "congestus”), showers or storms can follow by afternoon.",
    },
    {
        "id": "cumulonimbus", "name": "Cumulonimbus", "abbr": "Cb", "family": "Vertical cloud",
        "altitude": "Surface up to 12,000 m+ (a single towering cloud)", "made_of": "Water droplets low down, ice at the top",
        "looks_like": "A huge, dark-based tower, often flattening into a wide anvil shape at the top where "
                       "it hits the upper atmosphere.",
        "means": "Thunderstorms, heavy rain, hail, and lightning - the one cloud worth taking seriously.",
    },
]

FAMILY_ORDER = ["High cloud", "Middle cloud", "Low cloud", "Vertical cloud"]

_BY_ID = {c["id"]: c for c in CLOUD_TYPES}


def classify_conditions(weather_code, cloud_pct):
    """Rough, just-for-fun mapping from a live weather_code + cloud_pct
    reading to the cloud genus you're most likely looking at outside
    right now. Not meteorologically rigorous - real skies mix several
    genera at once - it's meant as a nudge to go outside and compare
    what you actually see against the guide, not a substitute for it.
    Returns (cloud_id_or_None, short_explanation)."""
    if weather_code is None:
        return None, "No live reading yet."
    weather_code = int(weather_code)
    cloud_pct = cloud_pct if cloud_pct is not None else 0

    if weather_code in (95, 96, 99):
        return "cumulonimbus", "Thunderstorm activity - towering cumulonimbus is almost certainly the cause."
    if weather_code == 82:
        return "cumulonimbus", "Violent rain showers usually come from a cumulonimbus cell nearby."
    if weather_code in (80, 81, 85, 86):
        return "cumulus", "Showery conditions - look for cumulus building upward into taller towers."
    if weather_code in (71, 73, 75):
        return "nimbostratus", "Continuous snow usually falls from a thick nimbostratus layer."
    if weather_code in (61, 63, 65, 51, 53, 55):
        if cloud_pct >= 85 or weather_code >= 63:
            return "nimbostratus", "Steady rain - the sky is probably a thick, featureless nimbostratus layer."
        return "stratus", "Light drizzle from a low, grey stratus layer."
    if weather_code in (45, 48):
        return "stratus", "Fog is really just stratus cloud sitting at ground level."
    if weather_code == 3:
        if cloud_pct >= 95:
            return "stratus", "Solid overcast - likely a flat, featureless stratus or altostratus sheet."
        return "stratocumulus", "Overcast but lumpy - probably stratocumulus rolls or patches."
    if weather_code == 2:
        if cloud_pct >= 50:
            return "altocumulus", "Broken mid-level patches about - keep an eye out for altocumulus “sheep”."
        return "cumulus", "Fair-weather cumulus - the classic puffy, flat-bottomed clouds."
    if weather_code == 1:
        if cloud_pct >= 15:
            return "cirrus", "Just a few wisps about - likely high, thin cirrus."
        return None, "Mostly clear - barely any cloud to spot right now."
    return None, "Clear skies here right now - a good time to check for faint high cirrus or contrails."


def _spotlight(today=None):
    """Deterministic 'cloud of the day' - rotates by UTC day-of-year, so
    it's stable all day and changes once every 24 hours without any
    extra state to track."""
    if today is None:
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc)
    doy = today.timetuple().tm_yday
    return CLOUD_TYPES[doy % len(CLOUD_TYPES)]


def _live_cards_html(live_locations):
    if not live_locations:
        return '<div class="no-data">No live readings yet - check back after the next automatic update.</div>'
    cards = []
    for loc in live_locations:
        cloud_id, note = classify_conditions(loc.get("weather_code"), loc.get("cloud_pct"))
        cloud_pct = loc.get("cloud_pct")
        cloud_pct_text = "{}% cloud cover".format(int(cloud_pct)) if cloud_pct is not None else "cloud cover unknown"
        if cloud_id and cloud_id in _BY_ID:
            guess_html = '<a class="live-guess" href="#cloud-{cid}">Likely {name} →</a>'.format(
                cid=cloud_id, name=_BY_ID[cloud_id]["name"],
            )
        else:
            guess_html = '<span class="live-guess muted">{note}</span>'.format(note=note)
        cards.append(
            '<div class="live-card">'
            '<a class="live-card-name" href="{dash}">{name}</a>'
            '<div class="live-card-meta">{cloud_pct_text}</div>'
            '{guess_html}'
            '</div>'.format(
                dash=loc.get("dashboard_path", "index.html"),
                name=loc.get("name", "—"),
                cloud_pct_text=cloud_pct_text,
                guess_html=guess_html,
            )
        )
    return "".join(cards)


def _guide_sections_html():
    by_family = {}
    for c in CLOUD_TYPES:
        by_family.setdefault(c["family"], []).append(c)

    sections = []
    for family in FAMILY_ORDER:
        entries = by_family.get(family, [])
        if not entries:
            continue
        cards = []
        for c in entries:
            cards.append('''
      <div class="cloud-card" id="cloud-{id}">
        <div class="cloud-card-head">
          <div>
            <span class="cloud-name">{name}</span>
            <span class="cloud-abbr">{abbr}</span>
          </div>
          <button class="learn-toggle" data-cloud-id="{id}" type="button">Mark as spotted</button>
        </div>
        <div class="cloud-altitude">{altitude} &middot; {made_of}</div>
        <div class="cloud-field"><strong>Look for:</strong> {looks_like}</div>
        <div class="cloud-field"><strong>Often means:</strong> {means}</div>
      </div>'''.format(
                id=c["id"], name=c["name"], abbr=c["abbr"], altitude=c["altitude"], made_of=c["made_of"],
                looks_like=c["looks_like"], means=c["means"],
            ))
        sections.append('''
    <div class="family-section">
      <h2 class="family-title">{family}</h2>
      <div class="cloud-grid">{cards}</div>
    </div>'''.format(family=family, cards="".join(cards)))
    return "".join(sections)


def _default_dashboard_path(locations):
    for loc in locations or []:
        if loc.get("dashboard_path") == "index.html":
            return "index.html"
    return (locations[0]["dashboard_path"] if locations else "index.html")


def render(locations, output_path="clouds.html", today=None):
    """locations is the same nav_locations list every page gets, except
    capture.py additionally stashes weather_code/cloud_pct onto each
    entry (when that location's fetch succeeded this run) so the "right
    now" strip has something live to work with."""
    back_path = _default_dashboard_path(locations)
    live_html = _live_cards_html(locations)
    guide_html = _guide_sections_html()
    spotlight = _spotlight(today)
    total = len(CLOUD_TYPES)

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cloud Guide - Clearline Weather</title>
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#1F3864">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Weather">
<style>
  :root{{ --navy:#1F3864; --navy-dark:#152747; --accent:#C0392B; --ink:#22303F; --muted:#5C6B7A; --bg:#FAFBFC; --white:#fff; --line:#DCE6F1; --gold:#C7960A; }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;padding-bottom:40px;}}
  .wrap{{max-width:900px;margin:0 auto;padding:20px 16px;}}
  .eyebrow{{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 8px;}}
  .back-link{{display:inline-block;font-size:.85rem;color:var(--navy);margin-bottom:6px;text-decoration:none;font-weight:600;}}
  .back-link:hover{{text-decoration:underline;}}
  .intro{{font-size:.85rem;color:var(--muted);margin-bottom:18px;}}

  .progress-card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:18px;}}
  .progress-label{{font-size:.8rem;font-weight:700;color:var(--navy);margin-bottom:8px;}}
  .progress-track{{background:var(--bg);border:1px solid var(--line);border-radius:999px;height:10px;overflow:hidden;}}
  .progress-fill{{background:linear-gradient(90deg,var(--navy),var(--gold));height:100%;width:0%;transition:width .3s ease;}}

  .card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px;}}
  .card h2{{font-size:.95rem;color:var(--navy);margin-bottom:12px;}}

  .live-strip{{display:flex;flex-wrap:wrap;gap:10px;}}
  .live-card{{flex:1 1 150px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 14px;}}
  .live-card-name{{display:block;font-size:.85rem;font-weight:700;color:var(--navy);text-decoration:none;}}
  .live-card-name:hover{{text-decoration:underline;}}
  .live-card-meta{{font-size:.72rem;color:var(--muted);margin:2px 0 8px;}}
  .live-guess{{display:inline-block;font-size:.78rem;font-weight:600;color:var(--accent);text-decoration:none;}}
  .live-guess:hover{{text-decoration:underline;}}
  .live-guess.muted{{color:var(--muted);font-weight:400;}}

  .spotlight-card{{background:linear-gradient(135deg,var(--navy),var(--navy-dark));border-radius:14px;padding:18px 20px;margin-bottom:18px;color:#fff;}}
  .spotlight-eyebrow{{font-size:.68rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#AFC2E0;}}
  .spotlight-name{{font-size:1.2rem;font-weight:700;margin:4px 0 6px;}}
  .spotlight-text{{font-size:.85rem;color:#DCE6F1;}}
  .spotlight-link{{display:inline-block;margin-top:8px;font-size:.78rem;color:#fff;font-weight:700;text-decoration:none;border-bottom:1px solid rgba(255,255,255,.5);}}

  .family-section{{margin-bottom:8px;}}
  .family-title{{font-size:.85rem;color:var(--navy);text-transform:uppercase;letter-spacing:.04em;margin:22px 0 10px;}}
  .cloud-grid{{display:grid;grid-template-columns:1fr;gap:12px;}}
  @media (min-width:640px){{ .cloud-grid{{grid-template-columns:repeat(2,1fr);}} }}
  .cloud-card{{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:14px 16px;scroll-margin-top:16px;}}
  .cloud-card.learned-highlight{{border-color:var(--gold);}}
  .cloud-card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:4px;}}
  .cloud-name{{font-size:.95rem;font-weight:700;color:var(--navy);}}
  .cloud-abbr{{font-size:.68rem;color:var(--muted);margin-left:6px;}}
  .cloud-altitude{{font-size:.72rem;color:var(--muted);margin-bottom:8px;}}
  .cloud-field{{font-size:.8rem;color:var(--ink);margin-top:6px;}}
  .cloud-field strong{{color:var(--navy);}}
  .learn-toggle{{flex-shrink:0;background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:5px 10px;font-size:.68rem;font-weight:700;color:var(--navy);cursor:pointer;white-space:nowrap;}}
  .learn-toggle.learned{{background:var(--navy);border-color:var(--navy);color:#fff;}}

  .no-data{{font-size:.85rem;color:var(--muted);padding:16px 0;text-align:center;}}
  .footer-note{{font-size:.75rem;color:var(--muted);text-align:center;margin-top:20px;}}
</style>
</head>
<body>
<div class="wrap">
  <span class="eyebrow">Personal Weather Log</span>
  <h1>Cloud Guide</h1>
  <a class="back-link" href="{back_path}">&larr; Back to current conditions</a>
  <div class="intro">The ten main cloud types, what they look like, and what they usually mean - plus a guess at what's over each of your locations right now.</div>

  <div class="progress-card">
    <div class="progress-label" id="progress-label">0 of {total} cloud types logged</div>
    <div class="progress-track"><div class="progress-fill" id="progress-bar"></div></div>
  </div>

  <div class="spotlight-card">
    <div class="spotlight-eyebrow">Cloud of the day</div>
    <div class="spotlight-name">{spot_name} ({spot_abbr})</div>
    <div class="spotlight-text">{spot_looks}</div>
    <a class="spotlight-link" href="#cloud-{spot_id}">Read more below &darr;</a>
  </div>

  <div class="card">
    <h2>Right now at your locations</h2>
    <div class="live-strip">{live_html}</div>
  </div>

  {guide_html}

  <div class="footer-note">
    Live guesses are a rough, for-fun heuristic from each location's current weather code and cloud cover -
    always trust your own eyes over the algorithm. Spotted checkmarks are saved only on this device.
  </div>
</div>
<script>
(function () {{
  var KEY = 'clearline_clouds_learned_v1';
  var total = {total};
  function loadLearned() {{
    try {{
      var raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    }} catch (e) {{ return []; }}
  }}
  function saveLearned(arr) {{
    try {{ localStorage.setItem(KEY, JSON.stringify(arr)); }} catch (e) {{ /* private mode etc - ok to lose it */ }}
  }}
  var learned = loadLearned();

  function updateProgress() {{
    var bar = document.getElementById('progress-bar');
    var label = document.getElementById('progress-label');
    var pct = total ? Math.round((learned.length / total) * 100) : 0;
    if (bar) bar.style.width = pct + '%';
    if (label) label.textContent = learned.length + ' of ' + total + ' cloud types logged';
  }}

  var toggles = document.querySelectorAll('.learn-toggle');
  for (var i = 0; i < toggles.length; i++) {{
    (function (btn) {{
      var id = btn.getAttribute('data-cloud-id');
      var cardEl = document.getElementById('cloud-' + id);
      function refresh() {{
        var on = learned.indexOf(id) !== -1;
        btn.classList.toggle('learned', on);
        btn.textContent = on ? '\\u2713 Spotted this one' : 'Mark as spotted';
        if (cardEl) cardEl.classList.toggle('learned-highlight', on);
      }}
      refresh();
      btn.addEventListener('click', function () {{
        var idx = learned.indexOf(id);
        if (idx === -1) learned.push(id); else learned.splice(idx, 1);
        saveLearned(learned);
        refresh();
        updateProgress();
      }});
    }})(toggles[i]);
  }}
  updateProgress();
}})();
</script>
</body>
</html>'''.format(
        back_path=back_path,
        total=total,
        live_html=live_html,
        guide_html=guide_html,
        spot_name=spotlight["name"],
        spot_abbr=spotlight["abbr"],
        spot_looks=spotlight["looks_like"],
        spot_id=spotlight["id"],
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
