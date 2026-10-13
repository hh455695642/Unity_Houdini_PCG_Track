"""Cumulative human-maintenance checks.

Native equivalence uses the three captured old consumers solely as test oracles.
It compares topology, attribute definitions/precision, every value and groups
exactly (zero numeric tolerance); this conversion performs no floating math.
Transaction fault injection additionally checks the migration tool's recovery.
"""
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
NATIVE_TYPES={n:'blast' for n in ('FRONT_TARGET_FILTER','FRONT_POINTS_ONLY','SIDE_REAR_TARGET_FILTER','SIDE_REAR_POINTS_ONLY','REAL_INSTANCE_FILTER')}
NATIVE_TYPES.update({n:'attribdelete' for n in ('FRONT_INSTANCE_ATTRIBUTES','SIDE_REAR_INSTANCE_ATTRIBUTES','REAL_INSTANCE_ATTRIBUTES')})
KEEP='P orient scale unity_instance instance_prefix name building_id face_index floor_index cell_index module_span selection_seed module_role module_variant surface_role facade_band is_building_entrance is_shop_entrance lod chunk_id pcg_kind pcg_variant preview_missing preview_size'.split()

def fingerprint(g):
 import hou
 def schema(attributes):
  return [(a.name(),str(a.dataType()),a.size(),str(a.numericDataType()) if a.dataType() in (hou.attribData.Int,hou.attribData.Float) else None,a.isArrayType(),a.isTransformedAsNormal()) for a in sorted(attributes,key=lambda a:a.name())]
 def values(items,attributes):return {a.name():[i.attribValue(a) for i in items] for a in sorted(attributes,key=lambda a:a.name())}
 p,q=g.points(),g.prims();v=[v for prim in q for v in prim.vertices()]
 data=dict(schema=[schema(g.pointAttribs()),schema(g.primAttribs()),schema(g.vertexAttribs()),schema(g.globalAttribs())],
  points=values(p,g.pointAttribs()),prims=values(q,g.primAttribs()),verts=values(v,g.vertexAttribs()),
  detail={a.name():g.attribValue(a) for a in g.globalAttribs()},
  topology=[(str(prim.type()),[v.point().number() for v in prim.vertices()]) for prim in q],
  point_groups={x.name():[p.number() for p in x.points()] for x in g.pointGroups()},
  prim_groups={x.name():[p.number() for p in x.prims()] for x in g.primGroups()},
  edge_groups={x.name():[(e.points()[0].number(),e.points()[1].number()) for e in x.edges()] for x in g.edgeGroups()})
 return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def assert_native_network(asset):
 from validate_streetbuilding_contract import require
 c=asset.node('StreetBuildingCore')
 for name,kind in NATIVE_TYPES.items():require(c.node(name) is not None and c.node(name).type().name()==kind,'Native SOP missing/type changed: '+name)
 whitelist='* '+' '.join('^'+k for k in KEEP)
 for target,tag,group,role in [('DIRECT_UNITY_INSTANCE_FACADE','FRONT','@facade_target>1','front_and_secondary_instances'),('BUILD_DIRECT_SIDE_REAR_INSTANCES','SIDE_REAR','@facade_target<2','side_and_rear_instances')]:
  f,p,a=(c.node(tag+s) for s in ('_TARGET_FILTER','_POINTS_ONLY','_INSTANCE_ATTRIBUTES'))
  require(f.input(0)==c.node('SELECT_FACADE_MODULES') and p.input(0)==f and a.input(0)==p and c.node(target).input(0)==a,'Native chain wiring changed: '+tag)
  require(f.evalParm('group')==group and f.evalParm('grouptype')==3 and not f.evalParm('negate'),'Native face selection changed: '+tag)
  require(p.evalParm('group')=='*' and p.evalParm('grouptype')==4,'Native point-only boundary changed: '+tag)
  require(a.evalParm('ptdel')==whitelist and a.evalParm('primdel')=='*' and a.evalParm('vtxdel')=='*' and a.evalParm('dtldel')=='' and not a.evalParm('negate') and not a.evalParm('updatevar'),'Native attribute schema changed: '+tag)
  require('s@output_role="'+role+'";' in c.node(target).evalParm('snippet') and 'removepoint' not in c.node(target).evalParm('snippet'),'Role boundary regained filtering code')
 f,a,t=(c.node(n) for n in ('REAL_INSTANCE_FILTER','REAL_INSTANCE_ATTRIBUTES','FILTER_REAL_INSTANCES'))
 require(f.input(0)==c.node('MERGE_DIRECT_BUILDING_INSTANCES') and a.input(0)==f and t.inputs()[:2]==(a,c.node('MERGE_DIRECT_BUILDING_INSTANCES')),'Production filter wiring changed')
 require(f.evalParm('group')=='@preview_missing!=0' and f.evalParm('grouptype')==3 and not f.evalParm('negate'),'Missing-marker filter changed')
 require(a.evalParm('ptdel')=='preview_missing preview_size' and a.evalParm('dtldel')=='' and not a.evalParm('updatevar'),'Preview attribute removal changed')
 require('npoints(1)-npoints(0)' in t.evalParm('snippet') and 'removepoint' not in t.evalParm('snippet'),'Missing count is not an O(1) input-boundary count')
 d=c.node('VALIDATE_DIRECT_DETAIL_INSTANCES')
 require(d.evalParm('class')==0 and 'if (npoints(0)==0) return;' in d.evalParm('snippet'),'Detail validator must scan once and preserve the empty-input boundary')
 require(len(c.stickyNotes())==9 and len(c.networkBoxes())==9,'Repeated maintenance added navigation items')
 for n in c.children():require(n.comment() and any('\u4e00'<=ch<='\u9fff' for ch in n.comment()),'Missing Chinese node explanation: '+n.name())

def validate_maintenance(asset):
 import hou
 from validate_streetbuilding_contract import configure,geometry,STYLE_CATALOG,require
 assert_native_network(asset)
 contract=json.loads((ROOT/'HoudiniProject/PCG_Track_21.0.440/scripts/contracts/streetbuilding_contract.json').read_text(encoding='utf-8'))
 a=asset.parent().createNode(asset.type().name(),'VERIFY_MAINTENANCE_LOCKED')
 helper=asset.parent().createNode('geo','VERIFY_MAINTENANCE_ORACLES')
 checked=0; entry={}
 try:
  for child in helper.children():child.destroy()
  refs={}
  for name,snippet in contract['maintenance_reference_vex'].items():
   input_name='DETAIL_INSTANCE_POINTS' if name=='VALIDATE_DIRECT_DETAIL_INSTANCES' else 'MERGE_DIRECT_BUILDING_INSTANCES' if name=='FILTER_REAL_INSTANCES' else 'SELECT_FACADE_MODULES'
   source=helper.createNode('object_merge','INPUT_'+name);source.setParms(dict(objpath1=a.node('StreetBuildingCore/'+input_name).path(),xformtype=0))
   if name=='VALIDATE_DIRECT_DETAIL_INSTANCES':
    snippet=snippet.replace('../../unity_style_catalog',a.path()+'/unity_style_catalog')
    for sibling in ('SELECT_FACADE_MODULES','PARSE_UNITY_INSTANCE_CATALOG'):
     snippet=snippet.replace('op:../'+sibling,'op:'+a.node('StreetBuildingCore/'+sibling).path())
   oracle=helper.createNode('attribwrangle','ORACLE_'+name);oracle.setParms({'class':'point' if name=='VALIDATE_DIRECT_DETAIL_INSTANCES' else 'detail','snippet':snippet});oracle.setInput(0,source);refs[name]=oracle
  fixtures=[dict(shape=0),*[dict(shape=1,notch_side=n) for n in range(4)],dict(width=4,depth=4,floors=1),dict(width=16,depth=12,floors=12),dict(seed=73)]
  for schema in (0,2):
   for params in fixtures:
    configure(a,STYLE_CATALOG,**params)
    a.setParms(dict(ground_rule_schema_version=schema,facade_overrides=0))
    for name,oracle in refs.items():
     actual=a.node('StreetBuildingCore/'+name)
     require(fingerprint(actual.geometry())==fingerprint(oracle.geometry()),'Exact native equivalence failed: '+name+' '+str((schema,params)))
     require(not actual.errors() and not actual.warnings(),'Native consumer diagnostics: '+name)
     checked+=1
  configure(a,STYLE_CATALOG,attachments=0)
  for name,oracle in refs.items():
   require(fingerprint(a.node('StreetBuildingCore/'+name).geometry())==fingerprint(oracle.geometry()),'Empty-attachment native equivalence failed: '+name)
   checked+=1
  configure(a,STYLE_CATALOG,width=12,floors=4)
  c=a.node('StreetBuildingCore'); before=c.node('BUILD_FACADE_CELLS').geometry().intrinsicValue('pointcount')
  a.parm('building_width').set(16); after=c.node('BUILD_FACADE_CELLS').geometry().intrinsicValue('pointcount')
  require(c.node('PARSE_GENERATION_RULES').geometry().attribValue('effective_width')==16 and after>before,'Width entry does not reach facade cells')
  entry['width_m']={'before':12,'after':16,'cells_before':before,'cells_after':after}
  configure(a,STYLE_CATALOG,floors=4); before=c.node('BUILD_FACADE_CELLS').geometry().intrinsicValue('pointcount')
  a.parm('floor_count').set(6); g=c.node('BUILD_FACADE_CELLS').geometry();after=g.intrinsicValue('pointcount')
  require(max(p.intAttribValue('floor_index') for p in g.points())==5 and after>before,'Floor entry does not generate the sixth floor')
  entry['total_floors']={'before':4,'after':6,'cells_before':before,'cells_after':after,'maximum_floor_index':5}
  counts=[]
  for request in (0,2):
   configure(a,STYLE_CATALOG,floors=4)
   a.setParms(dict(ground_rule_schema_version=2,ground_floor_use=2,entrance_count_max=1,facade_overrides=0,facade_layout_mode=0,window_count_min=request,window_count_max=8))
   g=geometry(a); per_floor=[sum(p.stringAttribValue('module_role')=='MiddleWindow' and p.intAttribValue('face_index')==0 and p.intAttribValue('floor_index')==floor for p in g.points()) for floor in (1,2,3)]
   require(per_floor==[request]*3,'Fixed window entry does not apply once per upper floor/physical facade: '+str(per_floor))
   counts.append(per_floor)
  entry['windows_per_upper_floor_front']={'requests':[0,2],'actual_per_floor':counts,'hidden_random_max':8}
 finally:
  helper.destroy();a.destroy()
 return dict(status='PASS',native_exact_comparisons=checked,numeric_tolerance=0,entries=entry,boxes=9,notes=9,native_sops=8,rollback=validate_rollback(asset))

def benchmark(hda):
 import hou
 from validate_streetbuilding_contract import configure,STYLE_CATALOG
 from validate_streetbuilding_core_cleanup import OUTPUTS
 hou.hda.installFile(str(hda.resolve()),change_oplibraries_file=False,force_use_assets=True)
 a=hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0','BENCH_MAINTENANCE_LOCKED');results={}
 try:
  for source in (0,1):
   configure(a,STYLE_CATALOG,module_source=source)
   outputs=[a.node('StreetBuildingCore/'+n) for n in OUTPUTS];samples=[]
   for i in range(11):
    a.parm('variation_seed').set(100+i)
    start=time.perf_counter()
    for n in outputs:n.cook(force=True)
    elapsed=(time.perf_counter()-start)*1000
    if i>=2:samples.append(elapsed)
   results['proxy' if source==0 else 'instances']=dict(median_ms=statistics.median(samples),min_ms=min(samples),max_ms=max(samples),samples_ms=samples)
 finally:a.destroy()
 return dict(method='fresh locked hython instance; 2 warmups + 9 seeds; all 7 outputs; wall-clock Cook only',results=results)

def validate_rollback(asset):
 """Inject two failures into a disposable instance; never touch/save Live."""
 import hou
 import maintain_streetbuilding_network as migration
 from validate_streetbuilding_contract import require
 contract=json.loads((ROOT/'HoudiniProject/PCG_Track_21.0.440/scripts/contracts/streetbuilding_contract.json').read_text(encoding='utf-8'))
 private=asset.parent().createNode(asset.type().name(),'VERIFY_MAINTENANCE_ROLLBACK')
 original_node,original_layout=migration._node,migration._layout
 results=[]
 try:
  private.allowEditingOfContents();c=private.node('StreetBuildingCore')
  # Permanent regression oracles, not a .codex_tmp task file. Non-target VEX
  # is snapshotted from the freshly installed definition in this process.
  baseline={'nodes':[{'path':'/obj/StreetBuilding_DEV/StreetBuildingCore/'+n.name(),
   'type':n.type().name(),'parms':{'snippet':contract['maintenance_reference_vex'].get(n.name(),n.evalParm('snippet'))} if n.parm('snippet') else {}}
   for n in c.children()]}
  def parameter(parm):
   try:expression=parm.expression();language=str(parm.expressionLanguage())
   except hou.OperationFailed:expression=None;language=None
   return (parm.rawValue(),tuple(k.asCode() for k in parm.keyframes()),expression,language)
  def snapshot():
   return json.dumps(dict(
    nodes=[(n.name(),n.type().name(),list(n.position()),n.comment(),
     [(p.name(),parameter(p)) for p in n.parms()],
     [(i.inputIndex(),i.inputNode().name(),i.outputIndex()) for i in n.inputConnections()],
     n.isBypassed(),n.isDisplayFlagSet(),n.isRenderFlagSet(),
     n.parentNetworkBox().name() if n.parentNetworkBox() else None) for n in c.children()],
    notes=[(n.name(),n.text(),list(n.position()),list(n.size()),
     n.parentNetworkBox().name() if n.parentNetworkBox() else None) for n in c.stickyNotes()],
    boxes=[(b.name(),b.comment(),list(b.position()),list(b.size()),sorted(i.name() for i in b.items())) for b in c.networkBoxes()]),
    sort_keys=True,ensure_ascii=False)
  # Authored test channels and an alternate original Box/connection exercise
  # actual restoration rather than merely comparing untouched parameters.
  front=c.node('FRONT_TARGET_FILTER');points=c.node('FRONT_POINTS_ONLY')
  front.parm('group').setExpression("'@facade_target>1'",language=hou.exprLanguage.Python)
  front.parm('grouptype').setExpression('3',language=hou.exprLanguage.Hscript)
  front.setInput(0,c.node('EMPTY_GEOMETRY'))
  keys=[]
  for frame,value in ((1,0),(10,1)):
   key=hou.Keyframe();key.setFrame(frame);key.setValue(value);keys.append(key)
  points.parm('negate').setKeyframes(keys)
  points.parentNetworkBox().removeItem(points);c.findNetworkBox('30_FACADE_SELECTION').addItem(points)
  class InjectedFailure(RuntimeError):pass
  def failing_node(*args,**kwargs):
   result=original_node(*args,**kwargs)
   if result.name()=='FRONT_POINTS_ONLY':
    result.parm('negate').deleteAllKeyframes();result.parm('negate').set(1)
    temporary=c.createNode('null','ROLLBACK_FAULT_NODE',run_init_scripts=False)
    temporary.setDisplayFlag(True);temporary.setRenderFlag(True)
    raise InjectedFailure('native stage after parameter/connection/Box changes')
   return result
  def failing_layout(*args,**kwargs):
   original_layout(*args,**kwargs)
   note=c.findStickyNote('NOTE_30_FACADE_SELECTION')
   note.parentNetworkBox().removeItem(note);c.findNetworkBox('40_BUILDING_INSTANCES').addItem(note)
   raise InjectedFailure('navigation after note/position/Box dimension changes')
  for phase,hook in (('front',failing_node),('navigation',failing_layout)):
   before=snapshot()
   if phase=='front':migration._node=hook
   else:migration._layout=hook
   try:migration.apply(hou,phase=phase,save=False,core_path=c.path(),baseline=baseline)
   except InjectedFailure:pass
   else:raise AssertionError('Fault did not execute: '+phase)
   after=snapshot();require(before==after,'Maintenance failed to restore channels/connections/UI/Box: '+phase)
   results.append(dict(phase=phase,status='PASS',snapshot_sha256=hashlib.sha256(after.encode()).hexdigest()))
   migration._node=original_node;migration._layout=original_layout
 finally:
  migration._node=original_node;migration._layout=original_layout;private.destroy()
 return dict(status='PASS',faults=results,channel_languages=['Python','Hscript'],
  animated_keyframes=2,box_membership_restored=True,production_saved=False)

def scope_audit(manifest_path,snapshot_path):
 from pcg_regression_gate import capture_live,load_manifest,MODULES
 m=load_manifest(manifest_path,'StreetBuilding');b=json.loads(snapshot_path.read_text(encoding='utf-8'))
 now=capture_live('StreetBuilding',MODULES['StreetBuilding'],'127.0.0.1',18811)
 if now['public_interface']!=b['public_interface']:raise AssertionError('Public interface changed')
 exceptions={name for name in ('StreetBuildingCore/DIRECT_UNITY_INSTANCE_FACADE','StreetBuildingCore/BUILD_DIRECT_SIDE_REAR_INSTANCES','StreetBuildingCore/FILTER_REAL_INSTANCES')}
 for name,state in b['nodes'].items():
  actual=now['nodes'][name]
  for field in ('type','flags','parameters','inputs'):
   old,new=state[field],actual[field]
   if name in exceptions and field=='parameters':old={k:v for k,v in old.items() if k!='snippet'};new={k:v for k,v in new.items() if k!='snippet'}
   if name=='StreetBuildingCore/VALIDATE_DIRECT_DETAIL_INSTANCES' and field=='parameters':old={k:v for k,v in old.items() if k not in ('snippet','class')};new={k:v for k,v in new.items() if k not in ('snippet','class')}
   if name in exceptions and field=='inputs':continue
   if old!=new:raise AssertionError('Non-whitelisted semantic mutation: '+name+':'+field)
 if set(now['nodes'])-set(b['nodes'])!={'StreetBuildingCore/'+n for n in NATIVE_TYPES}:raise AssertionError('Native node inventory changed')
 return dict(status='PASS',original_nodes_compared=len(b['nodes']),public_interface_unchanged=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--hda',type=Path);p.add_argument('--benchmark',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--manifest',type=Path);p.add_argument('--rollback',action='store_true');args=p.parse_args()
 if args.capture:result=scope_audit(args.manifest,args.capture)
 elif args.benchmark:result=benchmark(args.hda);args.benchmark.write_text(json.dumps(result,indent=2),encoding='utf-8')
 else:
  import hou
  hou.hda.installFile(str(args.hda.resolve()),change_oplibraries_file=False,force_use_assets=True)
  entry=hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0','VERIFY_MAINTENANCE_ENTRY')
  result=validate_rollback(entry) if args.rollback else validate_maintenance(entry)
 print(json.dumps(result,ensure_ascii=False,indent=2))
