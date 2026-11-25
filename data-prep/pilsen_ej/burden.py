"""Cumulative Burdens: one score per census block group around Sims (Pilsen), General Iron (Lincoln Park)
and Southside Recycling (Southeast Side), for the Sims Permit Case app.

Three domains, each a percentile (0-100, higher = more burdened):
  PEOPLE     block group, ranked against ALL ILLINOIS block groups (population >= 100), the way Illinois
             EPA's EJ screening works: mean of six ACS 2020-24 percentiles - income below twice the poverty
             line, people of colour, limited-English households, adults without a high-school diploma,
             children under 5, adults 65+.
  HEALTH     census tract, Chicago EJ Index 2023 (CDPH): mean of the city percentiles for adult asthma,
             coronary heart disease, low birth weight, and children 1-5 with blood lead >= 5 ug/dL;
             ranked among Chicago tracts.
  POLLUTION  census tract, Chicago EJ Index 2023 pollution-burden score (PM2.5, ozone, diesel, air-toxics
             cancer risk and hazard, toxic releases, traffic, freight, lead-paint housing, hazardous sites,
             polluting facilities...), ranked among Chicago tracts.
CUMULATIVE = mean of the three, ranked among all Chicago block groups (0-100).
Also attached: Illinois EPA EJ Start status (2021 screening; joined by block-group ID, so 2020 block groups
that were redrawn since 2010 have none), its 1-mile "area of EJ concern" (computed here), and the city's
"EJ neighborhood" designation (tract score >= 75, or >= 70 next to one).

Needs ~/.census_key and raw/Chicago-EJ-Index-Values_2023.10.04.xlsx. Usage: python3 burden.py
Writes out/burden_bg.geojson, out/burden_sites.json, and (if PEREZ_APP is set) the Shiny app's
data/census/burden_bg.geojson and burden_sites.json.
"""
import json, math, os, urllib.parse, urllib.request
import pandas as pd
from shapely.geometry import shape, Point, Polygon, mapping
from shapely.ops import unary_union
import census
from compare import SITES, MILE, tiger, km

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
EJSTART = 'https://geoservices.epa.illinois.gov/arcgis/rest/services/Political/EjStart2021Data/MapServer/{}/query'


def acs_state(cols):
    q = urllib.parse.urlencode({'get': ','.join(cols), 'for': 'block group:*',
                                'in': 'state:17 county:* tract:*', 'key': census.KEY})
    rows = census.get(f'https://api.census.gov/data/{census.YEAR}/acs/acs5?{q}')
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df['GEOID'] = df.state + df.county + df.tract + df['block group']
    df = df.set_index('GEOID')[cols].apply(pd.to_numeric, errors='coerce')
    return df.where(df >= 0)


def people_statewide():
    """census.indicators(), but for every Illinois block group."""
    census.acs = acs_state          # reuse the indicator definitions with a statewide query
    p, ok = census.indicators()
    ind = ['pct_under5', 'pct_65plus', 'pct_low_income', 'pct_poc', 'pct_limited_english', 'pct_no_hs']
    p['people_score'] = p.loc[ok, [c + '_pctile' for c in ind]].mean(axis=1)
    p['people_pctile'] = (p['people_score'].rank(pct=True) * 100).round(1)
    return p, ok


def ej_index():
    ej = pd.read_excel(os.path.join(HERE, 'raw/Chicago-EJ-Index-Values_2023.10.04.xlsx'), sheet_name='Indicator Values, Scores')
    ej.index = ej.CT_FIPS.astype('int64').astype(str)
    ej['health_score'] = ej[['ASTHMA_PCTILE', 'CHD_PCTILE', 'LBW_PCTILE', 'LEAD_PCTILE']].mean(axis=1) * 100
    ej['health_pctile'] = (ej.health_score.rank(pct=True) * 100).round(1)
    ej['pollution_pctile'] = (ej.POLLUTION_BURDEN_SCORE.rank(pct=True) * 100).round(1)
    return ej


def ej_start(bbox):
    """IEPA EJ Start 2021 status by block-group ID (the service returns attributes, not shapes)."""
    q = urllib.parse.urlencode({'geometry': ','.join(map(str, bbox)), 'geometryType': 'esriGeometryEnvelope',
                                'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'ID,EjStatus',
                                'returnGeometry': 'false', 'f': 'json'})
    with urllib.request.urlopen(EJSTART.format(28) + '?' + q, timeout=180) as f:
        res = json.loads(f.read())
    if 'features' not in res:
        raise SystemExit(f'EJ Start: {res}')
    return {f['attributes']['ID']: f['attributes']['EjStatus'] for f in res['features']}


def km_plane(geom, y0):
    """lon/lat geometry -> km plane, for distances (1-mile EJ buffer)."""
    from shapely.ops import transform
    k = 111.32 * math.cos(math.radians(y0))
    return transform(lambda x, y, z=None: (x * k, y * 110.54), geom)


EJ_STATUS = {0: 'not an EJ area', 1: 'EJ area (minority)', 2: 'EJ area (low income)', 3: 'EJ area (minority and low income)'}


def main():
    os.makedirs(OUT, exist_ok=True)
    p, ok = people_statewide()
    ej = ej_index()
    # Chicago block groups = those in a tract of the city's index
    chi = p[ok & p.index.str[:11].isin(ej.index)].copy()
    chi['health_pctile'] = ej.loc[chi.index.str[:11], 'health_pctile'].values
    chi['pollution_pctile'] = ej.loc[chi.index.str[:11], 'pollution_pctile'].values
    chi['cum_raw'] = chi[['people_pctile', 'health_pctile', 'pollution_pctile']].mean(axis=1)
    chi['cum_pctile'] = (chi.cum_raw.rank(pct=True) * 100).round(1)
    print(f'Illinois block groups ranked: {ok.sum():,}; Chicago block groups scored: {len(chi):,}')

    # city "EJ neighborhoods" (tract CEJI percentile >= 75, or >= 70 next to one) from join_ej.py
    ejn = {}
    tj = os.path.join(OUT, 'compare_tracts.geojson')
    feats_out, summary = [], {}
    for s in SITES:
        bgs = tiger(10, s['lonlat'], 2 * MILE)
        x, y = s['lonlat']; d = 2.2 * MILE
        bbox = (x - d / (111.32 * math.cos(math.radians(y))), y - d / 110.54, x + d / (111.32 * math.cos(math.radians(y))), y + d / 110.54)
        es = ej_start(bbox)
        trs = tiger(8, s['lonlat'], 2.2 * MILE)
        tshape = {f['properties']['GEOID']: shape(f['geometry']) for f in trs}
        high = {g for g in tshape if g in ej.index and ej.loc[g, 'CEJI_SCORE_PCTILE'] >= 75}
        for g in tshape:
            if g in ej.index:
                sc = ej.loc[g, 'CEJI_SCORE_PCTILE']
                ejn[g] = bool(sc >= 75 or (sc >= 70 and any(tshape[g].intersects(tshape[h]) for h in high if h != g)))
        rows = []
        for f in bgs:
            g = f['properties']['GEOID']
            if g not in p.index:
                continue
            geom = shape(f['geometry'])
            pt = geom.representative_point()
            st = es.get(g)
            r = p.loc[g]; tr = g[:11]
            inch = g in chi.index
            e = ej.loc[tr] if tr in ej.index else None
            val = lambda v, k=1: None if v is None or pd.isna(v) else round(float(v) * k, 3)
            props = {
                'GEOID': g, 'tract': tr, 'site': s['id'], 'km': f['properties']['km'],
                'pop': None if pd.isna(r['pop']) else int(r['pop']),
                'people_pctile': val(r.people_pctile), 'pct_low_income': val(r.pct_low_income), 'pct_poc': val(r.pct_poc),
                'pct_limited_english': val(r.pct_limited_english), 'pct_no_hs': val(r.pct_no_hs),
                'pct_under5': val(r.pct_under5), 'pct_65plus': val(r.pct_65plus),
                'median_hh_income': val(r.median_hh_income),
                'health_pctile': val(e.health_pctile) if e is not None else None,
                'pollution_pctile': val(e.pollution_pctile) if e is not None else None,
                'cum_pctile': val(chi.loc[g, 'cum_pctile']) if inch else None,
                'asthma': val(e.ASTHMA) if e is not None else None, 'chd': val(e.CHD) if e is not None else None,
                'lbw': val(e.LBW) if e is not None else None, 'child_lead': val(e.LEAD) if e is not None else None,
                'pm25': val(e.PM25) if e is not None else None, 'diesel': val(e.DIESEL) if e is not None else None,
                'cancer': val(e.CANCER) if e is not None else None, 'traffic_pctile': val(e.TRAFFIC_PCTILE, 100) if e is not None else None,
                'freight_pctile': val(e.FREIGHT_PCTILE, 100) if e is not None else None,
                'facilities_pctile': val(e.CONFACILITIES_PCTILE, 100) if e is not None else None,
                'city_ej_pctile': val(e.CEJI_SCORE_PCTILE) if e is not None else None,
                'city_ej_neighborhood': ejn.get(tr),
                'iepa_ej_status': None if st is None else int(st), 'iepa_ej_buffer': False,
            }
            simp = geom.simplify(0.00004, preserve_topology=True)
            rnd = lambda c: [round(c[0], 5), round(c[1], 5)]
            gj = mapping(simp)
            if gj['type'] == 'Polygon':
                gj = {'type': 'Polygon', 'coordinates': [[rnd(c) for c in ring] for ring in gj['coordinates']]}
            else:
                gj = {'type': 'MultiPolygon', 'coordinates': [[[rnd(c) for c in ring] for ring in poly] for poly in gj['coordinates']]}
            feats_out.append({'type': 'Feature', 'geometry': gj, 'properties': props, '_shape': geom})
            rows.append(props)
        # IEPA's "area of EJ concern" = EJ block groups + 1 mile around them
        site_feats = [f for f in feats_out if f['properties']['site'] == s['id']]
        ejpolys = [km_plane(f['_shape'], y) for f in site_feats if (f['properties']['iepa_ej_status'] or 0) > 0]
        if ejpolys:
            zone = unary_union(ejpolys).buffer(MILE)
            for f in site_feats:
                f['properties']['iepa_ej_buffer'] = bool(zone.contains(km_plane(f['_shape'].representative_point(), y)))
        for f in site_feats:
            for r in rows:
                if r['GEOID'] == f['properties']['GEOID']:
                    r['iepa_ej_buffer'] = f['properties']['iepa_ej_buffer']
        t = pd.DataFrame(rows)
        summary[s['id']] = {}
        for rn, rk in (('1', MILE), ('2', 2 * MILE)):
            a = t[(t.km <= rk) & t['pop'].notna()]
            sc = a[a.cum_pctile.notna()]
            w = lambda c: round(float((sc[c] * sc['pop']).sum() / sc['pop'].sum()), 1) if len(sc) else None
            summary[s['id']][rn] = {
                'people': int(a['pop'].sum()),
                'cum_pctile_popweighted': w('cum_pctile'),
                'share_top20': round(100 * float(sc.loc[sc.cum_pctile >= 80, 'pop'].sum() / a['pop'].sum()), 1) if len(a) else None,
                'share_top40': round(100 * float(sc.loc[sc.cum_pctile >= 60, 'pop'].sum() / a['pop'].sum()), 1) if len(a) else None,
                'people_pctile': w('people_pctile'), 'health_pctile': w('health_pctile'), 'pollution_pctile': w('pollution_pctile'),
                'child_lead': w('child_lead'), 'asthma': w('asthma'),
                'share_iepa_ej': round(100 * float(a.loc[a.iepa_ej_status.fillna(0) > 0, 'pop'].sum() / a['pop'].sum()), 1) if len(a) else None,
                'share_iepa_ej_area': round(100 * float(a.loc[a.iepa_ej_buffer.astype(bool), 'pop'].sum() / a['pop'].sum()), 1) if len(a) else None,
                'share_city_ej': round(100 * float(a.loc[a.city_ej_neighborhood.fillna(False).astype(bool), 'pop'].sum() / a['pop'].sum()), 1) if len(a) else None,
                'block_groups': int(len(a)), 'scored': int(len(sc)),
            }
            print(f"{s['name']:20s} {rn} mi: {summary[s['id']][rn]}")
    for f in feats_out:
        f.pop('_shape', None)
    json.dump({'type': 'FeatureCollection', 'features': feats_out}, open(os.path.join(OUT, 'burden_bg.geojson'), 'w'))
    json.dump(summary, open(os.path.join(OUT, 'burden_sites.json'), 'w'), indent=1)
    print(f'Wrote {len(feats_out)} block groups to out/burden_bg.geojson '
          f'({os.path.getsize(os.path.join(OUT, "burden_bg.geojson")) / 1e6:.1f} MB)')
    if os.environ.get('PEREZ_APP'):
        dest = os.path.join(os.environ['PEREZ_APP'], 'data', 'census')
        os.makedirs(dest, exist_ok=True)
        for fn in ('burden_bg.geojson', 'burden_sites.json'):
            with open(os.path.join(OUT, fn)) as a, open(os.path.join(dest, fn), 'w') as b:
                b.write(a.read())
        print('Copied to', dest)


if __name__ == '__main__':
    main()
