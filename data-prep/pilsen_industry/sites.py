import geopandas as gpd, warnings, pandas as pd, sys; warnings.filterwarnings('ignore')
pd.set_option('display.width',250); pd.set_option('display.max_rows',300); pd.set_option('display.max_colwidth',60)
CAT={1431:'manufacturing',1433:'manufacturing',1420:'manufacturing',
     1432:'warehousing',1450:'warehousing',
     1511:'rail',1570:'rail',
     1520:'trucking',
     1561:'utilities',1562:'utilities',1563:'utilities',1564:'utilities',
     1330:'municipal'}
l=gpd.read_file('lui_zone.gpkg'); l['LANDUSE']=l.LANDUSE.astype(int)
l=l[l.LANDUSE.isin(CAT)].copy(); l['cat']=l.LANDUSE.map(CAT)
parts=[]
for c,g in l.groupby('cat'):
    u=g.buffer(4).union_all().buffer(-4)
    s=gpd.GeoDataFrame(geometry=[u],crs=l.crs).explode(index_parts=False)
    s['cat']=c; parts.append(s)
s=pd.concat(parts,ignore_index=True); s=gpd.GeoDataFrame(s,crs=l.crs)
s['ha']=s.area/1e4
# dominant LUI code per site
j=gpd.overlay(l[['LANDUSE','cat','geometry']], s.reset_index()[['index','geometry']], how='intersection')
j['a']=j.area
dom=j.sort_values('a').groupby('index').LANDUSE.last()
s['code']=dom
# names from OSM polygons
osm=pd.concat([gpd.read_file(f) for f in ['osm_chopped_multipolygons.gpkg','osm_bldg_poi_multipolygons.gpkg']]).to_crs(26916)
osm=osm[osm.name.notna()].drop_duplicates('name' if False else 'osm_way_id')
osm['oa']=osm.area
o=gpd.overlay(s.reset_index()[['index','geometry']], osm[['name','other_tags','building','geometry','oa']].reset_index(drop=True), how='intersection')
o['a']=o.area
o=o[(o.a>0.3*o.oa)|(o.a>3000)]
names=o.sort_values('a').groupby('index').agg(name=('name','last'), names=('name',lambda x:'; '.join(pd.unique(x[::-1])[:4])))
pts=gpd.read_file('osm_chopped_points.gpkg').to_crs(26916)
pts=pts[~pts.other_tags.fillna('').str.contains('bus|"highway"|traffic|crossing|stop_position|platform')]
pp=gpd.sjoin(pts[['name','other_tags','geometry']], s.reset_index()[['index','geometry']], predicate='within')
pn=pp.groupby('index').name.apply(lambda x:'; '.join(pd.unique(x)[:4])).rename('ptnames')
s=s.join(names).join(pn)
s.to_file('sites_all.gpkg')
for t in [1,2,3]:
    print(t, (s.ha>=t).sum(), s[s.ha>=t].cat.value_counts().to_dict())
