"""Fill enrich.json 'commons' (photos taken near a site whose file title matches its name), slowly, resuming."""
import geopandas as gpd, json, re, time, urllib.request, warnings
warnings.filterwarnings('ignore')
UA = {'User-Agent': 'perro-map-data-prep/1.0'}
E = json.load(open('enrich.json'))
sites = gpd.read_file('sites_curated.gpkg')
cent = sites.copy(); cent['geometry'] = sites.representative_point(); cent = cent.to_crs(4326)
STOP = {'chicago', 'street', 'the', 'and', 'site', 'yard', 'company', 'co', 'inc', 'services', 'facility', 'center', 'building',
        'industrial', 'general', 'rail', 'west', 'south', 'north', 'east', 'with', 'from', 'line', 'lines', 'avenue', 'road'}
for _, r in cent.iterrows():
    s = E['sites'][r.key_s]
    if 'commons' in s: continue
    words = set(w for n in [r['name']] + [c['name'] for c in s['osm'][:3] if c['name']] for w in re.findall(r'[a-z]{4,}', str(n).lower())) - STOP
    if not words:
        s['commons'] = []; continue
    url = ('https://commons.wikimedia.org/w/api.php?action=query&format=json&list=geosearch&gsnamespace=6&gslimit=50'
           f'&gsradius={int(min(1000, max(150, (r.ha * 1e4) ** 0.5)))}&gscoord={r.geometry.y}|{r.geometry.x}')
    for wait in (3, 10, 30, 60):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as resp:
                res = json.load(resp)
            break
        except Exception as e:
            time.sleep(wait); res = None
    if res is None:
        print('gave up', r.key_s); continue
    s['commons'] = [h['title'] for h in res.get('query', {}).get('geosearch', [])
                    if words & set(re.findall(r'[a-z]{4,}', h['title'].lower()))][:3]
    json.dump(E, open('enrich.json', 'w'), indent=1)
    time.sleep(2)
print('sites with commons photos:', sum(1 for s in E['sites'].values() if s.get('commons')))
