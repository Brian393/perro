"""Chicago EJ Index (CDPH Cumulative Impact Assessment, 2023) for the census tracts around Sims.

The city's server refuses scripted downloads, so get the file in a browser first:
  https://www.chicago.gov/content/dam/city/depts/doe/supp_info/Chicago-EJ-Index-Values_2023.10.04.xlsx
and save it in raw/ (same name). Then: python3 join_ej.py

Joins the index to TIGERweb tract boundaries (2020 tracts) for the study area and marks the city's
"EJ neighborhoods": score >= 75, or >= 70 and touching a tract >= 75 (city methodology, 2023).
Also attaches, per tract, the census block-group summary from census.py if it has been run.
Writes out/pilsen_tract_ej.geojson and out/pilsen_tract_ej.csv
"""
import glob, json, math, os, re, urllib.parse, urllib.request
import pandas as pd
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
SIMS = (-87.6687, 41.8466)
BBOX = (-87.735, 41.815, -87.625, 41.875)
TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/8/query'


def find_file():
    files = glob.glob(os.path.join(HERE, 'raw', '*EJ*Index*.xlsx')) + glob.glob(os.path.join(HERE, 'raw', '*EJ*Index*.csv'))
    if not files:
        raise SystemExit('Put Chicago-EJ-Index-Values_2023.10.04.xlsx in raw/ first (see the docstring).')
    return files[0]


def load_index(path):
    """Return a frame indexed by 11-digit tract GEOID, whatever the sheet layout."""
    sheets = pd.read_excel(path, sheet_name=None) if path.endswith('.xlsx') else {'csv': pd.read_csv(path)}
    best = None
    for name, df in sheets.items():
        for c in df.columns:
            v = df[c].astype(str).str.replace(r'\.0$', '', regex=True)
            if v.str.fullmatch(r'17031\d{6}').mean() > 0.8:
                df = df.assign(GEOID=v)
                if best is None or len(df.columns) > len(best[1].columns):
                    best = (name, df)
                break
    if best is None:
        for name, df in sheets.items():
            print(name, list(df.columns)[:30])
        raise SystemExit('No sheet with an 11-digit Cook County tract GEOID column; see the columns above.')
    name, df = best
    # 2023 file: CEJI_SCORE = pollution burden (0-10) x population characteristics (0-10);
    # the city's EJ-neighborhood thresholds (75 / 70) apply to its percentile, CEJI_SCORE_PCTILE.
    score = [c for c in df.columns if str(c) == 'CEJI_SCORE_PCTILE'] or \
            [c for c in df.columns if re.search(r'ej.?index.?score|final.?score|^score$', str(c), re.I)]
    if not score:
        print('Sheet', name, 'columns:', list(df.columns))
        raise SystemExit('Could not find the EJ Index score column; set it by hand in join_ej.py.')
    df = df.rename(columns={score[0]: 'ej_score'}).drop_duplicates('GEOID').set_index('GEOID')
    print(f'EJ Index: sheet "{name}", {len(df)} tracts, score column "{score[0]}"')
    return df


def main():
    os.makedirs(OUT, exist_ok=True)
    ej = load_index(find_file())
    q = urllib.parse.urlencode({'geometry': ','.join(map(str, BBOX)), 'geometryType': 'esriGeometryEnvelope',
                                'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'GEOID',
                                'returnGeometry': 'true', 'outSR': 4326, 'f': 'geojson'})
    with urllib.request.urlopen(f'{TIGER}?{q}', timeout=120) as f:
        gj = json.loads(f.read())
    feats = [f for f in gj['features'] if f['properties']['GEOID'] in ej.index]
    shapes = {f['properties']['GEOID']: shape(f['geometry']) for f in feats}

    # city rule: >= 75, or >= 70 and adjacent to a tract >= 75 (adjacency checked city-wide would need all
    # tracts; inside the study area we check the neighbours we have, which covers every interior tract)
    high = {g for g in shapes if ej.loc[g, 'ej_score'] >= 75}
    bg = os.path.join(OUT, 'pilsen_bg_social.csv')
    soc = pd.read_csv(bg, dtype={'tract': str}) if os.path.exists(bg) else None
    keep = [c for c in ej.columns if c != 'ej_score' and ej[c].dtype.kind in 'fi'
            and (str(c).endswith('_PCTILE') or str(c) in ('CEJI_SCORE', 'POLLUTION_BURDEN_SCORE', 'POP_CHARACTERISTICS_SCORE'))]
    rows = []
    for f in feats:
        g = f['properties']['GEOID']
        s = float(ej.loc[g, 'ej_score'])
        touches = any(shapes[g].touches(shapes[h]) or shapes[g].intersects(shapes[h]) for h in high if h != g)
        c = shapes[g].centroid
        km = math.hypot((c.x - SIMS[0]) * 111.32 * math.cos(math.radians(c.y)), (c.y - SIMS[1]) * 110.54)
        p = {'GEOID': g, 'ej_score': round(s, 1), 'ej_neighborhood': bool(s >= 75 or (s >= 70 and touches)),
             'km_to_sims': round(km, 2)}
        p.update({str(k): (None if pd.isna(ej.loc[g, k]) else round(float(ej.loc[g, k]), 3)) for k in keep})
        if soc is not None:
            t = soc[soc.tract == g]
            if len(t):
                p['bg_count'] = len(t)
                p['bg_max_social_pctile'] = float(t.social_pctile.max())
        f['properties'] = p
        rows.append(p)
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(os.path.join(OUT, 'pilsen_tract_ej.geojson'), 'w'))
    t = pd.DataFrame(rows).sort_values('km_to_sims')
    t.to_csv(os.path.join(OUT, 'pilsen_tract_ej.csv'), index=False)
    near = t[t.km_to_sims <= 1.6]
    print(f'{len(t)} tracts in study area; within 1 mile of Sims: {len(near)} tracts, '
          f'{int(near.ej_neighborhood.sum())} EJ neighborhoods, median score {near.ej_score.median():.1f}')


if __name__ == '__main__':
    main()
