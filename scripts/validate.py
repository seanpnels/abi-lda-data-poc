#!/usr/bin/env python3
"""Stage 2 candidate QA. Diagnostic only; NOT compliance clearance."""
import csv, json, collections, datetime, os, sys
from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer

SRC = sys.argv[1] if len(sys.argv)>1 else 'work/candidates.geojsonseq'
OUT = sys.argv[2] if len(sys.argv)>2 else 'output/stage2'
os.makedirs(OUT, exist_ok=True)
nyc = (-74.26, 40.49, -73.68, 40.92)
category_rules = {
 'school': lambda t: t.get('amenity')=='school' or t.get('building')=='school',
 'daycare': lambda t: t.get('amenity') in ('kindergarten','childcare') or t.get('building')=='kindergarten',
 'worship': lambda t: t.get('amenity')=='place_of_worship' or t.get('building') in ('church','chapel','mosque','synagogue','temple'),
 'higher_education': lambda t: t.get('amenity') in ('college','university') or t.get('building') in ('college','university'),
 'substance_use_candidate': lambda t: t.get('social_facility') in ('drug_addiction','alcohol_addiction') or t.get('healthcare')=='speciality',
}
counts=collections.Counter(); geom_counts=collections.Counter(); examples=[]; matches=[]; errors=[]
# Test address reference is approximate: NOT the surveyed location of a billboard or facility footprint.
target = Point(-73.9884,40.7283)
project=Transformer.from_crs('EPSG:4326','EPSG:2263',always_xy=True).transform
p_target=transform(project,target)
with open(SRC,encoding='utf-8') as f:
 for line_num,line in enumerate(f,1):
  if not line.strip():continue
  try:
   # RFC 8142 GeoJSON Text Sequences prefix each record with ASCII RS (0x1E).
   record = line.lstrip('\x1e').strip()
   if not record: continue
   o=json.loads(record); props=o.get('properties') or {}; tags=props.get('tags') or {}
   # osmium export commonly flattens OSM tags directly into properties.
   if not tags: tags=props
   cats=[name for name,rule in category_rules.items() if rule(tags)]
   if not cats:continue
   geom=shape(o['geometry']) if o.get('geometry') else None
   if geom is None or geom.is_empty:counts['missing_geometry']+=1;continue
   name=str(tags.get('name',''))
   kind=geom.geom_type
   for c in cats:counts[c]+=1;geom_counts[(c,kind)]+=1
   counts['total_candidate_features']+=1
   if len(examples)<100:examples.append({'name':name,'categories':';'.join(cats),'geometry_type':kind,'osm_id':props.get('@id',props.get('id',''))})
   if ('middle collegiate' in name.lower() or 'st. thomas choir' in name.lower() or 'saint thomas choir' in name.lower()):
    try: distance_ft=round(transform(project,geom).distance(p_target),1)
    except Exception: distance_ft=None
    matches.append({'name':name,'categories':';'.join(cats),'geometry_type':kind,'osm_id':props.get('@id',props.get('id','')),'distance_to_approx_middle_church_reference_ft':distance_ft,'tags':json.dumps(tags,ensure_ascii=False)[:1200]})
  except Exception as e:
   counts['parse_errors']+=1
   if len(errors)<20:errors.append({'line':line_num,'error':str(e)})

# Fail closed: a successful workflow must never report an empty census after parsing failures.
if counts['parse_errors']:
 raise RuntimeError(f"Validation rejected: {counts['parse_errors']} GeoJSON records could not be parsed. Examples: {errors[:3]}")
if counts['total_candidate_features'] == 0:
 raise RuntimeError('Validation rejected: zero restricted-facility candidates were classified.')

def write_csv(path,rows,columns):
 with open(path,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
write_csv(os.path.join(OUT,'category_geometry_counts.csv'),[{'category':c,'geometry_type':g,'count':v} for (c,g),v in sorted(geom_counts.items())],['category','geometry_type','count'])
write_csv(os.path.join(OUT,'named_facility_matches.csv'),matches,['name','categories','geometry_type','osm_id','distance_to_approx_middle_church_reference_ft','tags'])
write_csv(os.path.join(OUT,'candidate_examples.csv'),examples,['name','categories','geometry_type','osm_id'])
report={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'counts':dict(counts),'geometry_counts':{f'{c}/{g}':n for (c,g),n in geom_counts.items()},'named_facility_matches':matches,'sample_errors':errors,'limitations':['DIAGNOSTIC ONLY. Not a complete facility census or compliance determination.','The Stage 1 tags-filter omits some possible facility tags; this report cannot quantify what was excluded.','An OSM point is not an actual building footprint; no building association is performed.','The approximate Middle Collegiate reference point is not suitable for compliance measurements.','Building polygons alone may lack the facility tag; this stage does not infer occupants.','The substance-use filter is deliberately incomplete and may include unrelated healthcare facilities.','No billboard inventory was uploaded or screened.']}
with open(os.path.join(OUT,'validation.json'),'w',encoding='utf-8') as f:json.dump(report,f,indent=2)
with open(os.path.join(OUT,'VALIDATION_README.txt'),'w') as f:
 f.write('ABI LDA STAGE 2 - DIAGNOSTIC ONLY\n\n')
 f.write('Total tagged candidate features: '+str(counts['total_candidate_features'])+'\n')
 f.write('Named matches: '+str(len(matches))+'\n')
 f.write('See validation.json and category_geometry_counts.csv.\n')
 f.write('NO COMPLIANCE CLEARANCE MAY BE INFERRED FROM THIS REPORT.\n')
print(json.dumps({'total':counts['total_candidate_features'],'named_matches':len(matches),'parse_errors':counts['parse_errors']},indent=2))
