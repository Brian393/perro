"""Thumbnail URL, author and licence for the reviewed photos listed in curate.py IMAGES -> images.json."""
import json, re, html, urllib.request, urllib.parse
from curate_images import IMAGES  # noqa: E402  (kept in a tiny module so this runs without the rest of curate.py)
q = urllib.parse.urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo', 'iiprop': 'extmetadata|url', 'iiurlwidth': 640,
                            'titles': '|'.join('File:' + f for f in IMAGES.values())})
r = json.load(urllib.request.urlopen(urllib.request.Request('https://commons.wikimedia.org/w/api.php?' + q,
                                                            headers={'User-Agent': 'perro-map-data-prep/1.0'}), timeout=60))
out = {}
for p in r['query']['pages'].values():
    ii = p['imageinfo'][0]; m = ii['extmetadata']
    out[p['title'][5:]] = dict(thumb=ii['thumburl'], page=ii['descriptionurl'],
                               artist=re.sub('<[^>]+>', '', html.unescape(m.get('Artist', {}).get('value', ''))).strip(),
                               license=m.get('LicenseShortName', {}).get('value', ''))
json.dump(out, open('images.json', 'w'), indent=1)
print(len(out), 'photos')
