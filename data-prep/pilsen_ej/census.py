"""Social vulnerability by census block group around Sims Metal (Pilsen), from the Census API.

Downloads ACS 5-year (2020-2024) block-group tables for all of Cook County, computes six
indicators, ranks every block group against the county, and keeps the ones in the study area
(Pilsen, Little Village, Bridgeport, McKinley Park and neighbours) with TIGERweb boundaries.

This is the *social* half of a vulnerability index only. Health and pollution burden come from
the city's Chicago EJ Index (join_ej.py, tract level), which the census does not carry.

Needs ~/.census_key (or CENSUS_KEY). Usage (from this folder): python3 census.py
Writes out/pilsen_bg_social.geojson and out/pilsen_bg_social.csv
"""
import json, math, os, urllib.parse, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
YEAR = 2024
KEY = os.environ.get('CENSUS_KEY') or open(os.path.expanduser('~/.census_key')).read().strip()
SIMS = (-87.6687, 41.8466)  # 2500 S. Paulina St (approx. centre of the yard)
BBOX = (-87.735, 41.815, -87.625, 41.875)  # lon/lat study area
TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/10/query'

r = lambda a, b: [f'{a}_{i:03d}E' for i in b]
TABLES = {
    'pop': ['B01003_001E'],
    'age': ['B01001_001E'] + r('B01001', [3, 20, 21, 22, 23, 24, 25, 27, 44, 45, 46, 47, 48, 49]),
    'pov': ['C17002_001E'] + r('C17002', range(2, 8)),          # ratio of income to poverty, < 2.0
    'race': ['B03002_001E', 'B03002_003E'],                       # total, white non-Hispanic
    'lang': ['C16002_001E'] + r('C16002', [4, 7, 10, 13]),        # limited-English households
    'edu': ['B15003_001E'] + r('B15003', range(2, 17)),           # 25+ without HS diploma
    'inc': ['B19013_001E'],
}


def get(url):
    with urllib.request.urlopen(url, timeout=120) as f:
        return json.loads(f.read())


def acs(cols):
    q = urllib.parse.urlencode({'get': ','.join(cols), 'for': 'block group:*',
                                'in': 'state:17 county:031 tract:*', 'key': KEY})
    rows = get(f'https://api.census.gov/data/{YEAR}/acs/acs5?{q}')
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df['GEOID'] = df.state + df.county + df.tract + df['block group']
    df = df.set_index('GEOID')[cols].apply(pd.to_numeric, errors='coerce')
    return df.where(df >= 0)  # ACS uses large negatives for "not available"


def indicators():
    """All Cook County block groups: counts, shares, county percentiles and social score."""
    d = pd.concat([acs(c) for c in TABLES.values()], axis=1)
    d = d.loc[:, ~d.columns.duplicated()]
    p = pd.DataFrame(index=d.index)
    p['pop'] = d.B01003_001E
    s = lambda cols: d[cols].sum(axis=1)
    p['pct_under5'] = s(['B01001_003E', 'B01001_027E']) / d.B01001_001E
    p['pct_65plus'] = s(r('B01001', [20, 21, 22, 23, 24, 25, 44, 45, 46, 47, 48, 49])) / d.B01001_001E
    p['pct_low_income'] = s(r('C17002', range(2, 8))) / d.C17002_001E     # below 200% of poverty
    p['pct_poc'] = 1 - d.B03002_003E / d.B03002_001E
    p['pct_limited_english'] = s(r('C16002', [4, 7, 10, 13])) / d.C16002_001E
    p['pct_no_hs'] = s(r('B15003', range(2, 17))) / d.B15003_001E
    p['median_hh_income'] = d.B19013_001E
    ind = ['pct_under5', 'pct_65plus', 'pct_low_income', 'pct_poc', 'pct_limited_english', 'pct_no_hs']
    ok = p['pop'] >= 100  # tiny block groups give unstable percentages
    for c in ind:
        p[c + '_pctile'] = (p.loc[ok, c].rank(pct=True) * 100).round(1)
    p['social_score'] = p.loc[ok, [c + '_pctile' for c in ind]].mean(axis=1).round(1)
    p['social_pctile'] = (p['social_score'].rank(pct=True) * 100).round(1)  # vs all Cook County BGs
    # raw counts, for area totals (shares of an area = sum of numerators / sum of denominators)
    p['n_low_income'], p['d_low_income'] = s(r('C17002', range(2, 8))), d.C17002_001E
    p['n_poc'], p['d_poc'] = d.B03002_001E - d.B03002_003E, d.B03002_001E
    p['n_limited_english'], p['d_limited_english'] = s(r('C16002', [4, 7, 10, 13])), d.C16002_001E
    p['n_no_hs'], p['d_no_hs'] = s(r('B15003', range(2, 17))), d.B15003_001E
    p['n_under5'] = s(['B01001_003E', 'B01001_027E'])
    p['n_65plus'] = s(r('B01001', [20, 21, 22, 23, 24, 25, 44, 45, 46, 47, 48, 49]))
    p['d_age'] = d.B01001_001E
    return p, ok


def main():
    os.makedirs(OUT, exist_ok=True)
    p, ok = indicators()
    p = p[[c for c in p.columns if not c.startswith(('n_', 'd_'))]]

    # boundaries for the study area
    q = urllib.parse.urlencode({'geometry': ','.join(map(str, BBOX)), 'geometryType': 'esriGeometryEnvelope',
                                'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'GEOID',
                                'returnGeometry': 'true', 'outSR': 4326, 'f': 'geojson'})
    gj = get(f'{TIGER}?{q}')
    feats = []
    for f in gj['features']:
        g = f['properties']['GEOID']
        if g not in p.index:
            continue
        row = p.loc[g]
        ring = f['geometry']['coordinates'][0] if f['geometry']['type'] == 'Polygon' else f['geometry']['coordinates'][0][0]
        cx, cy = sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)
        km = math.hypot((cx - SIMS[0]) * 111.32 * math.cos(math.radians(cy)), (cy - SIMS[1]) * 110.54)
        props = {'GEOID': g, 'tract': g[:11], 'km_to_sims': round(km, 2)}
        props.update({k: (None if pd.isna(v) else round(float(v), 4)) for k, v in row.items()})
        feats.append({'type': 'Feature', 'geometry': f['geometry'], 'properties': props})
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(os.path.join(OUT, 'pilsen_bg_social.geojson'), 'w'))
    t = pd.DataFrame([f['properties'] for f in feats]).sort_values('km_to_sims')
    t.to_csv(os.path.join(OUT, 'pilsen_bg_social.csv'), index=False)
    print(f'{len(feats)} block groups in study area (ACS {YEAR - 4}-{YEAR}); Cook County ranked: {ok.sum()}')
    near = t[t.km_to_sims <= 1.6]
    print(f'Within 1 mile of Sims: {len(near)} block groups, {int(near["pop"].sum()):,} people; '
          f'median social percentile {near.social_pctile.median():.0f}; '
          f'{(near.social_pctile >= 75).sum()} at or above the 75th')


if __name__ == '__main__':
    main()
