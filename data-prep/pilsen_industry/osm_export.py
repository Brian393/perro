"""Named OSM polygons and points around Pilsen + 1 mile (run before sites.py)."""
import geopandas as gpd, warnings; warnings.filterwarnings('ignore')
bb = (-87.7075, 41.8203, -87.6158, 41.8745)
for f in ['chopped', 'bldg_poi']:
    for lyr in ['multipolygons', 'points']:
        m = gpd.read_file(f'/media/brian/Legacy/chicago_geology/chicago_{f}.osm.pbf', layer=lyr, bbox=bb)
        m[m['name'].notna()].to_file(f'osm_{f}_{lyr}.gpkg')
