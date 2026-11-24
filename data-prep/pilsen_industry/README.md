# Industry & logistics around Pilsen

Builds `app/client/public/static/data/pilsen_industry.geojson` and `pilsen_industry_overview.html`.

Run from this folder, in order (needs geopandas; reads /media/brian/Legacy/chicago_geology):

1. `python3 extract.py` – Pilsen (Lower West Side) + 1 mile; clips the CMAP Land Use Inventory 2020 to it.
2. `python3 osm_export.py`, then `python3 sites.py` – merges touching parcels per category into sites; adds OpenStreetMap names.
3. `python3 curate.py ../../app/client/public/static/data` (first pass: writes sites_curated.gpkg)
4. `python3 enrich.py` – parcel owners (Cook County Assessor API, taxpayer of record), zoning, main building,
   OSM operator/website, Wikidata websites -> enrich.json.
   Optional: `python3 commons.py` lists Commons photos taken near each site; check them by eye, put the good ones
   in curate_images.py, then `python3 photo_credits.py` (author, licence, thumbnail -> images.json).
5. `python3 curate.py ../../app/client/public/static/data` again. Websites come from (in order) the WEBSITES table
   (incl. ones found by web search), OSM tags on the site, Wikidata, then the same business elsewhere in Chicago
   (osm_city_websites.csv: every named OSM feature with a website in python_runs/Chicago.osm.pbf).
6. `python3 parcels.py ../../app/client/public/static/data` – the parcels attached to each site, coloured by zoning
   in the City of Chicago zoning-map colours (gisapps.chicago.gov ExternalApps/Zoning MapServer layer 15). – keeps sites of 2 ha+, applies names,
   categories, merges, the "dozen to know" texts and the key-information table (edit NAME / HIGHLIGHTS /
   ACTIVITY / WEBSITES), writes the files. Private individuals who own parcels are shown as "Private owner".

Note: the site numbers used in curate.py come from the order of sites_all.gpkg; rerunning sites.py on
different inputs can renumber them.
