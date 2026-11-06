import json
import pathlib
import sys
from datetime import datetime, timezone

out = pathlib.Path(sys.argv[1]); candidate = pathlib.Path(sys.argv[2])
manifest = {
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'region': 'New York State (NYC validation subset to follow)',
    'source': 'https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf',
    'candidate_pbf_bytes': candidate.stat().st_size,
    'status': 'EXTRACTION ONLY — NOT VALIDATED FOR COMPLIANCE SCREENING',
    'limitations': [
        'This candidate filter is intentionally broad and incomplete.',
        'Substance-use facilities require additional tagging analysis.',
        'Building-to-facility association and complete footprint semantics are not validated.',
        'No screening or distance calculation is performed in this workflow.',
        'No daily schedule or persistent production storage is configured.'
    ]
}
(out/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
