"""Key facts per curated site: parcel owners (Cook County API), zoning, main building, OSM operator/website, Wikidata."""
import geopandas as gpd, pandas as pd, json, re, time, urllib.request, urllib.parse, warnings
warnings.filterwarnings('ignore')
SRC = '/media/brian/Legacy/chicago_geology/'
UA = {'User-Agent': 'perro-map-data-prep/1.0'}
def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            err = e; time.sleep(2)
    print('fail', url[:120], err); return None

sites = gpd.read_file('sites_curated.gpkg')  # EPSG:26916
bb = tuple(sites.to_crs(4326).total_bounds)
sites['sa'] = sites.area
out = {k: {} for k in sites.key_s}

def best(overlay, key_col, val_cols, min_share=0.0):
    overlay['a'] = overlay.area
    return overlay

# ---- parcels & owners
par = gpd.read_file(SRC + 'geojson_sources/Parcel_2021.gpkg', bbox=bb).to_crs(26916)
par['pa'] = par.area
o = gpd.overlay(sites[['key_s', 'geometry']], par[['pin10', 'assessorbldgclass', 'pa', 'geometry']], how='intersection')
o['a'] = o.area
o = o[(o.a > 0.5 * o.pa) | (o.a > 3000)]
pins = sorted(set(o.pin10.astype(str)))
owners = {}
for i in range(0, len(pins), 80):
    chunk = pins[i:i + 80]
    q = urllib.parse.urlencode({'$select': 'pin10,year,owner_address_name', '$where': f"pin10 in ({','.join(repr(p) for p in chunk)})",
                                '$order': 'year DESC', '$limit': 5000})
    for r in get('https://datacatalog.cookcountyil.gov/resource/3723-97qp.json?' + q) or []:
        if r.get('owner_address_name') and r['pin10'] not in owners:
            owners[r['pin10']] = (r['owner_address_name'].strip(), r['year'])
print('parcels', len(pins), 'with owner', len(owners))
for k, g in o.groupby('key_s'):
    g = g.assign(owner=g.pin10.astype(str).map(lambda p: owners.get(p, ('', ''))[0]))
    by_owner = g[g.owner != ''].groupby('owner').a.sum().sort_values(ascending=False)
    out[k]['owners'] = by_owner.index[:3].tolist()
    out[k]['n_parcels'] = int(len(g))
    top = g.sort_values('a').iloc[-1]
    out[k]['assessor_class'] = str(top.assessorbldgclass)
    out[k]['owner_year'] = owners.get(str(top.pin10), ('', ''))[1]

# ---- zoning
z = gpd.read_file(SRC + 'geojson_sources/Zoning_Districts.geojson', bbox=bb).to_crs(26916)
zo = gpd.overlay(sites[['key_s', 'sa', 'geometry']], z[['zone_class', 'geometry']], how='intersection')
zo['a'] = zo.area
for k, g in zo.groupby('key_s'):
    s = g.groupby('zone_class').a.sum().sort_values(ascending=False)
    out[k]['zoning'] = [c for c, a in s.items() if a > 0.1 * s.sum()][:3]

# ---- main building
b = gpd.read_file(SRC + 'chicago_buildings_height.gpkg', bbox=tuple(sites.to_crs(6455).total_bounds)).to_crs(26916)
b['ba'] = b.area
typ = gpd.read_file(SRC + 'building_materials_height.gpkg', ignore_geometry=True, columns=['bldg_id', 'typology'])
typ = typ.drop_duplicates('bldg_id').set_index('bldg_id').typology.to_dict()
bj = gpd.sjoin(b[['bldg_id', 'no_stories', 'stories', 'year_built', 'ba', 'height', 'geometry']].assign(geometry=b.representative_point()),
               sites[['key_s', 'geometry']], predicate='within')
for k, g in bj.groupby('key_s'):
    t = g.sort_values('ba').iloc[-1]
    st = t.no_stories if pd.notna(t.no_stories) and float(t.no_stories or 0) > 0 else t.stories
    out[k]['bldg'] = dict(id=str(t.bldg_id), typology=typ.get(t.bldg_id) or typ.get(str(t.bldg_id)) or '',
                          stories=int(float(st)) if pd.notna(st) and float(st) > 0 else None,
                          year=int(float(t.year_built)) if pd.notna(t.year_built) and float(t.year_built) > 1800 else None,
                          sqft=round(t.ba * 10.7639), height_m=round(float(t.height), 1) if pd.notna(t.height) else None,
                          n=int(len(g)))

# ---- OSM operator / website / image
def tags(t):
    return dict(re.findall(r'"([^"]+)"=>"((?:[^"\\]|\\.)*)"', t or ''))
osm = pd.concat([gpd.read_file(f) for f in ['osm_chopped_multipolygons.gpkg', 'osm_bldg_poi_multipolygons.gpkg']])
osm = osm.drop_duplicates(['osm_id', 'osm_way_id']).to_crs(26916)
osm['oa'] = osm.area
osm = osm[osm.oa < 2e6]  # drop neighbourhood / community-area outlines
oo = gpd.overlay(sites[['key_s', 'geometry']], osm[['name', 'building', 'other_tags', 'oa', 'geometry']].reset_index(drop=True), how='intersection')
oo['a'] = oo.area
oo = oo[(oo.a > 0.3 * oo.oa) | (oo.a > 3000)]
pts = gpd.read_file('osm_chopped_points.gpkg').to_crs(26916)
pj = gpd.sjoin(pts[['name', 'other_tags', 'geometry']], sites[['key_s', 'geometry']], predicate='within')
for k in out:
    cand = []
    g = oo[oo.key_s == k].sort_values('a', ascending=False)
    for _, r in g.iterrows():
        cand.append((r['name'], tags(r.other_tags), r.building, r.a))
    for _, r in pj[pj.key_s == k].iterrows():
        cand.append((r['name'], tags(r.other_tags), None, 0))
    out[k]['osm'] = [dict(name=n, building=bd, tags={t: v for t, v in tg.items() if t in (
        'operator', 'owner', 'brand', 'website', 'operator:website', 'brand:website', 'contact:website', 'url', 'wikidata',
        'operator:wikidata', 'brand:wikidata', 'image', 'wikimedia_commons', 'industrial', 'product', 'landuse', 'man_made',
        'power', 'railway', 'amenity', 'shop', 'office', 'craft', 'building', 'operator:type', 'description')}) for n, tg, bd, a in cand[:8]]

# ---- Wikidata: websites (P856) and images (P18)
qids = sorted({v for s in out.values() for c in s['osm'] for t, v in c['tags'].items() if t.endswith('wikidata') and re.match(r'^Q\d+$', v)})
wd = {}
for i in range(0, len(qids), 40):
    r = get('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims|labels&languages=en&ids=' + '|'.join(qids[i:i + 40]))
    for q, e in ((r or {}).get('entities') or {}).items():
        c = e.get('claims', {})
        val = lambda p: c[p][0]['mainsnak'].get('datavalue', {}).get('value') if p in c else None
        wd[q] = dict(label=e.get('labels', {}).get('en', {}).get('value'), website=val('P856'), image=val('P18'))
print('wikidata', len(wd))

# Photos: see commons.py (candidates only; pick reviewed ones into curate.py IMAGES).
json.dump(dict(sites=out, wikidata=wd), open('enrich.json', 'w'), indent=1)
print('done')
