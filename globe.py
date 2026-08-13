"""
Builds globe.html - a rotatable 3D Earth (drag to spin) textured with a
real satellite photo fetched daily by earth_texture.py, with your
monitored locations marked as clickable pins. One page shared by every
location, not per-location like the dashboards.

Three.js is loaded from cdnjs (a public CDN) as an ES module - the one
piece of this whole project that isn't fully self-contained, because a
WebGL globe isn't something worth hand-rolling from scratch. Everything
else (the scene setup, drag-to-rotate, the pins) is plain code below.
"""

THREE_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/0.185.1/three.module.min.js"


def _default_dashboard_path(locations):
    for loc in locations or []:
        if loc.get("slug") and loc.get("dashboard_path") == "index.html":
            return "index.html"
    return (locations[0]["dashboard_path"] if locations else "index.html")


def _texture_caption(texture_meta):
    image_date = (texture_meta or {}).get("image_date")
    if not image_date:
        return "Waiting for the first satellite image - check back after the next automatic update."
    try:
        import datetime
        d = datetime.datetime.strptime(image_date, "%Y-%m-%d")
        return "Real satellite imagery (NASA GIBS) from {} - updated once a day, not live-animated.".format(d.strftime("%d %b %Y"))
    except ValueError:
        return "Real satellite imagery (NASA GIBS), updated once a day - not live-animated."


def _pins_js(locations):
    """A small JS array literal of {name, lat, lon, url} for the inline
    script to loop over - built server-side so globe.py stays the single
    source of truth for what "your locations" means, same as every other
    page."""
    entries = []
    for loc in locations or []:
        if loc.get("lat") is None or loc.get("lon") is None:
            continue
        name = str(loc.get("name", "")).replace("\\", "\\\\").replace("'", "\\'")
        entries.append("{{name:'{name}',lat:{lat},lon:{lon},url:'{url}'}}".format(
            name=name, lat=loc["lat"], lon=loc["lon"], url=loc.get("dashboard_path", "index.html"),
        ))
    return "[" + ",".join(entries) + "]"


def _legend_html(locations):
    if not locations:
        return '<div class="no-data">No locations configured yet.</div>'
    items = []
    for loc in locations:
        items.append('<a class="globe-legend-item" href="{path}"><span class="globe-legend-dot"></span>{name}</a>'.format(
            path=loc.get("dashboard_path", "index.html"), name=loc.get("name", "—"),
        ))
    return "".join(items)


def render(locations, output_path="globe.html", texture_path="data/earth_texture.jpg", texture_meta=None):
    back_path = _default_dashboard_path(locations)
    caption = _texture_caption(texture_meta)
    pins_js = _pins_js(locations)
    legend_html = _legend_html(locations)

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cloud Globe - Clearline Weather</title>
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#0B1730">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Weather">
<style>
  :root{{ --navy:#1F3864; --navy-dark:#152747; --ink:#22303F; --muted:#5C6B7A; --bg:#FAFBFC; --white:#fff; --line:#DCE6F1; }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;padding-bottom:40px;}}
  .wrap{{max-width:900px;margin:0 auto;padding:20px 16px;}}
  .eyebrow{{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 8px;}}
  .back-link{{display:inline-block;font-size:.85rem;color:var(--navy);margin-bottom:18px;text-decoration:none;font-weight:600;}}
  .back-link:hover{{text-decoration:underline;}}
  .globe-card{{background:radial-gradient(circle at 35% 30%, #0F1E3D, #060C1C 75%);border-radius:20px;padding:18px;margin-bottom:16px;position:relative;}}
  .globe-canvas-wrap{{width:100%;max-width:520px;aspect-ratio:1/1;margin:0 auto;position:relative;touch-action:none;cursor:grab;}}
  .globe-canvas-wrap:active{{cursor:grabbing;}}
  .globe-canvas-wrap canvas{{display:block;width:100%;height:100%;}}
  .globe-status{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#AFC2E0;font-size:.85rem;text-align:center;padding:20px;pointer-events:none;}}
  .globe-hint{{text-align:center;color:#AFC2E0;font-size:.72rem;margin-top:10px;}}
  .globe-caption{{text-align:center;color:#AFC2E0;font-size:.72rem;margin-top:4px;}}
  .globe-legend{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:16px;}}
  .globe-legend-item{{display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:6px 12px;font-size:.78rem;color:#E7EEF8;text-decoration:none;}}
  .globe-legend-item:hover{{background:rgba(255,255,255,.12);}}
  .globe-legend-dot{{width:8px;height:8px;border-radius:50%;background:#F2C94C;display:inline-block;}}
  .no-data{{font-size:.85rem;color:var(--muted);padding:20px 0;text-align:center;}}
  .footer-note{{font-size:.75rem;color:var(--muted);text-align:center;margin-top:20px;}}
</style>
</head>
<body>
<div class="wrap">
  <span class="eyebrow">Personal Weather Log</span>
  <h1>Cloud Globe</h1>
  <a class="back-link" href="{back_path}">&larr; Back to current conditions</a>

  <div class="globe-card">
    <div class="globe-canvas-wrap" id="globe-canvas-wrap">
      <div class="globe-status" id="globe-status">Loading Earth imagery&hellip;</div>
    </div>
    <div class="globe-hint">Drag to rotate &middot; tap a pin to jump to that location</div>
    <div class="globe-caption">{caption}</div>
    <div class="globe-legend">{legend_html}</div>
  </div>

  <div class="footer-note">
    Satellite imagery: NASA GIBS (Earthdata, public domain) &middot; globe rendering: three.js.
  </div>
</div>
<script type="module">
import * as THREE from '{three_js_url}';

var wrap = document.getElementById('globe-canvas-wrap');
var statusEl = document.getElementById('globe-status');
var locations = {pins_js};

function setStatus(msg) {{
  if (statusEl) statusEl.textContent = msg;
}}

if (!window.WebGLRenderingContext) {{
  setStatus('Your browser does not support 3D graphics (WebGL), so the globe cannot be shown here.');
}} else {{
  function latLonToVector3(lat, lon, radius) {{
    var phi = (90 - lat) * (Math.PI / 180);
    var theta = (lon + 180) * (Math.PI / 180);
    return new THREE.Vector3(
      -radius * Math.sin(phi) * Math.cos(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta)
    );
  }}

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  // Start facing wherever your monitored locations actually are, rather
  // than an arbitrary default longitude that might show empty ocean.
  var startLat = 20, startLon = 0;
  if (locations.length) {{
    var sumLat = 0, sumLon = 0;
    locations.forEach(function (l) {{ sumLat += l.lat; sumLon += l.lon; }});
    startLat = sumLat / locations.length;
    startLon = sumLon / locations.length;
  }}
  camera.position.copy(latLonToVector3(startLat, startLon, 2.6));
  camera.lookAt(0, 0, 0);

  var renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  wrap.appendChild(renderer.domElement);

  function resize() {{
    var size = wrap.clientWidth;
    renderer.setSize(size, size, false);
    camera.aspect = 1;
    camera.updateProjectionMatrix();
  }}
  resize();
  window.addEventListener('resize', resize);

  var globeGroup = new THREE.Group();
  scene.add(globeGroup);

  var placeholder = new THREE.Mesh(
    new THREE.SphereGeometry(1, 48, 48),
    new THREE.MeshBasicMaterial({{ color: 0x1F3864 }})
  );
  globeGroup.add(placeholder);

  var loader = new THREE.TextureLoader();
  loader.load(
    'data/earth_texture.jpg',
    function (texture) {{
      texture.colorSpace = THREE.SRGBColorSpace;
      placeholder.material.map = texture;
      placeholder.material.color.set(0xffffff);
      placeholder.material.needsUpdate = true;
      setStatus('');
    }},
    undefined,
    function () {{
      setStatus('Satellite imagery not available yet - it updates once a day, check back soon.');
    }}
  );

  var pinMeshes = [];
  var pinGeometry = new THREE.SphereGeometry(0.022, 12, 12);
  var pinMaterial = new THREE.MeshBasicMaterial({{ color: 0xF2C94C }});
  locations.forEach(function (loc) {{
    var pin = new THREE.Mesh(pinGeometry, pinMaterial);
    pin.position.copy(latLonToVector3(loc.lat, loc.lon, 1.03));
    pin.userData.url = loc.url;
    pin.userData.name = loc.name;
    globeGroup.add(pin);
    pinMeshes.push(pin);
  }});

  // Manual drag-to-rotate (no OrbitControls dependency) with a bit of
  // momentum, plus a slow idle auto-rotate that pauses while you're
  // interacting with it.
  var dragging = false;
  var lastX = 0, lastY = 0;
  var velX = 0, velY = 0;
  var idleTimer = null;
  var autoRotate = true;

  function pointerPos(e) {{
    if (e.touches && e.touches.length) return {{ x: e.touches[0].clientX, y: e.touches[0].clientY }};
    return {{ x: e.clientX, y: e.clientY }};
  }}

  function onDown(e) {{
    dragging = true;
    autoRotate = false;
    clearTimeout(idleTimer);
    var p = pointerPos(e);
    lastX = p.x; lastY = p.y;
  }}
  function onMove(e) {{
    if (!dragging) return;
    var p = pointerPos(e);
    var dx = p.x - lastX, dy = p.y - lastY;
    lastX = p.x; lastY = p.y;
    velX = dx * 0.005;
    velY = dy * 0.005;
    globeGroup.rotation.y += velX;
    globeGroup.rotation.x = Math.max(-1.1, Math.min(1.1, globeGroup.rotation.x + velY));
  }}
  function onUp() {{
    dragging = false;
    idleTimer = setTimeout(function () {{ autoRotate = true; }}, 4000);
  }}

  wrap.addEventListener('mousedown', onDown);
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
  wrap.addEventListener('touchstart', onDown, {{ passive: true }});
  window.addEventListener('touchmove', onMove, {{ passive: true }});
  window.addEventListener('touchend', onUp);

  // Click/tap a pin to jump to that location's dashboard.
  var raycaster = new THREE.Raycaster();
  var pointer = new THREE.Vector2();
  wrap.addEventListener('click', function (e) {{
    var rect = wrap.getBoundingClientRect();
    pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    var hits = raycaster.intersectObjects(pinMeshes);
    if (hits.length && hits[0].object.userData.url) {{
      window.location.href = hits[0].object.userData.url;
    }}
  }});

  (function animate() {{
    requestAnimationFrame(animate);
    if (autoRotate && !dragging) {{
      globeGroup.rotation.y += 0.0015;
    }} else if (!dragging) {{
      // gentle decay of drag momentum
      velX *= 0.92; velY *= 0.92;
      globeGroup.rotation.y += velX;
      globeGroup.rotation.x = Math.max(-1.1, Math.min(1.1, globeGroup.rotation.x + velY));
    }}
    renderer.render(scene, camera);
  }})();
}}
</script>
</body>
</html>'''.format(
        back_path=back_path,
        caption=caption,
        legend_html=legend_html,
        three_js_url=THREE_JS_URL,
        pins_js=pins_js,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
