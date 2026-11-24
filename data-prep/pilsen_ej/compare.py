"""Who lives around three Chicago metal shredders: Sims (Pilsen), General Iron (Lincoln Park, closed 2020)
and Southside Recycling (Southeast Side, built for General Iron's owner, never permitted).

Same sources as census.py and join_ej.py: ACS 5-year block groups (Census API) and the city's 2023
Chicago EJ Index (tracts). Areas are 1 and 2 miles around each site; a block group or tract counts when
its centre (TIGERweb internal point) is inside the circle.

Run census.py's prerequisites first (~/.census_key, raw/Chicago-EJ-Index-Values_2023.10.04.xlsx).
Usage (from this folder): python3 compare.py
Writes out/compare_sites.json, out/compare_bg.geojson, out/compare_tracts.geojson (2-mile areas), and
the map files app/client/public/static/data/general_iron_sites.geojson and general_iron_compare.html
"""
import html, json, math, os, urllib.parse, urllib.request
import pandas as pd
import census

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
APP = os.path.join(HERE, '../../app/client/public/static/data/')
MILE = 1.609344
TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/{}/query'
ICON = './static/data/icons/ind-scrap.svg'

SITES = [
    dict(id='gi-sims', short='Pilsen', name='Sims Metal', place='Pilsen', address='2500 S. Paulina St.',
         lonlat=(-87.6687, 41.8466),
         status='Operating. Applying for a state permit (FESOP) to shred about 700,000 tons a year, roughly twice its current cap.'),
    dict(id='gi-clifton', short='Lincoln Park', name='General Iron', place='Lincoln Park', address='1909 N. Clifton Ave.',
         lonlat=(-87.6566, 41.9161),
         status='Shredded scrap here for decades. Closed 31 December 2020 under a 2019 agreement with the city; buildings demolished from 2022.'),
    dict(id='gi-burley', short='Southeast', name='Southside Recycling', place='Southeast Side', address='11600 S. Burley Ave.',
         lonlat=(-87.5450, 41.6838),
         status="Built for General Iron's owner, Reserve Management Group, to take over its shredding. "
                'Never opened: the city denied the operating permit in February 2022, and the Illinois Appellate Court upheld the denial on 6 November 2026.'),
]


def km(x, y, s):
    return math.hypot((x - s[0]) * 111.32 * math.cos(math.radians(y)), (y - s[1]) * 110.54)


def tiger(layer, site, radius_km):
    x, y = site
    dlat = radius_km / 110.54 + 0.005
    dlon = radius_km / (111.32 * math.cos(math.radians(y))) + 0.005
    q = urllib.parse.urlencode({'geometry': f'{x - dlon},{y - dlat},{x + dlon},{y + dlat}',
                                'geometryType': 'esriGeometryEnvelope', 'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects',
                                'outFields': 'GEOID,INTPTLAT,INTPTLON', 'returnGeometry': 'true', 'outSR': 4326, 'f': 'geojson'})
    with urllib.request.urlopen(TIGER.format(layer) + '?' + q, timeout=180) as f:
        feats = json.loads(f.read())['features']
    for f in feats:
        pr = f['properties']
        f['properties'] = {'GEOID': pr['GEOID'], 'km': round(km(float(pr['INTPTLON']), float(pr['INTPTLAT']), site), 3)}
    return [f for f in feats if f['properties']['km'] <= radius_km]


def area_stats(p, ej, bgs, tracts):
    g = p.loc[[b for b in bgs if b in p.index]]
    t = ej.loc[[x for x in tracts if x in ej.index]]
    share = lambda n, d: round(100 * g[n].sum() / g[d].sum(), 1) if g[d].sum() else None
    return {
        'people': int(g['pop'].sum()), 'block_groups': len(g),
        'low_income': share('n_low_income', 'd_low_income'), 'poc': share('n_poc', 'd_poc'),
        'limited_english': share('n_limited_english', 'd_limited_english'), 'no_hs': share('n_no_hs', 'd_no_hs'),
        'under5': share('n_under5', 'd_age'), 'over65': share('n_65plus', 'd_age'),
        'bg_income_median': None if g.median_hh_income.dropna().empty else int(g.median_hh_income.median()),
        'bg_top_quarter': int((g.social_pctile >= 75).sum()),
        'tracts': len(tracts), 'tracts_in_city_index': len(t),
        'ej_pctile_median': None if t.empty else round(float(t.CEJI_SCORE_PCTILE.median()), 1),
        'ej_tracts_75': int((t.CEJI_SCORE_PCTILE >= 75).sum()),
        'pollution_burden': None if t.empty else round(float(t.POLLUTION_BURDEN_SCORE.median()), 2),
        'pop_characteristics': None if t.empty else round(float(t.POP_CHARACTERISTICS_SCORE.median()), 2),
    }


# rows of the comparison table: key, label, format, True if a higher value means more burden
ROWS = [
    ('people', 'People living there', lambda v: f'{v:,}', None),
    ('low_income', 'Below twice the poverty line', lambda v: f'{v:.0f}%', True),
    ('poc', 'People of colour', lambda v: f'{v:.0f}%', True),
    ('limited_english', 'Households with limited English', lambda v: f'{v:.0f}%', True),
    ('no_hs', 'Adults without a high-school diploma', lambda v: f'{v:.0f}%', True),
    ('under5', 'Children under 5', lambda v: f'{v:.1f}%', True),
    ('over65', 'Adults 65 and over', lambda v: f'{v:.0f}%', True),
    ('bg_income_median', 'Typical household income*', lambda v: f'${v / 1000:.0f}k', False),
    ('ej_pctile_median', 'City EJ Index, typical tract (percentile)', lambda v: f'{v:.0f}', True),
    ('ej_tracts_75', 'City "EJ neighborhood" tracts (top quarter)', None, True),
    ('pollution_burden', 'Pollution burden, typical tract (0–10)', lambda v: f'{v:.1f}', True),
]
TD = "style='padding:4px 6px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums'"
TH = "style='padding:4px 6px;text-align:right;font-size:12px;line-height:1.2;white-space:nowrap;vertical-align:bottom'"
TL = "style='padding:4px 6px 4px 0;text-align:left;font-weight:normal;font-size:13px;line-height:1.25'"


def table(stats, radius, ids):
    head = ''.join(f"<th {TH}><a href='#' data-map-feature='{s['id']}' data-fit='{site_box(s)}' style='color:inherit'>{s['short'].replace(' ', '<br>')}</a></th>" for s in SITES if s['id'] in ids)
    body = []
    for key, label, fmt, worse_high in ROWS:
        vals = [stats[s['id']][radius][key] for s in SITES if s['id'] in ids]
        nums = [v for v in vals if v is not None]
        top = (max(nums) if worse_high else min(nums)) if nums and worse_high is not None else None
        cells = []
        for sid, v in zip([s['id'] for s in SITES if s['id'] in ids], vals):
            if key == 'ej_tracts_75':
                t = stats[sid][radius]
                txt = f"{v} of {t['tracts_in_city_index']}" if t['tracts_in_city_index'] else '–'
            else:
                txt = '–' if v is None else fmt(v)
            b = v is not None and v == top and len(set(nums)) > 1
            cells.append(f"<td {TD}>{'<b>' if b else ''}{txt}{'</b>' if b else ''}</td>")
        body.append(f"<tr style='border-top:1px solid rgba(128,128,128,.3)'><th {TL}>{label}</th>{''.join(cells)}</tr>")
    return (f"<table style='border-collapse:collapse;width:100%;margin:4px 0 10px'><tr><th></th>{head}</tr>"
            + ''.join(body) + '</table>')


def site_detail(s, stats):
    a, b = stats[s['id']]['1'], stats[s['id']]['2']
    row = lambda k, l, f: (f"<tr style='border-top:1px solid rgba(128,128,128,.3)'><th {TL}>{l}</th>"
                           f"<td {TD}>{'–' if a[k] is None else f(a[k])}</td><td {TD}>{'–' if b[k] is None else f(b[k])}</td></tr>")
    rows = ''.join(row(k, l, f) for k, l, f, _ in ROWS if f)
    return (f"<h3 style='margin:0 0 2px'>{html.escape(s['name'])}</h3>"
            f"<div style='opacity:.75;margin-bottom:8px'>{html.escape(s['address'])}, {html.escape(s['place'])}</div>"
            f"<p style='margin:0 0 10px'>{html.escape(s['status'])}</p>"
            f"<table style='border-collapse:collapse;width:100%'><tr><th></th><th {TH}>1 mile</th><th {TH}>2 miles</th></tr>{rows}</table>"
            "<p style='margin:10px 0 0'><a href='#' data-overlay-back='1'>Back to the panel</a></p>")


def site_box(x):
    """lon/lat bbox around a site's 2-mile ring, for data-fit links"""
    lon, lat = x['lonlat']
    dy, dx = 2.1 * MILE / 110.54, 2.1 * MILE / (111.32 * math.cos(math.radians(lat)))
    return f"{lon - dx:.4f},{lat - dy:.4f},{lon + dx:.4f},{lat + dy:.4f}"


def overview(stats):
    """People tab of the Sims Permit Case app (Shiny): map key and the three-site comparison.
    data-map-feature links ask the map to fly to a site and show its summary; data-fit zooms the map."""
    ids = [s['id'] for s in SITES]
    xs, ys = [s['lonlat'][0] for s in SITES], [s['lonlat'][1] for s in SITES]
    pad = 2 * MILE / 111
    allbox = f"{min(xs) - pad:.4f},{min(ys) - pad:.4f},{max(xs) + pad:.4f},{max(ys) + pad:.4f}"
    return (
        "<h2 style='margin:0 0 6px'>Three shredders, three neighbourhoods</h2>"
        "<p style='margin:0 0 8px'>General Iron shredded cars and scrap in <b>Lincoln Park</b> until the end of 2020. "
        "Its new owner built a replacement plant on the <b>Southeast Side</b>, but the city refused to let it open, "
        "and federal housing officials found the move discriminatory. <b>Sims Metal</b> still shreds in <b>Pilsen</b>. "
        "Who lives around each site? Click a name to go there: "
        + ' · '.join(f"<a href='#' data-map-feature='{x['id']}' data-fit='{site_box(x)}'>{html.escape(x['short'])}</a>" for x in SITES)
        + f" · <a href='#' data-fit='{allbox}'>all three</a>.</p>"
        "<h3 style='margin:12px 0 2px'>On the map: where the poverty is</h3>"
        "<p style='margin:0'>Each shape is a census block group (about 600 to 3,000 people) within 2 miles of a site, "
        "coloured by the share of residents living below twice the poverty line. Rings mark 1 and 2 miles.</p>"
        + key_html(None)
        + f"<p style='margin:0 0 4px;font-size:13px'>Chicago overall: {globals().get('CITY_PCT', 33):.0f}%. Grey: too few residents for a reliable figure. "
          "Hover a block group for its figure; click it for all its data.</p>"
        "<h3 style='margin:12px 0 2px'>Within 1 mile</h3>" + table(stats, '1', ids)
        + "<h3 style='margin:12px 0 2px'>Within 2 miles</h3>" + table(stats, '2', ids)
        + "<p style='margin:0 0 6px;font-size:13px'><b>Bold</b> marks the heaviest burden in each row.</p>"
          "<p style='margin:0 0 6px;font-size:13px'><b>Did General Iron run on the Southeast Side?</b> No. The Southside Recycling "
          "shredder at 11600 S. Burley was built but never received its city operating permit. Other businesses of the same owner "
          "already ran on that land, and the court weighed their compliance record.</p>"
          "<p style='margin:0;font-size:12px;opacity:.8'>Sources: U.S. Census Bureau, American Community Survey 2020–2024 (block groups); "
          "City of Chicago, Chicago EJ Index 2023 (census tracts). An area counts a block group or tract when its centre is inside the circle. "
          "*Median of the block groups' median incomes, an approximation. The Southside Recycling site sits in an industrial zone, so few "
          "people live within 1 mile; the 2-mile figures cover South Deering, the East Side and Hegewisch. Lincoln Park's low-income "
          "share is raised by students living off campus. Some tracts near the Southeast site are outside Chicago and have no city EJ score.</p>")


# ---- map layer: block groups filled by share below twice the poverty line ----
BINS = [(0, 15, '#f2f0f7'), (15, 25, '#cbc9e2'), (25, 35, '#9e9ac8'), (35, 50, '#756bb1'), (50, 101, '#54278f')]
NODATA = '#d9d9d9'


def rgba(hex_, a):
    return f'rgba({int(hex_[1:3], 16)},{int(hex_[3:5], 16)},{int(hex_[5:7], 16)},{a})'


def chicago_low_income():
    q = urllib.parse.urlencode({'get': 'C17002_001E,' + ','.join(f'C17002_{i:03d}E' for i in range(2, 8)) + ',B19013_001E',
                                'for': 'place:14000', 'in': 'state:17', 'key': census.KEY})
    v = list(map(float, census.get(f'https://api.census.gov/data/{census.YEAR}/acs/acs5?{q}')[1][:8]))
    return 100 * sum(v[1:7]) / v[0], v[7]


def key_html(pct):
    """Inline colour key: five swatches with their ranges, the current class outlined."""
    cells = []
    for lo, hi, c in BINS:
        on = pct is not None and lo <= pct < hi
        lab = f'{lo}+' if hi > 100 else f'{lo}–{hi}'
        cells.append(f"<span style='display:inline-block;text-align:center;margin-right:2px'>"
                     f"<span style='display:block;width:30px;height:11px;background:{c};"
                     f"border:{'2px solid #111' if on else '1px solid rgba(0,0,0,.25)'};box-sizing:border-box'></span>"
                     f"<span style='font-size:10px;{'font-weight:bold' if on else 'opacity:.7'}'>{lab}%</span></span>")
    return "<div style='margin:4px 0 2px;white-space:nowrap'>" + ''.join(cells) + '</div>'


def fmt_pct(v, d=0):
    return '–' if v is None else f'{100 * v:.{d}f}%'


def bg_layer(bg_out, p, ej, city_pct, city_inc):
    site = {s['id']: s for s in SITES}
    feats = []
    for f in bg_out:
        pr = f['properties']
        g, s = pr['GEOID'], site[pr['site']]
        r = p.loc[g]
        small = pd.isna(r['pop']) or r['pop'] < 100 or pd.isna(r.pct_low_income)
        pct = None if small else 100 * float(r.pct_low_income)
        col = NODATA if pct is None else next(c for lo, hi, c in BINS if lo <= pct < hi)
        tract = g[:11]
        ejrow = ej.loc[tract] if tract in ej.index else None
        dist = pr['km']
        where = f"{dist:.1f} km ({dist / MILE:.1f} mi) from {s['name']}, {s['place']}"
        head = ('<b>Too few residents for a reliable figure</b>' if pct is None
                else f'<b>{pct:.0f}% live below twice the poverty line</b>')
        hover = (head + key_html(pct)
                 + f"<span style='font-size:12px'>Chicago overall: {city_pct:.0f}% · {where}</span>"
                 + "<br><i style='font-size:12px'>Click for this block group's data</i>")
        rows = [
            ('People', '–' if pd.isna(r['pop']) else f"{int(r['pop']):,}", ''),
            ('Below twice the poverty line', fmt_pct(None if small else r.pct_low_income), f'Chicago {city_pct:.0f}%'),
            ('Typical household income', '–' if pd.isna(r.median_hh_income) else f'${r.median_hh_income:,.0f}', f'Chicago ${city_inc:,.0f}'),
            ('People of colour', fmt_pct(None if small else r.pct_poc), ''),
            ('Households with limited English', fmt_pct(None if small else r.pct_limited_english), ''),
            ('Adults without a high-school diploma', fmt_pct(None if small else r.pct_no_hs), ''),
            ('Children under 5', fmt_pct(None if small else r.pct_under5, 1), ''),
            ('Adults 65 and over', fmt_pct(None if small else r.pct_65plus), ''),
            ('Social vulnerability (all six measures)', '–' if pd.isna(r.social_pctile) else f'{r.social_pctile:.0f}th percentile', 'of Cook County block groups'),
        ]
        tbl = ''.join(f"<tr style='border-top:1px solid rgba(128,128,128,.3)'><th {TL}>{a}</th><td {TD}>{b}</td>"
                      f"<td style='padding:4px 0 4px 6px;font-size:12px;opacity:.7'>{c}</td></tr>" for a, b, c in rows)
        if ejrow is not None:
            ejp = float(ejrow.CEJI_SCORE_PCTILE)
            ejtxt = (f"<p style='margin:10px 0 4px'><b>City EJ Index for this census tract: {ejp:.0f}th percentile</b>"
                     f"{' — an official EJ neighborhood (top quarter)' if ejp >= 75 else ''}.<br>"
                     f"Pollution burden {float(ejrow.POLLUTION_BURDEN_SCORE):.1f} of 10 · "
                     f"population characteristics {float(ejrow.POP_CHARACTERISTICS_SCORE):.1f} of 10.</p>")
        else:
            ejtxt = "<p style='margin:10px 0 4px;opacity:.8'>This tract is outside Chicago and has no city EJ Index score.</p>"
        detail = (f"<h3 style='margin:0 0 2px'>Block group {g[-1]}, census tract {int(tract[5:9])}.{tract[9:]}</h3>"
                  f"<div style='opacity:.75;margin-bottom:6px'>{where}</div>"
                  + (f"<div style='font-size:15px;margin:6px 0 0'>{head}</div>{key_html(pct)}" )
                  + f"<table style='border-collapse:collapse;width:100%;margin-top:8px'>{tbl}</table>{ejtxt}"
                  "<p style='margin:8px 0 0;font-size:12px;opacity:.8'>Source: U.S. Census Bureau, American Community Survey 2020–2024 "
                  "(5-year estimates, block group); City of Chicago, Chicago EJ Index 2023. Block-group estimates have wide margins of error.</p>"
                  f"<p style='margin:10px 0 0'><a href='#' data-feature='{s['id']}'>{html.escape(s['name'])}: the 1- and 2-mile summary</a> · "
                  "<a href='#' data-overlay-back='1'>Back to the panel</a></p>")
        geom = f['geometry']
        rnd = lambda c: [round(c[0], 5), round(c[1], 5)]
        if geom['type'] == 'Polygon':
            geom = {'type': 'Polygon', 'coordinates': [[rnd(c) for c in ring] for ring in geom['coordinates']]}
        else:
            geom = {'type': 'MultiPolygon', 'coordinates': [[[rnd(c) for c in ring] for ring in poly] for poly in geom['coordinates']]}
        feats.append({'type': 'Feature', 'id': 'bg-' + g, 'geometry': geom,
                      'properties': {'fid': 'bg-' + g, 'color': rgba(col, 0.62), 'stroke': 'rgba(60,50,90,0.55)',
                                     'hoverAttribute': hover, 'detail': detail}})
    return feats


def rings():
    feats = []
    for s in SITES:
        x, y = s['lonlat']
        for miles in (1, 2):
            rk = miles * MILE
            pts = [[round(x + rk / (111.32 * math.cos(math.radians(y))) * math.sin(a), 5),
                    round(y + rk / 110.54 * math.cos(a), 5)] for a in [i * 2 * math.pi / 96 for i in range(97)]]
            feats.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': pts},
                          'properties': {'color': 'rgba(0,0,0,0)', 'stroke': 'rgba(20,20,20,0.85)' if miles == 1 else 'rgba(20,20,20,0.5)'}})
    return feats


def main():
    p, ok = census.indicators()
    ej = pd.read_excel(os.path.join(HERE, 'raw/Chicago-EJ-Index-Values_2023.10.04.xlsx'), sheet_name='Indicator Values, Scores')
    ej.index = ej.CT_FIPS.astype('int64').astype(str)
    stats, bg_out, tr_out = {}, [], []
    for s in SITES:
        bgs = tiger(10, s['lonlat'], 2 * MILE)
        trs = tiger(8, s['lonlat'], 2 * MILE)
        stats[s['id']] = {}
        for rname, rk in (('1', MILE), ('2', 2 * MILE)):
            stats[s['id']][rname] = area_stats(p, ej, [f['properties']['GEOID'] for f in bgs if f['properties']['km'] <= rk],
                                               [f['properties']['GEOID'] for f in trs if f['properties']['km'] <= rk])
        for f in bgs:
            g = f['properties']['GEOID']
            if g in p.index:
                r = p.loc[g]
                f['properties'].update(site=s['id'], pop=int(r['pop']) if not pd.isna(r['pop']) else None,
                                       social_pctile=None if pd.isna(r.social_pctile) else float(r.social_pctile),
                                       **{k: None if pd.isna(r[k]) else round(float(r[k]), 4)
                                          for k in ('pct_low_income', 'pct_poc', 'pct_limited_english', 'pct_no_hs', 'median_hh_income')})
                bg_out.append(f)
        for f in trs:
            g = f['properties']['GEOID']
            f['properties']['site'] = s['id']
            if g in ej.index:
                f['properties'].update(ej_pctile=round(float(ej.loc[g, 'CEJI_SCORE_PCTILE']), 1),
                                       pollution_burden=round(float(ej.loc[g, 'POLLUTION_BURDEN_SCORE']), 2),
                                       pop_characteristics=round(float(ej.loc[g, 'POP_CHARACTERISTICS_SCORE']), 2))
            tr_out.append(f)
        a = stats[s['id']]
        print(f"{s['name']:20s} 1 mi: {a['1']['people']:>7,} people, EJ median {a['1']['ej_pctile_median']} | "
              f"2 mi: {a['2']['people']:>7,} people, EJ median {a['2']['ej_pctile_median']}, low income {a['2']['low_income']}%")
    os.makedirs(OUT, exist_ok=True)
    json.dump(stats, open(os.path.join(OUT, 'compare_sites.json'), 'w'), indent=1)
    json.dump({'type': 'FeatureCollection', 'features': bg_out}, open(os.path.join(OUT, 'compare_bg.geojson'), 'w'))
    json.dump({'type': 'FeatureCollection', 'features': tr_out}, open(os.path.join(OUT, 'compare_tracts.geojson'), 'w'))

    feats = [{'type': 'Feature', 'id': s['id'], 'geometry': {'type': 'Point', 'coordinates': list(s['lonlat'])},
              'properties': {'fid': s['id'], 'name': s['name'], 'icon': ICON, 'iconScale': 0.9,
                             'hoverAttribute': f"<b>{html.escape(s['name'])}</b><br>{html.escape(s['place'])}",
                             'detail': site_detail(s, stats)}} for s in SITES]
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(APP + 'general_iron_sites.geojson', 'w'))
    city_pct, city_inc = chicago_low_income()
    json.dump({'type': 'FeatureCollection', 'features': bg_layer(bg_out, p, ej, city_pct, city_inc)},
              open(APP + 'general_iron_poverty.geojson', 'w'))
    json.dump({'type': 'FeatureCollection', 'features': rings()}, open(APP + 'general_iron_rings.geojson', 'w'))
    globals()['CITY_PCT'] = city_pct
    panel = os.path.join(OUT, 'people_map.html')
    open(panel, 'w').write(overview(stats))
    print('Wrote the map layers to', APP, 'and the People panel to', panel)
    # the Shiny app reads it from its data/census/ folder (set PEREZ_APP to the app folder to copy it there)
    if os.environ.get('PEREZ_APP'):
        dest = os.path.join(os.environ['PEREZ_APP'], 'data', 'census', 'people_map.html')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, 'w').write(overview(stats))
        print('Copied to', dest)


if __name__ == '__main__':
    main()
