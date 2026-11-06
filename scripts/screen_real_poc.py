#!/usr/bin/env python3
"""Stage 4: review-only NYC placement screen against candidate OSM geometries."""
import csv, json, sys, time
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from shapely.geometry import shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer

src, inventory, out = map(Path,sys.argv[1:4]); out.mkdir(parents=True,exist_ok=True)
start=time.perf_counter()
project=Transformer.from_crs('EPSG:4326','EPSG:2263',always_xy=True).transform
cats={'school':('amenity',{'school'}),'daycare':('amenity',{'kindergarten','childcare'}),'worship':('amenity',{'place_of_worship'}),'university':('amenity',{'college','university'})}
buildings={'school':{'school'},'daycare':{'kindergarten'},'worship':{'church','chapel','mosque','synagogue','temple'},'university':{'college','university'}}
def classify(tags):
    result=[k for k,(tag,vals) in cats.items() if tags.get(tag) in vals or tags.get('building') in buildings[k]]
    if tags.get('social_facility') in {'drug_addiction','alcohol_addiction'}:result.append('substance_use_candidate')
    return result
features=[]; parse_errors=0; qualities=Counter()
with src.open(encoding='utf-8') as f:
    for line in f:
        line=line.strip().lstrip('\x1e')
        if not line:continue
        try:
            obj=json.loads(line)
            props=obj.get('properties') or {}
            tags=props.get('tags') or props
            categories=classify(tags)
            if not categories or not obj.get('geometry'):continue
            geom=transform(project,shape(obj['geometry']))
            if not geom.is_valid:geom=geom.buffer(0)
            if geom.is_empty:continue
            quality='mapped_polygon_unverified_building' if geom.geom_type in ('Polygon','MultiPolygon') else ('point_only' if geom.geom_type in ('Point','MultiPoint') else 'line_or_other')
            features.append({'geometry':geom,'quality':quality,'categories':categories,'name':tags.get('name',''),'osm_id':props.get('@id',obj.get('id',''))})
            qualities[quality]+=1
        except Exception as exc:
            parse_errors+=1
            if parse_errors<=3:print('Parse error:',repr(exc))
if parse_errors:raise RuntimeError(f'OSM parsing errors: {parse_errors}')
if not features:raise RuntimeError('No OSM facilities classified')
with inventory.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f); original_columns=reader.fieldnames or []; placements=list(reader)
if not placements:raise RuntimeError('No placements in input')
required={'Unit #','Latitude','Longitude'}
if not required.issubset(original_columns):raise RuntimeError('Missing input columns: '+str(required-set(original_columns)))
index=STRtree([x['geometry'] for x in features]); rows=[]; red=yellow=green=gray=0
for row in placements:
    output=dict(row)
    output.update({'stage4_status':'','nearest_candidate_distance_ft':'','nearest_candidate_name':'','nearest_candidate_categories':'','nearest_candidate_osm_id':'','nearest_candidate_geometry_quality':'','candidates_within_300ft':'','screening_rule_ft':250,'review_band_ft':50,'human_review_required':'YES','stage4_notes':''})
    try:
        lat=float(row['Latitude']); lon=float(row['Longitude'])
        if not (40<=lat<=42 and -75<=lon<=-72):raise ValueError('outside NYC demonstration coverage')
        point=transform(project,Point(lon,lat))
        matches=[]
        for idx in index.query(point.buffer(300)):
            feature=features[int(idx)]; dist=point.distance(feature['geometry'])
            if dist<=300:matches.append((dist,feature))
        matches.sort(key=lambda x:x[0]); output['candidates_within_300ft']=len(matches)
        polygon=[(d,f) for d,f in matches if f['quality']=='mapped_polygon_unverified_building']
        pointlike=[(d,f) for d,f in matches if f['quality']!='mapped_polygon_unverified_building']
        if polygon and polygon[0][0]<=250:status='RED_POTENTIAL_CONFLICT'
        elif polygon and polygon[0][0]<=300:status='YELLOW_NEAR_POLYGON'
        elif pointlike:status='YELLOW_UNVERIFIED_GEOMETRY'
        else:status='GREEN_NO_DETECTED_CONFLICT'
        if matches:
            dist,f=matches[0];output.update({'nearest_candidate_distance_ft':round(dist,1),'nearest_candidate_name':f['name'],'nearest_candidate_categories':';'.join(f['categories']),'nearest_candidate_osm_id':f['osm_id'],'nearest_candidate_geometry_quality':f['quality']})
        output['stage4_notes']='Candidate geometries are not verified building footprints; green does not certify compliance.'
    except Exception as exc:
        status='GRAY_UNABLE_TO_SCREEN';output['stage4_notes']=str(exc)
    output['stage4_status']=status;rows.append(output)
counts=Counter(r['stage4_status'] for r in rows)
with (out/'linknyc_250ft_screening.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (out/'stage4_audit.json').open('w',encoding='utf-8') as f:
    json.dump({'generated_utc':datetime.now(timezone.utc).isoformat(),'restriction_ft':250,'review_band_ft':50,'placements':len(rows),'status_counts':dict(counts),'candidate_features':len(features),'geometry_quality_counts':dict(qualities),'elapsed_seconds_screening_including_parse':round(time.perf_counter()-start,2),'limitations':['POC review-only; no compliance clearance','Facility polygons are not verified building footprints; may be campuses/grounds','Point-only and line-only facility data is incomplete','Missing OSM facilities cannot be inferred; green is not compliance','No facility-to-building association','OSM filter coverage is not certified','Distances use NYC EPSG:2263 US survey feet','No independent verification of input coordinates or past Streamlit statuses']},f,indent=2)
print('Stage4:',len(rows),'placements;',dict(counts),'elapsed',round(time.perf_counter()-start,2),'seconds')
