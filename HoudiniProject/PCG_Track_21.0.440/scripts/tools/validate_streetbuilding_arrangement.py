"""Behavior contracts on final instances, independent of the migration script."""
from collections import Counter, defaultdict


def validate_arrangement(parent):
    from validate_streetbuilding_contract import (configure, geometry, require, signature,
        STYLE_CATALOG, catalog_module_rows, set_facade_override)
    a=parent.parent().createNode(parent.type().name(),'VERIFY_ARRANGEMENT')
    cases=0
    def records():
        g=geometry(a,'SELECT_FACADE_MODULES').freeze()
        rows=[]
        for p in g.points():
            role=p.stringAttribValue('module_role')
            if role not in ('Entrance','GroundShopDoor','GroundShop','GroundWall','MiddleWindow','MiddleBlank','SideWall','RearWall'):continue
            rows.append(dict(role=role,variant=p.stringAttribValue('module_variant'),
                path=p.stringAttribValue('unity_instance'),floor=p.intAttribValue('floor_index'),
                origin=p.attribValue('arrangement_origin'),right=p.attribValue('arrangement_right'),
                face=p.intAttribValue('face_index'),span=p.intAttribValue('module_span'),
                u=p.floatAttribValue('arrangement_u'),P=tuple(p.position()),cell=p.intAttribValue('cell_index')))
        return rows,g
    def group(rows):
        groups=defaultdict(list)
        for r in rows:groups[(r['floor'],r['face'],r['origin'],r['right'])].append(r)
        return {k:sorted(v,key=lambda x:x['u']) for k,v in groups.items()}
    def coverage(rows):
        for key,items in group(rows).items():
            cursor=0
            for r in items:
                require(abs(r['u']-r['span']-cursor)<.001,'Gap/overlap in final facade '+str(key))
                cursor+=r['span']*2
                x=r['origin'][0]+r['right'][0]*r['u']
                z=r['origin'][2]+r['right'][2]*r['u']
                require(abs(r['P'][0]+x)<.001 and abs(r['P'][2]-z)<.001,'Final pivot/metadata disagree')
    try:
        single='STYLE|2|4|3\n'+'\n'.join('|'.join(r) for r in catalog_module_rows(STYLE_CATALOG) if int(r[5])==1)
        sequences={}
        for mode in (0,1,2,3,4):
            configure(a,single,width=16,floors=4,attachments=0,rhythm=mode)
            set_facade_override(a,floor_from=2,floor_to=4,mode=2,rhythm=mode,window=(4,4),blank=(4,4))
            rows,g=records();coverage(rows)
            front=[v for k,v in group(rows).items() if k[0]==1 and k[1]==0][0]
            seq=['W' if r['role']=='MiddleWindow' else 'B' for r in front]
            sequences[mode]=''.join(seq)
            require(Counter(seq)==Counter(W=4,B=4),'Arrangement changed requested counts')
            for floor in (2,3):
                other=[v for k,v in group(rows).items() if k[0]==floor and k[1]==0][0]
                require([(r['u'],r['role'],r['span']) for r in front]==[(r['u'],r['role'],r['span']) for r in other],'Upper floors do not align')
            if mode in (1,2):require(sequences[mode]=='WBWBWBWB','Uniform is not evenly distributed: '+sequences[mode])
            if mode==4:require(sequences[mode]=='WWBBWWBB','Groups are not pairs')
            if mode==3:
                for x,y in zip(front,reversed(front)):
                    require(x['role']==y['role'] and x['span']==y['span'] and x['path']==y['path'],'Symmetric module pair mismatch')
                    require(abs(x['u']+y['u']-16)<.001,'Symmetric position mismatch')
            require(signature(g)==signature(geometry(a,'SELECT_FACADE_MODULES')),'Recook changed arrangement')
            cases+=1
        for unified in (0,1):
            for shape in (0,1):
                for corner in (0,1,2,3) if shape else (0,):
                    baseline=None;entrance=None
                    for mode in (0,1,3,4):
                        configure(a,STYLE_CATALOG,width=16,shape=shape,notch_side=corner,rhythm=mode,attachments=0)
                        a.parm('facade_overrides').set(0)
                        a.parm('unified_ground_walls').set(unified)
                        rows,g=records();coverage(rows)
                        counts=Counter((r['floor'],r['face'],r['origin'],r['role'],r['span']) for r in rows)
                        doors=[(r['P'],r['span']) for r in rows if r['role']=='Entrance']
                        if baseline is None:baseline=counts;entrance=doors
                        require(counts==baseline,'Changing arrangement changed module quantities/spans')
                        require(doors==entrance and len(doors)==1,'Changing arrangement moved entrance')
                        require(g.stringAttribValue('arrangement_report'),'No arrangement diagnostics')
                        geometry(a);cases+=1
        a.parm('unified_ground_walls').set(0)
        for cells,windows in ((2,1),(3,1),(5,3),(8,0),(8,8)):
            for mode in (0,1,3,4):
                configure(a,single,width=cells*2,floors=3,attachments=0,rhythm=mode)
                set_facade_override(a,floor_from=2,floor_to=3,mode=2,rhythm=mode,
                                    window=(windows,windows),blank=(cells-windows,cells-windows))
                rows,g=records();coverage(rows)
                front=[v for k,v in group(rows).items() if k[0]==1 and k[1]==0][0]
                require(sum(r['span'] for r in front if r['role']=='MiddleWindow')==windows,'Boundary quantity changed')
                geometry(a);cases+=1
        upper = validate_upper_uniform(parent)
        return {'status':'PASS','cases':cases,'sequences':sequences,'alignment':True,'coverage':True,'entrance_fixed':True,'upper_uniform':upper}
    finally:a.destroy()


def validate_upper_uniform(parent):
    """Independent final-instance oracle; never imports a patch or production VEX.

    Ordered partitions are enumerated only for small mixed-width fixtures.
    Integer objectives avoid floating point ties in the reference oracle.
    """
    from itertools import combinations_with_replacement
    from fractions import Fraction
    from validate_streetbuilding_contract import (configure, geometry, require,
        signature, STYLE_CATALOG, catalog_module_rows, style_row, SOURCE_PREFIX,
        set_facade_override)
    a=parent.parent().createNode(parent.type().name(),'VERIFY_UPPER_UNIFORM_A')
    roles=('MiddleWindow','MiddleBlank','SideWall','RearWall')
    cases=0; example=False; mixed_walls=False
    def rows(g):
        attributes={v.name() for v in g.pointAttribs()}
        return [{k:p.attribValue(k) for k in attributes} for p in g.points()]
    def key(r):
        return (r['floor_index'],r['face_index'],tuple(r['arrangement_origin']),tuple(r['arrangement_right']))
    def groups(records):
        result=defaultdict(list)
        for r in records:
            if r['floor_index']>0 and r['module_role'] in roles:result[key(r)].append(r)
        return {k:sorted(v,key=lambda r:r['arrangement_u']) for k,v in result.items()}
    def identity(r):
        return tuple((k,tuple(r[k]) if isinstance(r.get(k),(tuple,list)) else r.get(k))
                     for k in ('module_role','module_variant','unity_instance','module_span','orient','scale','pscale'))
    def objective(gaps,n,w):
        # Multiply squared errors by (2N)^2, yielding exact integer scores.
        primary=sum((2*n*g-w*(1 if i in (0,n) else 2))**2 for i,g in enumerate(gaps))
        cursor=0;drift=0
        for i,g in enumerate(gaps[:-1]):
            cursor+=g;drift+=(2*n*cursor-w*(2*i+1))**2
        return primary,drift,gaps[0]
    def verify():
        nonlocal cases,example,mixed_walls
        source=rows(geometry(a,'SELECT_FACADE_VARIANTS').freeze())
        result=geometry(a,'SELECT_FACADE_MODULES').freeze();out=rows(result)
        cw=float(geometry(a,'PARSE_UNITY_INSTANCE_CATALOG').attribValue('style_cell_width'))
        ins,outs=groups(source),groups(out)
        require(ins.keys()==outs.keys(),'Uniform moved modules across segments')
        for k,items in outs.items():
            before=ins[k]
            require(Counter(map(identity,before))==Counter(map(identity,items)),'Uniform changed module multiset')
            for window in (False,True):
                require([identity(r) for r in before if (r['module_role']=='MiddleWindow')==window]==
                        [identity(r) for r in items if (r['module_role']=='MiddleWindow')==window],
                        'Uniform changed ordered window/wall queue')
            base=min(r['cell_index'] for r in before);cursor=0;gaps=[0];window_spans=[];walls=[]
            for r in items:
                span=r['module_span'];center=(cursor+span*.5)*cw
                require(abs(r['arrangement_u']-center)<.001,'Uniform gap/overlap')
                require(r['cell_index']==base+cursor,'Uniform cell metadata mismatch')
                origin=r['arrangement_origin'];right=r['arrangement_right'];pos=r['P']
                require(abs(pos[0]+origin[0]+right[0]*center)<.001 and
                        abs(pos[2]-origin[2]-right[2]*center)<.001,'Uniform position/grid mismatch')
                require(r['name']==r['instance_prefix'] and
                        f'_Face{k[1]}_F{k[0]:02d}_C{base+cursor:02d}_' in r['name'],
                        'Uniform name/grid mismatch')
                cursor+=span
                if r['module_role']=='MiddleWindow':window_spans.append(span);gaps.append(0)
                else:gaps[-1]+=span;walls.append(span)
            n=len(window_spans);w=sum(walls)
            if n:
                if all(s==1 for s in walls):
                    cuts=[min(range(w+1),key=lambda x:(abs(Fraction(x)-Fraction(w*(2*i+1),2*n)),x)) for i in range(n)]
                    expected=[v-u for u,v in zip([0]+cuts,cuts+[w])]
                    require(gaps==expected,f'A rule mismatch {k}: {gaps} != {expected}')
                else:
                    mixed_walls=True
                    if len(walls)<=12 and n<=4:
                        prefix=[0]
                        for s in walls:prefix.append(prefix[-1]+s)
                        best=min(objective([prefix[v]-prefix[u] for u,v in zip((0,)+cuts,cuts+(len(walls),))],n,w)
                                 for cuts in combinations_with_replacement(range(len(walls)+1),n))
                        require(objective(gaps,n,w)==best,f'Mixed-wall partition is not optimal: {gaps}')
                if window_spans==[1,2,1] and w==8:
                    require(gaps==[1,3,3,1],'Three-window eight-wall acceptance failed');example=True
            require(cursor==sum(r['module_span'] for r in before),'Uniform changed coverage extent')
        # Verify downstream emits exactly the same positioned facade modules.
        final=[r for r in rows(geometry(a).freeze()) if r['floor_index']>0 and r['module_role'] in roles]
        exported=lambda r:(identity(r),tuple(round(v,5) for v in r['P']),r['floor_index'],r['face_index'],r['cell_index'])
        require(Counter(map(exported,final))==Counter(exported(r) for v in outs.values() for r in v),
                'Downstream changed final uniform instances')
        require(signature(result)==signature(geometry(a,'SELECT_FACADE_MODULES')),'Repeat cook changed uniform arrangement')
        # Follow a host using its original cell, not a cell already rewritten by
        # another module. Point order is unchanged by this arrangement stage.
        hosts={(key(r),r['cell_index']):i for i,r in enumerate(source)
               if r['floor_index']>0 and r['module_role'] in roles}
        for i,r in enumerate(source):
            if r['module_role']!='Cornice' or r['floor_index']<=0:continue
            host=hosts.get((key(r),r['cell_index']))
            if host is None:continue
            moved=out[i];before=source[host];after=out[host]
            expected=tuple(r['P'][j]+after['P'][j]-before['P'][j] for j in range(3))
            require(all(abs(moved['P'][j]-expected[j])<.001 for j in range(3)),
                    'Cornice followed the wrong original host')
            require(moved['cell_index']==after['cell_index'],'Cornice cell did not follow host')
            require(moved['name']==moved['instance_prefix'],'Cornice prefix mismatch')
        cases+=1
        return outs
    def setup(spans=(1,2),wall_spans=(1,),count=3,cells=12,cw=2,shape=0,corner=0,seed=29):
        catalog=[f'STYLE|{cw}|4|3']
        catalog+=['|'.join(r) for r in catalog_module_rows(STYLE_CATALOG) if int(r[2]) not in (4,5,10,11)]
        for span in spans:catalog.append(style_row(4,SOURCE_PREFIX+f'UniformWindow_{span}.fbx',width=span,floors=2))
        for role in (5,10,11):
            for span in wall_spans:catalog.append(style_row(role,SOURCE_PREFIX+f'UniformWall_{role}_{span}.fbx',width=span,floors=2))
        configure(a,'\n'.join(catalog),width=cells*cw,depth=cells*cw,floors=4,rhythm=1,
                  attachments=0,roof=0,shape=shape,notch_side=corner,seed=seed,notch_width=2*cw,notch_depth=2*cw)
        a.setParms(dict(ground_rule_schema_version=2,ground_floor_use=2,entrance_count_max=1,
                        facade_layout_mode=0,window_count_min=count,window_count_max=6,
                        facade_overrides=0,parapet_enabled=0,architectural_trim_enabled=0))
    try:
        for spans in ((1,),(2,),(1,2)):
            for count,cells in ((0,8),(1,8),(1,9),(3,12),(8,8),(5,6)):
                setup(spans=spans,count=count,cells=cells);verify()
        # Search the real solver's seed space instead of injecting a synthetic
        # point order or reusing production selection/arrangement functions.
        for seed in range(64):
            setup(seed=seed);verify()
            if example:break
        require(example,'Acceptance fixture did not exercise single/double/single + eight walls')
        for widths in ((2,),(1,2),(2,3)):
            setup(wall_spans=widths,cells=12,count=2);verify()
        require(mixed_walls,'Mixed-wall fixtures did not exercise indivisible wide walls')
        for shape,corner in ((0,0),(1,0),(1,1),(1,2),(1,3)):
            setup(shape=shape,corner=corner,cells=16);verify()
            a.setParms(dict(facade_layout_mode=1,window_count_min=2,window_count_max=6));verify()
        setup(cw=1.25);verify()
        setup();a.parm('architectural_trim_enabled').set(1);verify()
        setup(spans=(1,));aligned=verify()
        fronts=[v for k,v in sorted(aligned.items()) if k[1]==0]
        require(all([(r['cell_index'],identity(r)) for r in v]==
                    [(r['cell_index'],identity(r)) for r in fronts[0]] for v in fronts),
                'Identical quota/material/seed changed upper-floor arrangement')
        setup();a.parm('facade_rhythm').set(2);verify()
        setup();set_facade_override(a,floor_from=3,floor_to=3,mode=2,rhythm=1,window=(1,1))
        result=verify()
        require(sum(r['module_role']=='MiddleWindow' for k,v in result.items() if k[0]==2 and k[1]==0 for r in v)==1,
                'Local override lost its requested quota')
        report=geometry(a,'BUILD_METADATA').attribValue('upper_window_report')
        require('source=' in report and 'requested=' in report,'Override source diagnostics missing')
        return dict(status='PASS',cases=cases,example_1_3_3_1=example,mixed_wall_oracle=mixed_walls,
                    module_multiset=True,queue_order=True,coverage=True,non_two_meter_grid=True)
    finally:a.destroy()
