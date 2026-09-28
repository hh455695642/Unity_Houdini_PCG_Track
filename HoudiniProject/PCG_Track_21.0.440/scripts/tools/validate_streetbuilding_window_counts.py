"""Module-count contracts, independent of the migration patch and solver."""
from collections import Counter
import json

def validate_window_counts(parent):
    from validate_streetbuilding_contract import configure, geometry, require, style_row, STYLE_CATALOG, SOURCE_PREFIX, signature
    a=parent.parent().createNode(parent.type().name(),'VERIFY_WINDOW_MODULE_COUNTS')
    cases=0
    def setup(count=2, spans=(1,2), shape=0, notch=0, rear=0, width=12,depth=10):
        catalog='\n'.join(row for row in STYLE_CATALOG.splitlines() if not(row.startswith('M|') and row.split('|')[2]=='4'))
        for span in spans:
            catalog+='\n'+style_row(4,SOURCE_PREFIX+f'WindowContract_{span}.fbx',width=span,floors=2)
        configure(a,catalog,floors=5,attachments=0,roof=0,shape=shape,notch_side=notch,rear=rear,width=width,depth=depth)
        a.setParms(dict(ground_rule_schema_version=2,style_rule_source=0,ground_floor_use=2,
            entrance_count_max=1,facade_layout_mode=0,window_count_min=count,window_count_max=64,
            facade_overrides=0,parapet_enabled=0,blank_count_min=0,blank_count_max=64))
    def counts():
        g=geometry(a,'SELECT_FACADE_MODULES')
        result=Counter()
        for p in g.points():
            if p.intAttribValue('floor_index')>0 and p.stringAttribValue('module_role')=='MiddleWindow' and not p.intAttribValue('preview_missing'):
                result[(p.intAttribValue('floor_index'),p.intAttribValue('face_index'))]+=1
        return result
    try:
        setup()
        expected={(f,face):2 for f in range(1,5) for face in (0,1,2)}
        require(dict(counts())==expected,'Precise 2 must produce 2 WINDOW MODULES per floor and physical face: '+str(counts()))
        for spans in ((1,),(2,),(1,2)):
            for shape,notch in ((0,0),(1,0),(1,1),(1,2),(1,3)):
                for rear in (0,2):
                    setup(spans=spans,shape=shape,notch=notch,rear=rear)
                    got=counts();expected={(f,face):2 for f in range(1,5) for face in range(4 if rear else 3)}
                    require(dict(got)==expected,f'Physical face quota mismatch {spans,shape,notch,rear}: {got}')
                    cells=geometry(a,'BUILD_FACADE_CELLS'); placed=geometry(a,'SELECT_FACADE_MODULES')
                    coverage=Counter()
                    for p in placed.points():
                        if p.intAttribValue('floor_index')==0 or p.stringAttribValue('module_role') not in ('MiddleWindow','MiddleBlank','SideWall','RearWall'):continue
                        floor=p.intAttribValue('floor_index');face=p.intAttribValue('face_index');cell=p.intAttribValue('cell_index');span=p.intAttribValue('module_span')
                        for c in range(cell,cell+span):coverage[(floor,face,c)]+=1
                    expected_cells={(p.intAttribValue('floor_index'),p.intAttribValue('face_index'),p.intAttribValue('cell_index')) for p in cells.points() if p.intAttribValue('floor_index')>0}
                    require(set(coverage)==expected_cells and all(v==1 for v in coverage.values()),'Windows/walls overlap or leave holes')
                    before=signature(placed)
                    a.setParms(dict(blank_count_min=64,blank_count_max=0,window_count_max=0))
                    require(signature(geometry(a,'SELECT_FACADE_MODULES'))==before,'Hidden max or retired blank changed precise layout')
                    cases+=1
        for requested in (0,1,2,64):
            setup(count=requested,spans=(2,),width=6,depth=4)
            got=counts()
            require(all(v<=min(requested,1) for v in got.values()),'Narrow face exceeded feasible module count')
            require(sum(got.values())==12*min(requested,1),'Capacity clamp missed feasible count')
            cases+=1
        setup();a.setParms(dict(facade_layout_mode=1,window_count_min=1,window_count_max=3))
        first=signature(geometry(a,'SELECT_FACADE_MODULES'))
        require(all(1<=v<=3 for v in counts().values()),'Random request outside range')
        require(signature(geometry(a,'SELECT_FACADE_MODULES'))==first,'Fixed-seed output changed')
        a.parm('variation_seed').set(94)
        require(signature(geometry(a,'SELECT_FACADE_MODULES'))!=first,'Random seed ignored')
        setup()
        rules=dict(layoutMode=0,rhythm=1,windowMin=1,windowMax=8,blankMin=64,blankMax=64,
            groundUse=2,commercialDoorMin=1,commercialDoorMax=1,residentialDoorEnabled=False,shopfrontRatio=.65,
            trimEnabled=False,attachmentsEnabled=False,roofEnabled=False,parapetEnabled=False,parapetHeight=.6,density=0)
        a.setParms(dict(style_rule_source=1,style_override_upper=0,style_override_ground=1,unity_style_rules=json.dumps(dict(version=2,ground=rules,upper=rules,roof=rules))))
        require(set(counts().values())=={2},'Retired style data overrode the instance count')
        a.parm('style_override_upper').set(1)
        require(set(counts().values())=={2},'Instance upper override not applied')
        from validate_streetbuilding_contract import set_facade_override
        set_facade_override(a,floor_from=3,floor_to=3,mode=2,rhythm=1,window=(1,1))
        require(counts()[(2,0)]==1 and counts()[(1,0)]==2,'Floor override did not isolate target')
        report=geometry(a,'BUILD_METADATA').attribValue('upper_window_report')
        require('requested=' in report and 'actual=' in report and 'source=' in report,'Missing final window metadata')
        setup(spans=())
        require(not counts(),'Missing window catalog emitted real windows')
        require('no_compatible_window' in geometry(a,'BUILD_METADATA').attribValue('upper_window_report'),'Missing-resource reason not exposed')
        for mask in (1,4,8,15):
            setup(rear=2)
            rows=[]
            for row in a.evalParm('unity_style_catalog').splitlines():
                f=row.split('|')
                if len(f)==18 and f[2]=='4':f[10]=str(mask)
                rows.append('|'.join(f))
            a.parm('unity_style_catalog').set('\n'.join(rows))
            got=counts()
            require(all((face==0 and mask&1 or face in (1,2) and mask&4 or face==3 and mask&8) for _,face in got),'Disabled facade emitted windows')
            require(sum(got.values())==8*((1 if mask&1 else 0)+(2 if mask&4 else 0)+(1 if mask&8 else 0)),'Facade mask dropped feasible windows')
        for rhythm in (0,1,3,4):
            setup();a.parm('facade_rhythm').set(rhythm)
            require(sum(counts().values())==24,'Arrangement changed module count')
        return dict(status='PASS',cases=cases+14,unit='module',scope='floor/physical_face',blank_ignored=True)
    finally:a.destroy()
