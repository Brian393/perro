# Pilsen vulnerability layers

Background: the city's February 2022 denial of the Southside Recycling (General Iron) permit rested on a
health impact assessment that ranked nearby census block groups among the most vulnerable to air
pollution in Chicago. These scripts build the equivalent picture around Sims Metal, 2500 S. Paulina.

| Step | Script | Source | Output |
|---|---|---|---|
| 1 | `census.py` | Census API, ACS 5-year 2020–2024, block groups; TIGERweb boundaries | `out/pilsen_bg_social.geojson`, `.csv` |
| 2 | `join_ej.py` | Chicago EJ Index 2023 (CDPH Cumulative Impact Assessment), tracts | `out/pilsen_tract_ej.geojson`, `.csv` |
| 3 | `compare.py` | Both, for 1 and 2 miles around Sims, General Iron (Lincoln Park) and Southside Recycling (Southeast Side) | `out/compare_*.json/geojson`; map layers `general_iron_{poverty,rings,sites}.geojson` in `app/client/public/static/data/`; People-tab text `out/people_map.html` |

**Step 1** ranks every Cook County block group (population ≥ 100) on six census indicators: children
under 5, adults 65+, income below 200% of poverty, people of colour, limited-English households, adults
without a high-school diploma. `social_score` is the mean of the six county percentiles;
`social_pctile` ranks that score. This is the social half of vulnerability only: the census has no
health or pollution data.

**Step 2** needs the city's file, which chicago.gov only serves to browsers. Download
<https://www.chicago.gov/content/dam/city/depts/doe/supp_info/Chicago-EJ-Index-Values_2023.10.04.xlsx>
into `raw/`, then run `python3 join_ej.py`. It marks the city's own "EJ neighborhoods" (score ≥ 75, or
≥ 70 next to a tract ≥ 75). Methodology:
<https://www.chicago.gov/content/dam/city/depts/doe/supp_info/CIA_ChicagoEnvironmentalJusticeIndexMethodology_Updated_11.21.2023.pdf>

The Census key is read from `~/.census_key` (never commit it). Study area: lon −87.735 to −87.625,
lat 41.815 to 41.875.

**Step 3** feeds the People chapter of the Sims Permit Case (legend item `sims_case`; chapters in
`app.windrose.chapters` of app-conf.json). The map layers are served by the map app; the panel text
goes to the Shiny app, which reads `data/census/people_map.html`. Run it as
`PEREZ_APP=<path to the sims_permit app> python3 burden.py` (and `compare.py`) to copy the files there.

**Step 4** `burden.py` builds the Cumulative Burdens tab of the Sims Permit Case: every block group within
2 miles of the three sites, scored on People (ACS 2020-24, six indicators ranked against all Illinois block
groups, as Illinois EPA screens), Health (asthma, heart disease, low birth weight, children's blood lead) and
Pollution (pollution-burden score), both from the city's EJ Index by tract; the cumulative score is the mean
of the three, ranked among all Chicago block groups. Also attaches Illinois EPA EJ Start status and the city's
EJ-neighborhood flag. Run as `PEREZ_APP=<app folder> python3 burden.py` to copy `burden_bg.geojson` and
`burden_sites.json` into the Shiny app's `data/census/`.
