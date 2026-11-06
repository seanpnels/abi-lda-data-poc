"""Build validated 209 DMA boundaries and Census state polygons for Stage 6.
Dependencies: requests, shapely, pyshp. Never invent or silently truncate DMA coverage.
"""
import io, json, zipfile
from pathlib import Path
import requests
import shapefile
from shapely.geometry import shape, mapping

DMA_URL = ('https://servicesdev.arcgis.com/f126c8da131543019b05e4bfab6fc6ac/'
           'ArcGIS/rest/services/Esri_Demographics_2025_Base_01_gdb/FeatureServer/2/query')
CENSUS_URL = 'https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip'
OUT = Path('work'); OUT.mkdir(exist_ok=True)
s = requests.Session()


def arcgis_query(params):
    """Request ArcGIS data and fail explicitly on service-level errors."""
    response = s.get(DMA_URL, params=params, timeout=180)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS query error: {data['error']}")
    return data


# Request object IDs separately; ArcGIS returnIdsOnly is not subject to the
# normal feature-transfer record limit.
id_response = arcgis_query({"where": "1=1", "returnIdsOnly": "true", "f": "json"})
object_id_field = id_response.get("objectIdFieldName") or "OBJECTID"
object_ids = id_response.get("objectIds")
if not isinstance(object_ids, list):
    raise RuntimeError("ArcGIS did not return an objectIds list")
object_ids = sorted(set(object_ids))
print(f"ArcGIS reported {len(object_ids)} unique DMA feature object IDs", flush=True)
if len(object_ids) != 209:
    raise RuntimeError(f"Expected exactly 209 DMA object IDs; got {len(object_ids)}")

# Small batches avoid service-imposed maxRecordCount and URL-length limits.
# Fail closed if any batch returns fewer features than requested.
features = []
for offset in range(0, len(object_ids), 20):
    batch = object_ids[offset:offset + 20]
    data = arcgis_query({
        "objectIds": ",".join(str(x) for x in batch),
        "outFields": f"{object_id_field},ID,name",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    received = data.get("features")
    if not isinstance(received, list) or len(received) != len(batch):
        raise RuntimeError(
            f"DMA batch {offset // 20 + 1}: requested {len(batch)} features, "
            f"received {len(received) if isinstance(received, list) else 'invalid response'}"
        )
    features.extend(received)
    print(f"Fetched {len(features)}/{len(object_ids)} DMA geometries", flush=True)

if len(features) != 209:
    raise RuntimeError(f"Expected exactly 209 DMAs; got {len(features)}")
ids=set(); dma=[]
for f in features:
    p=f.get('properties') or {}; code=str(p.get('ID','')).strip(); name=str(p.get('name','')).strip()
    if not code or not name or code in ids: raise RuntimeError('Invalid/duplicate DMA')
    g=shape(f['geometry'])
    if g.is_empty or not g.is_valid: raise RuntimeError(f'Invalid DMA polygon: {name}')
    ids.add(code); dma.append({'type':'Feature','properties':{'id':code,'name':name},'geometry':mapping(g)})
resp=s.get(CENSUS_URL,timeout=180);resp.raise_for_status()
z=zipfile.ZipFile(io.BytesIO(resp.content)); shp=next(n for n in z.namelist() if n.endswith('.shp')); root=shp[:-4]
reader=shapefile.Reader(shp=io.BytesIO(z.read(root+'.shp')),
                        shx=io.BytesIO(z.read(root+'.shx')),
                        dbf=io.BytesIO(z.read(root+'.dbf')))
fields=[x[0] for x in reader.fields[1:]]
# Geofabrik US state extracts are available for 50 states and DC. Exclude territories.
exclude={'Puerto Rico','Guam','American Samoa','Northern Mariana Islands','United States Virgin Islands'}
states=[]
for item in reader.iterShapeRecords():
    p=dict(zip(fields,item.record)); name=str(p['NAME'])
    if name in exclude:continue
    g=shape(item.shape.__geo_interface__)
    if not g.is_valid:g=g.buffer(0)
    if g.is_empty:continue
    states.append({'type':'Feature','properties':{'name':name,'slug':name.lower().replace(' ','-')},
                   'geometry':mapping(g.simplify(.003,preserve_topology=True))})
if len(states)!=51:raise RuntimeError(f'Expected 50 states + DC, got {len(states)}')
index={'schema_version':1,'dma_source':DMA_URL,'state_source':CENSUS_URL,
       'dma':{'type':'FeatureCollection','features':dma},
       'states':{'type':'FeatureCollection','features':states}}
(OUT/'dma-state-index.json').write_text(json.dumps(index,separators=(',',':')))
print('Validated DMA boundaries:',len(dma),'states:',len(states))
