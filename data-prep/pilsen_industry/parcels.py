"""Parcels attached to each curated site, coloured by Chicago zoning (official City zoning-map colours) -> GeoJSON."""
import geopandas as gpd, pandas as pd, json, sys, warnings
warnings.filterwarnings('ignore')
SRC = '/media/brian/Legacy/chicago_geology/'
OUT = sys.argv[1]
# City of Chicago Zoning map (gisapps.chicago.gov ExternalApps/Zoning MapServer layer 15), by ZONE_TYPE: fill, outline
ZT = {1: ('Business', (255, 193, 193), (255, 127, 127)), 2: ('Commercial', (0, 128, 255), (115, 178, 255)),
      3: ('Manufacturing', (157, 210, 227), (115, 178, 255)), 4: ('Residential', (255, 225, 165), (255, 167, 127)),
      5: ('Planned Development', None, (178, 178, 178)), 6: ('Planned Manufacturing District', (204, 153, 255), (197, 0, 255)),
      7: ('Downtown Mixed', (255, 150, 150), (78, 78, 78)), 8: ('Downtown Core', (255, 0, 0), (78, 78, 78)),
      9: ('Downtown Residential', (225, 225, 150), (78, 78, 78)), 10: ('Downtown Service', (250, 90, 90), (78, 78, 78)),
      11: ('Transportation', (104, 104, 104), (178, 178, 178)), 12: ('Parks & Open Space', (180, 255, 180), (56, 168, 0))}
rgba = lambda c, a: f'rgba({c[0]},{c[1]},{c[2]},{a})'
# Our own choices on top of the official scheme: each PMD its own deep colour (10% more opaque),
# and the official PMD violet moved to the rail and city/postal logistics sites, whatever their zoning.
PMD = {'PMD 11': ('Pilsen PMD', (208, 34, 43), (140, 12, 20)),      # PERRO red (app primary #d0222b)
       'PMD 7': ('PMD 7', (183, 65, 14), (122, 40, 6)),              # rust
       'PMD 8': ('PMD 8', (125, 80, 45), (80, 48, 22))}               # brown
MUNICIPAL = ('Rail and city/postal logistics site', (204, 153, 255), (197, 0, 255))
sites_cat = dict(zip(gpd.read_file('sites_curated.gpkg').key_s, gpd.read_file('sites_curated.gpkg')['cat']))
sites = gpd.read_file('sites_curated.gpkg')
zone = gpd.read_file('zone.geojson').to_crs(26916).geometry.iloc[0]
bb = tuple(sites.to_crs(4326).total_bounds)
par = gpd.read_file(SRC + 'geojson_sources/Parcel_2021.gpkg', bbox=bb).to_crs(26916)
par['pa'] = par.area
o = gpd.overlay(sites[['key_s', 'name', 'geometry']], par[['pin10', 'pa', 'geometry']], how='intersection')
o['a'] = o.area
o = o[(o.a > 0.5 * o.pa) | (o.a > 3000)].sort_values('a').drop_duplicates('pin10', keep='last')
p = par[par.pin10.isin(o.pin10)].drop_duplicates('pin10').merge(o[['pin10', 'key_s', 'name']], on='pin10')
p['geometry'] = p.intersection(zone)
p = p[~p.is_empty]
z = gpd.read_file(SRC + 'geojson_sources/Zoning_Districts.geojson', bbox=bb).to_crs(26916)
zo = gpd.overlay(p[['pin10', 'geometry']], z[['zone_class', 'zone_type', 'geometry']], how='intersection')
zo['a'] = zo.area
zmain = zo.sort_values('a').drop_duplicates('pin10', keep='last').set_index('pin10')
feats = []
for _, r in p.iterrows():
    zc = zmain.zone_class.get(r.pin10, '')
    zt = int(zmain.zone_type.get(r.pin10, 0) or 0)
    label, fill, line = ZT.get(zt, ('Unknown', (220, 220, 220), (150, 150, 150)))
    alpha = 0.55
    if zc in PMD:  # PMD colour wins, also for rail and city sites inside a PMD
        _, fill, line = PMD[zc]; alpha = 0.65
    elif sites_cat.get(r.key_s) in ('municipal', 'rail'):
        _, fill, line = MUNICIPAL
    g = gpd.GeoSeries([r.geometry.simplify(0.5)], crs=26916).to_crs(4326).iloc[0]
    feats.append({'type': 'Feature', 'geometry': json.loads(gpd.GeoSeries([g]).to_json())['features'][0]['geometry'],
                  'properties': {'pin': r.pin10, 'site': f'ind-{r.key_s}', 'detailRef': f'ind-{r.key_s}',
                                 'zone_class': zc, 'zone_type': label,
                                 'color': rgba(fill, alpha) if fill else 'rgba(178,178,178,0.25)', 'stroke': rgba(line, 0.9),
                                 'hoverAttribute': f"<b>{zc or 'No zoning data'}</b> · {label}<br>{r['name']}"}})
# Every other parcel inside the three PMDs (within Pilsen + 1 mile), so each district shows whole.
pmdz = z[z.zone_class.isin(list(PMD))][['zone_class', 'geometry']]
rest = par[~par.pin10.isin(p.pin10)].drop_duplicates('pin10').copy()
pts = rest.copy(); pts['geometry'] = rest.representative_point()
inside = gpd.sjoin(pts[['pin10', 'geometry']], pmdz, predicate='within').drop_duplicates('pin10').set_index('pin10').zone_class
rest = rest[rest.pin10.isin(inside.index)]
rest['geometry'] = rest.intersection(zone)
rest = rest[~rest.is_empty]
for _, r in rest.iterrows():
    zc = inside[r.pin10]
    name, fill, line = PMD[zc]
    g = gpd.GeoSeries([r.geometry.simplify(0.5)], crs=26916).to_crs(4326).iloc[0]
    feats.append({'type': 'Feature', 'geometry': json.loads(gpd.GeoSeries([g]).to_json())['features'][0]['geometry'],
                  'properties': {'pin': r.pin10, 'zone_class': zc, 'zone_type': 'Planned Manufacturing District',
                                 'color': rgba(fill, 0.65), 'stroke': rgba(line, 0.9),
                                 'hoverAttribute': f"<b>{zc}</b> · Planned Manufacturing District",
                                 'detail': (f"<h2 style='margin:0 0 8px'>{zc} · Planned Manufacturing District</h2>"
                                            f"<p><b>Parcel (PIN):</b> {r.pin10[:2]}-{r.pin10[2:4]}-{r.pin10[4:7]}-{r.pin10[7:]}</p>"
                                            "<p>This parcel is not part of one of the large industrial and logistics sites on the map; "
                                            "it is shown so the whole manufacturing district can be seen.</p>"
                                            "<p style='font-size:80%;opacity:.75'>Sources: Cook County parcels 2021; City of Chicago zoning.</p>"
                                            "<p><a href='#' data-overlay-back>&larr; All industry &amp; logistics</a></p>")}})
print(len(rest), 'more PMD parcels')
fc = {'type': 'FeatureCollection', 'features': feats}
s = json.dumps(fc, separators=(',', ':'))
import re
s = re.sub(r'(\d+\.\d{6})\d+', r'\1', s)
open(f'{OUT}/pilsen_industry_parcels.geojson', 'w').write(s)
print(len(feats), 'parcels,', round(len(s) / 1e6, 2), 'MB'); print(pd.Series([f['properties']['zone_type'] for f in feats]).value_counts().to_dict())
