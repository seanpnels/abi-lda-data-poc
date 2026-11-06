#!/usr/bin/env python3
"""Stage 3: demonstrator only. Never certify compliance from this output."""
import csv, json, sys, math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
proj = Transformer.from_crs('EPSG:4326','EPSG:2263',always_xy=True).transform
# EPSG:2263 coordinates are US survey feet, sufficient for this NYC-only POC.
FACILITY_TAGS={'school':('amenity',{'school'}),'daycare':('amenity',{'kindergarten','childcare'}),'worship':('amenity',{'place_of_worship'}),'university':('amenity',{'college','university'})}
BUILDING_TAGS={'school':{'school'},'daycare':{'kindergarten'},'worship':{'church','chapel','mosque','synagogue','temple'},'university':{'college','university'}}
def categories(t):
    result=[]
    for c,(k,vals) in FACILITY_TAGS.items():
        if t.get(k) in vals or t.get('building') in BUILDING_TAGS[c]: result.append(c)
    if t.get('social_facility') in {'drug_addiction','alcohol_addiction'}: result.append('substance_use_candidate')
    return result
features=[]; counts=Counter(); errors=0
with SRC.open('r',encoding='utf-8') as fh:
    for line in fh:
        line=line.strip().lstrip('\x1e')
        if not line: continue
        try:
            d=json.loads(line); tags=d.get('properties',{}).get('tags') or {}; cats=categories(tags)
            if not cats or not d.get('geometry'): continue
            geom=shape(d['geometry'])
            if geom.is_empty: continue
            g=transform(proj,geom)
            if not g.is_valid: g=g.buffer(0)
            if g.is_empty: continue
            if g.geom_type in ('Polygon','MultiPolygon'): quality='mapped_polygon_not_verified_building'
            elif g.geom_type=='Point': quality='point_only_no_footprint'
            else: quality='line_or_other_not_verified_building'
            f={'id':str(d.get('properties',{}).get('@id',d.get('id',''))),'name':tags.get('name',''),'categories':cats,'geometry':g,'quality':quality}
            features.append(f); counts[quality]+=1
        except Exception as exc:
            errors+=1
            if errors<5: print('PARSE ERROR:',repr(exc))
if errors: raise RuntimeError(f'{errors} records failed parsing')
if not features: raise RuntimeError('No facilities classified')
# We deliberately choose mapped polygon centroids as synthetic fixtures, not real inventory.
# A centroid is inside many polygons but not all; representative_point is guaranteed inside.
polys=[f for f in features if f['quality']=='mapped_polygon_not_verified_building' and f['geometry'].bounds[0]>900000 and f['geometry'].bounds[2]<1100000 and f['geometry'].bounds[1]>100000 and f['geometry'].bounds[3]<300000]
if not polys: raise RuntimeError('No NYC polygon fixtures available')
fixtures=[]; used=set()
for f in polys:
    cat=f['categories'][0]
    if cat in used: continue
    used.add(cat)
    p=f['geometry'].representative_point()
    fixtures.append((f'SYNTHETIC_{cat.upper()}_INSIDE',p,500))
    fixtures.append((f'SYNTHETIC_{cat.upper()}_OFFSET_600FT',Point(p.x+600,p.y),500))
    if len(used)>=4: break
if not fixtures: raise RuntimeError('No synthetic fixtures created')
geoms=[f['geometry'] for f in features]; tree=STRtree(geoms)
rows=[]
for label,p,limit in fixtures:
    candidates=tree.query(p.buffer(limit+50))
    hits=[]
    for idx in candidates:
        f=features[int(idx)]; dist=p.distance(f['geometry']);
        if dist<=limit+50: hits.append((dist,f))
    hits.sort(key=lambda x:x[0]); polygon_hits=[(d,f) for d,f in hits if f['quality']=='mapped_polygon_not_verified_building']
    point_hits=[(d,f) for d,f in hits if f['quality']=='point_only_no_footprint']
    if polygon_hits and polygon_hits[0][0]<=limit: status='RED_POTENTIAL_CONFLICT'
    elif polygon_hits and polygon_hits[0][0]<=limit+50: status='YELLOW_NEAR_POLYGON'
    elif point_hits: status='YELLOW_POINT_ONLY_REVIEW'
    else: status='GREEN_NO_DETECTED_CONFLICT_IN_CANDIDATES'
    best=hits[0] if hits else None
    rows.append({'fixture':label,'synthetic':True,'buffer_ft':limit,'status':status,'nearest_mapped_candidate_ft':round(best[0],1) if best else '', 'nearest_candidate_name':best[1]['name'] if best else '', 'nearest_candidate_categories':';'.join(best[1]['categories']) if best else '', 'nearest_geometry_quality':best[1]['quality'] if best else '', 'candidate_hits_within_550ft':len(hits),'review_required':True})
with (OUT/'synthetic_screening_results.csv').open('w',newline='',encoding='utf-8') as fh:
    writer=csv.DictWriter(fh,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
# Explicitly capture the caveats: a tagged polygon is not necessarily a building footprint;
# an absent tag is not evidence that the facility does not exist.
report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source':'New York State Geofabrik latest OSM PBF, fetched during workflow','total_classified_candidate_geometries':len(features),'geometry_quality_counts':dict(counts),'synthetic_test_points':len(rows),'synthetic_status_counts':dict(Counter(r['status'] for r in rows)),'limitations':['POC ONLY; synthetic locations are not billboards.','Candidate polygons may be parcels, campuses or grounds, not building footprints.','Point-only facilities are not treated as verified building polygons.','Stage 1 tag filters omit some facilities, especially substance-use facilities.','No building-to-facility association, full coverage certification, or real inventory validation.','Green means no detected conflict in the limited candidate dataset, never compliance clearance.','EPSG:2263 is appropriate for the NYC demonstration, not statewide or nationwide screening.','Middle Collegiate Church is NOT validated by this synthetic test.']}
(OUT/'stage3_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(OUT/'README.txt').write_text('STAGE 3 — SYNTHETIC SCREENING ENGINE DEMONSTRATOR\n\nThis is NOT a compliance clearance tool.\nRead stage3_report.json for explicit limitations.\nThe CSV contains only generated points derived from mapped candidate polygons; no ABI inventory is used.\n',encoding='utf-8')
print(json.dumps(report,indent=2))
