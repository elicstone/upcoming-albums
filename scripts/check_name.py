"""Offline check of the generated title patterns; never contacts a tracker."""
import argparse
import re
from update_feed import ROOT, validate_feed

parser = argparse.ArgumentParser()
parser.add_argument('release_name')
args = parser.parse_args()
content = (ROOT / 'upcoming-albums.txt').read_text(encoding='utf-8')
validate_feed(content)
matches = []
for pattern in content.splitlines():
    regex = re.escape(pattern.lower()).replace(r'\*', '.*').replace(r'\?', '.')
    if re.fullmatch(regex, args.release_name.lower()):
        matches.append(pattern)
print('\n'.join(matches) if matches else 'NO TITLE MATCH')
print('Offline title-pattern check only; no tracker or download client was contacted.')
