"""Industrial & logistics sites in Pilsen + 1 mile -> GeoJSON points + overview HTML for PERRO."""
import geopandas as gpd, pandas as pd, json, html, warnings, sys
warnings.filterwarnings('ignore')
OUT = sys.argv[1]
ICON_URL = './static/data/icons/'  # as seen from the app page
s = gpd.read_file('sites_all.gpkg')
s = s[s.ha >= 2].copy()

LU = {1420: 'General industrial (under 100,000 sq ft)', 1431: 'Manufacturing / processing (100,000+ sq ft)',
      1432: 'Warehousing / distribution (100,000+ sq ft)', 1433: 'Flex or mixed industrial (100,000+ sq ft)',
      1450: 'Storage', 1511: 'Rail right-of-way', 1520: 'Transportation yards & terminals',
      1570: 'Intermodal (rail–truck) facility', 1564: 'Utility / waste facility',
      1330: 'Government services & public works'}

CATS = {  # key: (label, colour)
    'rail': ('Rail yards, lines & intermodal', '#7b3294'),
    'yards': ('Truck & bus yards', '#e66101'),
    'scrap': ('Scrap, waste & building materials', '#8c510a'),
    'manufacturing': ('Manufacturing & processing', '#c51b7d'),
    'warehousing': ('Warehousing & food distribution', '#2166ac'),
    'utilities': ('Power & utilities', '#01665e'),
    'municipal': ('City & postal logistics', '#4d4d4d'),
}

DROP = {39, 161, 288, 332, 339, 340, 342, 635, 629}
MERGE = {'bnsf': [470, 497, 493], 'upcanal': [400, 404, 405], 'amtrak': [542, 544, 543],
         'bnsf14': [547, 546], 'schulze': [72, 71], 'cinespace': [216, 223]}
NAME = {  # index: (name, category or None to keep)
    111: ('Prairie Material & Republic Recycling area', 'scrap'),
    128: ('Sims Metal Management', 'scrap'),
    157: ('Republic Services', 'scrap'), 107: ('Republic Services yard', 'scrap'),
    45: ('Ozinga ready-mix concrete', 'scrap'), 101: ('Illinois Brick Company', 'scrap'),
    345: ('Lakeshore Recycling & City Fleet Management shop', 'municipal'),
    61: ('Chicago Scenic Studios & AT&T', None), 126: ('QTS Chicago data center', None),
    252: ("Kellogg's / Ferrara Candy", None), 173: ('Domino Foods & Chefs Warehouse', None),
    149: ('Banner Wholesale Grocers & Heidler Hardwood Lumber', None), 27: ('Chinatown wholesale market', 'warehousing'),
    140: ('East Balt bakery', None), 37: ('Sanchem, Inc.', None), 102: ('Industrial site (Marz Community Brewing)', None),
    98: ('H. Kramer and Company (brass & bronze smelter)', None), 169: ('Kehoe Design', None),
    306: ('USPS Chicago processing & distribution center', None), 307: ('USPS vehicle maintenance facility', None),
    319: ('Streets & Sanitation garage, Water Management & Fleet fuel station', None),
    323: ('Bureau of Electricity & Water Pipe Extension yard', None),
    351: ('Metra Electric 18th Street (Weldon) Yard', None), 432: ('Rail embankment along 16th Street', None),
    505: ('Rail junction (CP Brighton)', None), 500: ('Rail junction (CP Brighton / CP Pershing)', None),
    491: ('Rail lines near Western Ave & 26th St', None),
    558: ('Bus & food-truck storage yard', None), 583: ('Brighton Park maintenance facility', None),
    575: ('Illinois Central School Bus', None), 600: ('Fisk Generating Station (closed)', None),
    604: ('Utility site', None), 595: ('ComEd transfer yard', None), 599: ('UIC cogeneration & utilities plant', None),
    646: ('Anthony Marano Co. produce', None), 649: ('Chicago International Produce Market', None),
    656: ('Amazon DCH1 delivery station & Swift Intermodal', None), 626: ('UPS Chicago hub', None),
    638: ('Pepsi bottling plant', None), 645: ('Bataglia Distribution & Chicago Yacht Works', None),
    647: ('Preferred Freezer Services', None), 655: ('Preferred Freezer Services', None),
    648: ('FedEx distribution', None), 657: ('Frozen Assets cold storage', None),
    662: ('Concordance Healthcare Solutions', None), 72: ('Schulze & Burch Biscuit Co. & Bubbly Dynamics', None),
    216: ('Cinespace film studios (former Ryerson steel)', None), 15: None,
}
MERGE_NAME = {'bnsf': ('BNSF Western Avenue intermodal yard', None), 'upcanal': ('Union Pacific Canal Street yard', None),
              'amtrak': ('Amtrak Chicago car yard & 16th Street diesel shop', 'rail'),
              'bnsf14': ('BNSF 14th Street coach yard', 'rail'), 'schulze': NAME[72], 'cinespace': NAME[216]}

HIGHLIGHTS = {  # key -> short "why it matters"
    600: "Coal-fired power plant on Cermak Road, closed in 2012 after a long campaign by PERRO and its allies. "
         "What it left behind, from coal dust to metals in the soil, is still a neighbourhood question; see the Lead Testing layer.",
    128: "Large metal shredder and scrap yard on the river. Shredding throws off metal-laden dust and has caused fires and "
         "explosions; it is a long-running focus of PERRO's air monitoring (see the 'Fisk and SIMS' layer).",
    'bnsf': "Container yard where freight trains hand off to trucks: diesel locomotives, cranes and a steady stream of "
            "trucks on Western and Blue Island Avenues.",
    626: "Parcel-sorting hub next to the river. Very large daily truck volumes on Roosevelt Road, Canal and Jefferson.",
    649: "Wholesale produce market. Refrigerated trucks come and go around the clock and run diesel cooling units while parked.",
    656: "Last-mile delivery station: hundreds of delivery vans in and out every day, beside a trucking yard.",
    126: "Data centre in a former newspaper printing plant. Very high electricity demand, backed up by banks of diesel "
         "emergency generators.",
    'amtrak': "Passenger-rail yards south of Union Station, where diesel locomotives are serviced and left idling.",
    157: "Waste-hauling and recycling operation: garbage trucks, sorting and the dust and noise that go with it.",
    345: "Private recycling operation next to the City's fleet repair shop: heavy trucks and waste handling.",
    319: "City Streets & Sanitation garage with Water Management and a fleet fuel station: a municipal truck hub.",
    45: "Ready-mix concrete plant on the river: cement dust and a constant flow of mixer trucks.",
}

rows = []
used = set()
def add(key, idx_list, name_cat):
    part = s.loc[[i for i in idx_list if i in s.index]]
    if part.empty: return
    big = part.sort_values('ha').iloc[-1]
    name, cat = name_cat if name_cat else (None, None)
    names = '; '.join(x for x in part.names.dropna().tolist())
    rows.append(dict(key=key, cat=cat or big['cat'], code=int(big['code']), ha=part.ha.sum(),
                     name=name or (big['name'] if isinstance(big['name'], str) else None),
                     osm=names, geometry=part.geometry.union_all() if len(part) > 1 else big.geometry))
    used.update(idx_list)

for k, ids in MERGE.items():
    add(k, ids, MERGE_NAME[k])
for i, r in s.iterrows():
    if i in used or i in DROP: continue
    add(i, [i], NAME.get(i))

d = gpd.GeoDataFrame(rows, crs=s.crs)
d.loc[d['cat'] == 'trucking', 'cat'] = 'yards'
d.loc[d['name'].isna() & (d['cat'] == 'rail'), 'name'] = 'Rail right-of-way'
d.loc[d['name'].isna(), 'name'] = d['code'].map(lambda c: LU[c].split(' (')[0] + ' site')
d['key_s'] = d.key.astype(str)
d[['key_s', 'name', 'cat', 'code', 'ha', 'geometry']].to_file('sites_curated.gpkg')
pts = d.geometry.representative_point()
d['acres'] = d.ha * 2.471
ll = gpd.GeoSeries(pts, crs=s.crs).to_crs(4326)

def esc(x): return html.escape(str(x))

# ---------- key information per site (from enrich.py -> enrich.json; images reviewed by hand) ----------
import os, re, subprocess, urllib.parse
ENR = json.load(open('enrich.json')) if os.path.exists('enrich.json') else {'sites': {}, 'wikidata': {}}
PHOTOS = json.load(open('images.json')) if os.path.exists('images.json') else {}
# Reviewed photos (Wikimedia Commons file names) per site key; see commons.py for finding candidates.
from curate_images import IMAGES  # reviewed photos per site key
# Photos picked from harvest_images.py: harvest/picked/<n> - <Name> (<site id>).jpg, uploaded to S3_IMAGES
S3_IMAGES = 'https://perro-pilsen.s3.us-east-2.amazonaws.com/assets/images/industry/'
def picked_photos():
    out = {}
    pdir = os.path.join('harvest', 'picked')
    if not os.path.isdir(pdir):
        return out
    for fn in sorted(os.listdir(pdir)):
        m = re.search(r'\((ind-[^)]+)\)\.\w+$', fn)
        if not m:
            continue
        cr = os.path.join('harvest', 'candidates', m.group(1), 'credits.json')
        c = json.load(open(cr)).get(fn, {}) if os.path.exists(cr) else {}
        out[m.group(1)] = dict(c, source=c.get('source', 'photo'), s3=S3_IMAGES + urllib.parse.quote(fn))
    return out
PICKED = picked_photos()
ACTIVITY = {'600': 'Former coal-fired power plant (closed 2012)', '128': 'Scrap metal recycling (metal shredder)',
            'bnsf': 'Rail–truck intermodal container terminal', '626': 'Parcel sorting hub',
            '649': 'Wholesale produce market', '656': 'Package delivery station; trucking yard', '126': 'Data center',
            'amtrak': 'Passenger-car yard & locomotive shop', 'bnsf14': 'Passenger-car (coach) yard',
            '157': 'Waste hauling & recycling', '107': 'Waste hauling yard', '345': 'Waste transfer & recycling; city fleet repair',
            '319': 'City vehicle garage & fueling', '45': 'Ready-mix concrete plant', '111': 'Building materials & recycling',
            'upcanal': 'Rail yard', '351': 'Commuter-rail yard', '306': 'Mail processing & distribution',
            '307': 'Postal vehicle maintenance', '638': 'Beverage bottling & distribution', '101': 'Brick & masonry supply'}
WEBSITES = {'128': 'https://www.simsmm.com', '157': 'https://www.republicservices.com', '107': 'https://www.republicservices.com',
            '45': 'https://ozinga.com', 'amtrak': 'https://www.amtrak.com', 'upcanal': 'https://www.up.com',
            '319': 'https://www.chicago.gov/city/en/depts/streets.html', '656': 'https://www.amazon.com',
            '306': 'https://www.usps.com', '307': 'https://www.usps.com', '351': 'https://metra.com',
            # found by web search (company pages or trade press), Nov 2026
            'cinespace': 'https://cinespace.com/location/cinespace-chicago', '645': 'https://battagliafoods.com',
            '646': 'https://anthonymarano.com', '647': 'https://www.onelineage.com', '655': 'https://www.onelineage.com',
            # Wikidata / well-known company domains
            '252': 'https://www.ferrarausa.com', '98': 'https://hkramer.com', '173': 'https://www.dominosugar.com',
            '595': 'https://www.comed.com', '604': 'https://www.comed.com', '432': 'https://www.up.com',
            '500': 'https://www.cn.ca', '505': 'https://www.cn.ca'}
OSM_ACT = {('power', 'plant'): 'Power plant', ('railway', 'yard'): 'Rail yard', ('railway', 'junction'): 'Rail junction',
           ('industrial', 'depot'): 'Depot', ('industrial', 'bakery'): 'Industrial bakery', ('industrial', 'foundry'): 'Foundry',
           ('industrial', 'asphalt_plant'): 'Asphalt plant', ('product', 'bricks'): 'Bricks', ('product', 'candy'): 'Candy',
           ('product', 'food'): 'Food', ('craft', 'window_construction'): 'Window manufacturing'}
ZONE_KIND = [('PMD', 'Planned Manufacturing District'), ('PD', 'Planned Development'), ('M', 'Manufacturing'),
             ('C', 'Commercial'), ('B', 'Business'), ('DS', 'Downtown Service'), ('D', 'Downtown'), ('R', 'Residential'),
             ('POS', 'Parks & Open Space'), ('T', 'Transportation')]
ORG = re.compile(r'\b(LLC|L\.L\.C|INC|CORP|CO|COMPANY|LP|LTD|TRUST|BANK|CITY|DIST|AUTHOR|RAILROAD|RAILWAY|RR|PROP|PROPERTIES|ASSOC|'
                 r'SERVICES?|DEPT|MGMT|MANAGEMENT|PARTNERS|HOLDINGS|GROUP|WASTE|TRANSPORTATION|BOARD|STATE|COUNTY|UNIV|'
                 r'UNIVERSITY|CHURCH|FUND|ENTERPRISES|INDUSTRIES|REALTY|INVEST\w*|DEVELOPMENT|TAX|USPS|POSTAL|METRA|AMTRAK|'
                 r'COMED|EDISON|GENERATION|READY|MIX|MARKET|FOODS?|STORAGE|LOGISTICS|PARTNERSHIP|VENTURES|CTR|CENTER)\b')

def norm(n):
    n = re.sub(r"[^a-z0-9 ]", " ", str(n).lower().replace('&', ' and '))
    return ' '.join(w for w in n.split() if w not in ('inc', 'llc', 'co', 'company', 'corp', 'corporation', 'the', 'ltd', 'lp'))

def city_websites():
    """Named OSM features with a website anywhere in Chicago (osm_city_websites.csv) -> {normalised name/brand/operator: url}."""
    out = {}
    if not os.path.exists('osm_city_websites.csv'):
        return out
    for _, r in pd.read_csv('osm_city_websites.csv').iterrows():
        t = dict(re.findall(r'"([^"]+)"=>"((?:[^"\\]|\\.)*)"', str(r.other_tags)))
        url = next((t[k] for k in ('website', 'contact:website', 'url', 'operator:website', 'brand:website') if t.get(k)), None)
        if not url:
            continue
        for key in (r['name'], t.get('brand'), t.get('operator')):
            if key and norm(key) and norm(key) not in out:
                out[norm(key)] = url
    return out
CITY_WEB = city_websites()

def class_labels():
    try:
        txt = subprocess.run(['pdftotext', '-layout', '/media/brian/Legacy/chicago_geology/geojson_sources/Class_codes_definitions_12.16.24_0.pdf', '-'],
                             capture_output=True, text=True).stdout
    except Exception:
        return {}
    return {a + b: lab.strip() for a, b, lab in re.findall(r'\b(\d)-(\d\d)\s+(\S.*)', txt)}
CLASS = class_labels()

FIX = {'CHICAGO TRANSIT AUTHOR': 'Chicago Transit Authority', 'UP': 'Union Pacific', 'CN': 'Canadian National', 'NS': 'Norfolk Southern'}
UPPER = {'RTA', 'LLC', 'INC', 'LP', 'LTD', 'II', 'III', 'USA', 'CTA', 'USPS', 'UPS', 'UIC', 'BNSF', 'RE', 'EME', 'QTS'}
def nice(n):
    n = FIX.get(n.strip().upper(), n.strip())
    words = [w.upper() if re.sub(r'\W', '', w.upper()) in UPPER else (w.capitalize() if w.isupper() or w.islower() else w) for w in n.split()]
    return ' '.join(words).replace('Comed', 'ComEd')

def owner_label(n):
    if n.strip().upper() == 'RAILROAD':
        return 'Railroad (state-assessed rail property)'
    return nice(n) if ORG.search(n.upper()) else 'Private owner'

def zoning_label(z):
    for pre, kind in ZONE_KIND:
        if re.match(rf'^{pre}[\s\-\d]', z + ' '):
            return f'{z} ({kind})'
    return z

def row(label, value):
    return f"<tr><th style='text-align:left;vertical-align:top;padding:4px 10px 4px 0;white-space:nowrap'>{label}</th><td style='padding:4px 0'>{value}</td></tr>"

def key_info(r, cat_label):
    k = str(r.key)
    e = ENR['sites'].get(k, {})
    wd = ENR['wikidata']
    osm = e.get('osm', [])
    # operator / chief tenant: OSM operator tags first, then the names of the site's significant OSM features.
    # Each candidate carries its own website (OSM tag, or Wikidata P856 of its operator/brand).
    SIGNIF = ('operator', 'industrial', 'landuse', 'power', 'railway', 'shop', 'office', 'craft', 'amenity', 'product', 'man_made', 'brand')
    # Priority: 0 operator of the site's own (namesake) feature, 1 namesake feature name, 2 other operators, 3 other names.
    words = lambda x: set(re.findall(r'[a-z0-9]{2,}', x.lower())) - {'chicago', 'street', 'the', 'and', 'site', 'co', 'inc', 'of', 'llc'}
    site_words = words(r['name'])
    cands = []
    for c in osm:
        t = c['tags']
        site_web = next((t[wk] for wk in ('website', 'operator:website', 'brand:website', 'contact:website', 'url') if t.get(wk)), None)
        q = t.get('operator:wikidata') or t.get('brand:wikidata')
        op_web = wd.get(q, {}).get('website') if q else None
        namesake = bool(c['name']) and len(words(c['name']) & site_words) >= min(2, len(words(c['name'])))
        if t.get('operator'):
            cands.append((0 if namesake else 2, nice(t['operator']), op_web or site_web))
        if c['name'] and (c.get('building') or any(x in t for x in SIGNIF)) and not (namesake and t.get('operator')):
            cands.append((1 if namesake else 3, c['name'], site_web or op_web))
    if any(c[0] == 0 for c in cands):  # operator known: don't repeat the site's own name
        cands = [c for c in cands if c[0] != 1]
    cands = [(n, w) for _, n, w in sorted(cands, key=lambda c: c[0])]
    tenants, webs = [], {}
    for n, w in cands:
        low = n.lower()
        same = next((x for x in tenants if low in x.lower() or x.lower() in low), None)
        if same:
            webs[same] = webs.get(same) or w
            continue
        tenants.append(n); webs[n] = w
    tenant = ', '.join(tenants[:2]) or '—'
    web = WEBSITES.get(k) or (webs.get(tenants[0]) if tenants else None)
    if not web:  # same business elsewhere in Chicago (OSM)
        web = next((CITY_WEB[norm(n)] for n in tenants + [r['name']] if norm(n) in CITY_WEB), None)
    web_html = f"<a href='{esc(web)}' target='_blank' rel='noopener'>{esc(re.sub(r'^https?://(www\.)?', '', web).rstrip('/'))}</a>" if web else '—'
    # activity
    act = ACTIVITY.get(k)
    if not act:
        found = [OSM_ACT[(t, v)] for c in osm for t, v in c['tags'].items() if (t, v) in OSM_ACT]
        act = '; '.join(dict.fromkeys(found)) or LU[r['code']].split(' (')[0]
    cls = CLASS.get(e.get('assessor_class', ''), '')
    # owners
    owners = list(dict.fromkeys(owner_label(n) for n in e.get('owners', [])))[:2]
    owner_html = '<br>'.join(esc(o) for o in owners) or '—'
    if e.get('n_parcels', 0) > 1:
        owner_html += f"<br><span style='opacity:.7;font-size:90%'>{e['n_parcels']} parcels; largest owners shown</span>"
    zoning = ', '.join(zoning_label(z) for z in e.get('zoning', [])) or '—'
    # building
    b = e.get('bldg')
    btype, stories = '—', '—'
    if b:
        specific = b['typology'] in ('Light Industrial (Metal Bldg)', 'Distribution / Warehouse (Tilt-Up Concrete)', 'Loft Industrial (Prewar)',
                                     'Parking Garage', 'Postwar Commercial Block', 'Civic / Government / Institutional')
        osm_b = next((c['building'] for c in osm if c.get('building') and c['building'] not in ('yes', 'roof')), None)
        base = b['typology'] if specific else (f"{osm_b.capitalize()} building" if osm_b else 'Large building')
        extra = [f"built {b['year']}" if b.get('year') else None, f"~{b['sqft']:,} sq ft footprint",
                 f"{b['n']} buildings on site" if b.get('n', 0) > 1 else None]
        btype = esc(base) + '<br><span style="opacity:.7;font-size:90%">' + esc(', '.join(x for x in extra if x)) + (f'; assessor class: {esc(cls)}' if cls else '') + '</span>'
        h = b.get('height_m')  # NB: enrich.py's 'height_m' holds the footprint file's height, which is in feet
        stories = (str(b['stories']) if b.get('stories') else 'not recorded') + (f' (building about {h:.0f} ft tall)' if h else '')
    # image: a photo picked from the harvest (uploaded to S3) first, else a reviewed Commons photo
    img = ''
    f = IMAGES.get(k)
    pk = PICKED.get(f'ind-{k}')
    if pk:
        ph = pk
        credit = f"{esc(ph['source'].split(' /')[0])}: {esc(ph.get('author') or 'unknown')}, {esc(ph.get('license') or '')}"
        img = (f"<a href='{esc(ph.get('page') or ph['s3'])}' target='_blank' rel='noopener'><img src='{esc(ph['s3'])}' alt='{esc(r['name'])}' "
               f"style='width:100%;border-radius:4px;display:block'></a><div style='font-size:80%;opacity:.7;margin:2px 0 10px'>Photo: {credit}</div>")
    elif f and f in PHOTOS:
        ph = PHOTOS[f]
        credit = f"{esc(ph['artist'] or 'Wikimedia Commons')}, {esc(ph['license'])}"
        img = (f"<a href='{esc(ph['page'])}' target='_blank' rel='noopener'><img src='{esc(ph['thumb'])}' alt='{esc(r['name'])}' "
               f"style='width:100%;border-radius:4px;display:block'></a><div style='font-size:80%;opacity:.7;margin:2px 0 10px'>Photo: {credit}</div>")
    rows = ''.join([row('Name', f"<b>{esc(r['name'])}</b>"),
                    row('Category', f"<img src='{ICON_URL}ind-{r['cat']}.svg' width='18' height='18' alt='' style='vertical-align:-4px;margin-right:4px'>{esc(cat_label)}"),
                    row('Parcel owner', owner_html), row('Activity', esc(act)), row('Operator / chief tenant', esc(tenant)),
                    row('Website', web_html), row('Zoning', esc(zoning)), row('Building type', btype), row('Stories', esc(stories))])
    return (img + f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{rows}</table>"
            "<p style='font-size:80%;opacity:.75;margin-top:10px'>Sources: CMAP Land Use Inventory 2020; Cook County Assessor (taxpayer of record); "
            "City of Chicago zoning and building footprints; OpenStreetMap; Wikidata.</p>"
            "<p><a href='#' data-overlay-back>&larr; All industry &amp; logistics</a></p>")
feats = []
for (i, r), p in zip(d.iterrows(), ll):
    label, colour = CATS[r['cat']]
    fid = f'ind-{r.key}'
    why = HIGHLIGHTS.get(r.key)
    others = [n for n in pd.unique([x.strip() for x in (r.osm or '').split(';') if x.strip()]) if n.lower() not in r['name'].lower()][:5]
    detail = key_info(r, label)
    icon_scale = 0.55 if r.ha < 5 else 0.68 if r.ha < 12 else 0.8  # of the 32 px icon
    feats.append({'type': 'Feature', 'id': fid,
                  'geometry': {'type': 'Point', 'coordinates': [round(p.x, 6), round(p.y, 6)]},
                  'properties': {'fid': fid, 'name': r['name'], 'category': label, 'color': colour, 'icon': f"{ICON_URL}ind-{r['cat']}.svg", 'iconScale': icon_scale,
                                 'area_ha': round(r.ha, 1), 'highlight': bool(why),
                                 'hoverAttribute': f"<b>{esc(r['name'])}</b><br>{esc(label)}",
                                 'detail': detail}})
json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{OUT}/pilsen_industry.geojson', 'w'))

# overview
counts = d['cat'].value_counts()
legend = ''.join(f"<li style='list-style:none;margin:4px 0'><img src='{ICON_URL}ind-{k}.svg' width='22' height='22' alt='' style='vertical-align:middle;margin-right:8px'>{esc(l)} <span style='opacity:.7'>({counts.get(k,0)})</span></li>"
                 for k, (l, c) in CATS.items())
ZKEY = [('Pilsen Planned Manufacturing District (PMD 11)', 'rgba(208,34,43,0.65)', 'rgb(140,12,20)'),
        ('Planned Manufacturing District 7', 'rgba(183,65,14,0.65)', 'rgb(122,40,6)'),
        ('Planned Manufacturing District 8', 'rgba(125,80,45,0.65)', 'rgb(80,48,22)'),
        ('Rail yards & lines, city & postal sites (any zoning)', 'rgba(204,153,255,0.55)', 'rgb(197,0,255)'),
        ('Manufacturing (M)', 'rgba(157,210,227,0.55)', 'rgb(115,178,255)'),
        ('Planned Development (PD)', 'rgba(178,178,178,0.25)', 'rgb(178,178,178)'),
        ('Commercial (C)', 'rgba(0,128,255,0.55)', 'rgb(115,178,255)'), ('Business (B)', 'rgba(255,193,193,0.55)', 'rgb(255,127,127)'),
        ('Downtown Service (DS)', 'rgba(250,90,90,0.55)', 'rgb(78,78,78)'), ('Downtown Mixed (DX)', 'rgba(255,150,150,0.55)', 'rgb(78,78,78)'),
        ('Residential (R)', 'rgba(255,225,165,0.55)', 'rgb(255,167,127)')]
zoning_key = ''.join(f"<li style='list-style:none;margin:3px 0'><span style='display:inline-block;width:18px;height:12px;background:{f};border:1.5px solid {o};margin-right:8px;vertical-align:middle'></span>{esc(l)}</li>" for l, f, o in ZKEY)
order = list(HIGHLIGHTS)
hl = ''.join(f"<li style='margin:6px 0'><img src='{ICON_URL}ind-{d.loc[d.key == k, 'cat'].iloc[0]}.svg' width='16' height='16' alt='' style='vertical-align:-3px;margin-right:4px'><a href='#' data-feature='ind-{k}'><b>{esc(d.loc[d.key == k, 'name'].iloc[0])}</b></a><br><span style='font-size:90%'>{esc(HIGHLIGHTS[k])}</span></li>" for k in order)
overview = (f"<h2 style='margin:0 0 6px'>Industry &amp; logistics around Pilsen</h2>"
            f"<p>The {len(d)} largest industrial, rail, trucking, utility and city logistics sites (2 hectares / 5 acres and up) in Pilsen and within one mile of its borders. "
            "Icon size shows the size of the site. Hover over an icon for its name; click it for details.</p>"
            f"<ul style='padding-left:0'>{legend}</ul>"
            f"<h3 style='margin:14px 0 4px'>Zoning of the sites' parcels</h3><p style='margin:0 0 4px'>Shown from zoom 13, in the City of Chicago zoning-map colours, except the three PMDs and the rail and city sites. Hover a parcel for its district; click it for the site.</p>"
            f"<ul style='padding-left:0'>{zoning_key}</ul>"
            f"<h3 style='margin:14px 0 4px'>A dozen to know</h3><ol style='padding-left:20px'>{hl}</ol>"
            "<p style='font-size:85%;opacity:.8'>Sources: CMAP Land Use Inventory 2020 (parcels merged into sites, clipped to Pilsen + 1 mile); "
            "names from OpenStreetMap contributors; parcels: Cook County 2021; zoning: City of Chicago. Sites smaller than 2 ha are left out. Icons: Font Awesome Free (CC BY 4.0).</p>")
open(f'{OUT}/pilsen_industry_overview.html', 'w').write(overview)
print(len(d)); print(d['cat'].value_counts().to_dict())
missing=[k for k in HIGHLIGHTS if k not in set(d.key)]; print('missing highlights', missing)
