"""Photo candidates for the Industry & logistics sites, found by place (not by name).

For each site (pilsen_industry.geojson + its parcels in pilsen_industry_parcels.geojson):
  1-4  Mapillary street-level photos (CC BY-SA 4.0) taken near the site with the camera pointing AT its
       parcels; closest and most recent first, at least 40 m apart so they differ.
  5    Aerial view of the site from USGS NAIP imagery (public domain), parcels outlined in red.
Saved as harvest/candidates/<site id>/<n> - <Name> (<site id>).jpg with credits.json, and a contact
sheet harvest/index.html.

Pick one per site: copy it into harvest/picked/ (same file name), upload harvest/picked/* to
s3://perro-pilsen/assets/images/industry/, rerun curate.py.

Needs a Mapillary token in ~/.mapillary_token (or MAPILLARY_TOKEN). Without one, only the aerials are made.
Usage (from this folder): python3 harvest_images.py [site ids...] [--redo]
"""
import html, io, json, math, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw
from shapely.geometry import shape, Point, LineString
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '../../app/client/public/static/data/')
OUT = os.path.join(HERE, 'harvest')
UA = {'User-Agent': 'perro-map-site-photos/1.0'}
TOKEN = os.environ.get('MAPILLARY_TOKEN') or (open(os.path.expanduser('~/.mapillary_token')).read().strip()
                                              if os.path.exists(os.path.expanduser('~/.mapillary_token')) else None)
N_STREET = 4
NAIP = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'


def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                data = r.read()
                return data if binary else json.loads(data)
        except Exception as e:
            err = e
            time.sleep(3 * (i + 1))
    print('   ! failed:', url.split('access_token')[0][:90], err)
    return None


def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', '', s).strip()[:90]


# local metres around a point (good enough at site scale)
def to_m(lon, lat, lon0, lat0):
    return ((lon - lon0) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 110540)


def site_shapes(fid, pt, parcels):
    geoms = [shape(f['geometry']) for f in parcels if f['properties'].get('site') == fid]
    lon0, lat0 = pt
    if not geoms:
        g = Point(lon0, lat0).buffer(0.0008)
        geoms = [g]
    ll = unary_union(geoms)
    from shapely.ops import transform
    m = transform(lambda x, y, z=None: to_m(x, y, lon0, lat0), ll)
    return ll, m


def street_photos(fid, pt, ll, m):
    """Mapillary photos whose view ray (camera -> compass angle) hits the site within 250 m."""
    if not TOKEN:
        return []
    minx, miny, maxx, maxy = ll.bounds
    pad = 0.0015
    # the API wants small boxes: tile the site's box into ~0.01 deg pieces
    xs = [minx - pad + i * 0.01 for i in range(int((maxx - minx + 2 * pad) / 0.01) + 1)]
    ys = [miny - pad + j * 0.01 for j in range(int((maxy - miny + 2 * pad) / 0.01) + 1)]
    found = {}
    for x in xs:
        for y in ys:
            bbox = f'{x},{y},{min(x + 0.01, maxx + pad)},{min(y + 0.01, maxy + pad)}'
            q = urllib.parse.urlencode({'access_token': TOKEN, 'bbox': bbox, 'limit': 2000,
                                        'fields': 'id,thumb_1024_url,computed_geometry,geometry,computed_compass_angle,compass_angle,captured_at,creator,is_pano'})
            for im in (get('https://graph.mapillary.com/images?' + q) or {}).get('data', []):
                found[im['id']] = im
    lon0, lat0 = pt
    edge = m.boundary
    scored = []
    for im in found.values():
        if im.get('is_pano') or not im.get('thumb_1024_url'):
            continue
        g = (im.get('computed_geometry') or im.get('geometry') or {}).get('coordinates')
        ang = im.get('computed_compass_angle', im.get('compass_angle'))
        if not g or ang is None:
            continue
        cx, cy = to_m(g[0], g[1], lon0, lat0)
        cam = Point(cx, cy)
        if m.contains(cam):
            continue  # inside the yard: rarely a useful view
        ray = LineString([(cx, cy), (cx + 250 * math.sin(math.radians(ang)), cy + 250 * math.cos(math.radians(ang)))])
        if not ray.intersects(m):
            continue
        d = cam.distance(m)
        if d > 150 or d < 10:
            continue  # too far, or hugging the edge (under a viaduct, against a wall)
        hit = ray.intersection(m)
        # prefer: close to the site, looking at a good stretch of it, recent
        depth = hit.length if hasattr(hit, 'length') else 0
        age_years = (time.time() - im.get('captured_at', 0) / 1000) / 3.15e7
        scored.append((d / 30 - min(depth, 120) / 60 + age_years / 4, im, (cx, cy)))
    scored.sort(key=lambda t: t[0])
    out, used = [], []
    for _, im, c in scored:
        if any(math.hypot(c[0] - u[0], c[1] - u[1]) < 40 for u in used):
            continue
        used.append(c)
        out.append(dict(source='Mapillary', kind='street', url=im['thumb_1024_url'],
                        page=f"https://www.mapillary.com/app/?pKey={im['id']}",
                        author=(im.get('creator') or {}).get('username', ''), license='CC BY-SA 4.0',
                        date=time.strftime('%Y-%m-%d', time.gmtime(im.get('captured_at', 0) / 1000))))
        if len(out) >= N_STREET:
            break
    return out


def merc(lon, lat):
    return lon * 20037508.34 / 180, math.log(math.tan((90 + lat) * math.pi / 360)) * 20037508.34 / math.pi


def aerial(ll):
    """NAIP crop around the site (EPSG:3857), parcels outlined. Returns JPEG bytes."""
    minx, miny, maxx, maxy = ll.bounds
    (x0, y0), (x1, y1) = merc(minx, miny), merc(maxx, maxy)
    w, h = x1 - x0, y1 - y0
    pad = max(w, h) * 0.18 + 40
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    # 4:3 frame
    w, h = x1 - x0, y1 - y0
    if w / h < 4 / 3:
        e = (h * 4 / 3 - w) / 2; x0, x1 = x0 - e, x1 + e
    else:
        e = (w * 3 / 4 - h) / 2; y0, y1 = y0 - e, y1 + e
    W, H = 1024, 768
    q = urllib.parse.urlencode({'bbox': f'{x0},{y0},{x1},{y1}', 'bboxSR': 3857, 'imageSR': 3857,
                                'size': f'{W},{H}', 'format': 'jpg', 'f': 'image'})
    data = get(f'{NAIP}?{q}', binary=True)
    if not data or data[:2] != b'\xff\xd8':
        return None
    img = Image.open(io.BytesIO(data)).convert('RGB')
    dr = ImageDraw.Draw(img)
    polys = getattr(ll, 'geoms', [ll])
    for p in polys:
        for ring in [p.exterior] + list(p.interiors):
            pts = [((merc(a, b)[0] - x0) / (x1 - x0) * W, (y1 - merc(a, b)[1]) / (y1 - y0) * H) for a, b in ring.coords]
            dr.line(pts + [pts[0]], fill=(208, 34, 43), width=3)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
    return buf.getvalue()


def harvest(f, parcels):
    fid, name = f['id'], f['properties']['name']
    pt = f['geometry']['coordinates']
    ll, m = site_shapes(fid, pt, parcels)
    d = os.path.join(OUT, 'candidates', fid)
    os.makedirs(d, exist_ok=True)
    credits = {}
    n = 0
    for c in street_photos(fid, pt, ll, m):
        data = get(c['url'], binary=True)
        if not data:
            continue
        n += 1
        fn = f'{n} - {safe(name)} ({fid}).jpg'
        open(os.path.join(d, fn), 'wb').write(data)
        credits[fn] = c
    a = aerial(ll)
    if a:
        fn = f'5 - {safe(name)} ({fid}).jpg'
        open(os.path.join(d, fn), 'wb').write(a)
        credits[fn] = dict(source='USGS NAIP aerial imagery', kind='aerial', author='USGS / USDA', license='public domain',
                           page='https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip')
    json.dump(credits, open(os.path.join(d, 'credits.json'), 'w'), indent=1)
    return credits


def contact_sheet(feats):
    rows = []
    for f in feats:
        d = os.path.join(OUT, 'candidates', f['id'])
        p = os.path.join(d, 'credits.json')
        cr = json.load(open(p)) if os.path.exists(p) else {}
        cells = ''.join(
            f"<figure><a href='candidates/{f['id']}/{urllib.parse.quote(fn)}' target='_blank'>"
            f"<img src='candidates/{f['id']}/{urllib.parse.quote(fn)}' loading='lazy'></a>"
            f"<figcaption><b>{fn.split(' - ')[0]}</b> · {html.escape(c['source'])}{' ' + c['date'] if c.get('date') else ''}"
            f"<br><a href='{html.escape(c.get('page') or '')}' target='_blank'>{html.escape(c.get('author') or '')}</a> · {html.escape(c['license'])}</figcaption></figure>"
            for fn, c in sorted(cr.items()))
        rows.append(f"<section><h2>{html.escape(f['properties']['name'])} <small>{f['id']} · {html.escape(f['properties']['category'])}</small></h2>"
                    f"<div class='row'>{cells or '<i>nothing found</i>'}</div></section>")
    page = ("<!doctype html><meta charset='utf-8'><title>Site photo candidates</title><style>"
            "body{font:14px sans-serif;margin:16px;background:#f6f4ef}h2{font-size:16px;margin:20px 0 6px}small{color:#777;font-weight:normal}"
            ".row{display:flex;gap:8px;flex-wrap:wrap}figure{margin:0;width:260px}img{width:260px;height:195px;object-fit:cover;border-radius:4px}"
            "figcaption{font-size:11px;color:#444}</style><h1>Site photo candidates</h1>"
            "<p>1–4: Mapillary street views pointing at the site · 5: aerial, parcels outlined. Copy the one you want from "
            "<code>candidates/&lt;site&gt;/</code> into <code>picked/</code>, upload <code>picked/</code> to "
            "s3://perro-pilsen/assets/images/industry/, rerun curate.py.</p>" + ''.join(rows))
    open(os.path.join(OUT, 'index.html'), 'w').write(page)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    redo = '--redo' in sys.argv
    feats = json.load(open(DATA + 'pilsen_industry.geojson'))['features']
    parcels = json.load(open(DATA + 'pilsen_industry_parcels.geojson'))['features']
    os.makedirs(os.path.join(OUT, 'picked'), exist_ok=True)
    if not TOKEN:
        print('No Mapillary token: aerials only.')
    todo = [f for f in feats if not args or f['id'] in args]
    for n, f in enumerate(todo, 1):
        if os.path.exists(os.path.join(OUT, 'candidates', f['id'], 'credits.json')) and not redo:
            continue
        c = harvest(f, parcels)
        street = sum(1 for x in c.values() if x['kind'] == 'street')
        print(f"[{n}/{len(todo)}] {f['properties']['name']}: {street} street view(s){' + aerial' if len(c) > street else ''}", flush=True)
    contact_sheet(feats)
    print('Contact sheet:', os.path.join(OUT, 'index.html'), flush=True)


if __name__ == '__main__':
    main()
