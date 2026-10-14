"""Independent door contracts: final output, authoring weights and small exhaustive fixtures."""
from collections import Counter
from functools import lru_cache
import re
import time


def validate_doors(parent):
    from validate_streetbuilding_contract import configure, geometry, require, STYLE_CATALOG, style_row, SOURCE_PREFIX
    a=parent.parent().createNode(parent.type().name(),'VERIFY_DOOR_WEIGHT_PLACEMENT')
    samples=512
    results=[]
    cases=0
    started=time.perf_counter()
    base='\n'.join(r for r in STYLE_CATALOG.splitlines()
                   if not(r.startswith('M|') and int(r.split('|')[2]) in (0,1,2,3)))

    def catalog(doors, walls=(1,), shops=(), wall_mask=15, shop_mask=15, height=4):
        rows=[base]
        for name,span,weight,mask in doors:
            rows.append(style_row(3,SOURCE_PREFIX+name+'.fbx',width=span,height=height,
                                  weight=weight,facades=mask,floors=1))
        for role,widths,mask in ((2,walls,wall_mask),(0,shops,shop_mask)):
            for span in widths:
                rows.append(style_row(role,SOURCE_PREFIX+f'DoorTest{role}_{span}.fbx',width=span,
                                      height=height,facades=mask,floors=1))
        return '\n'.join(rows)

    def setup(raw, width=12, depth=12, use=2, number=1, shops=0, rear=2, shape=0):
        configure(a,raw,width=width,depth=depth,floors=1,attachments=0,roof=0,rear=rear,shape=shape)
        a.setParms(dict(ground_rule_schema_version=2,ground_floor_use=use,residential_door_enabled=1,
            entrance_count_max=number,facade_layout_mode=0,shopfront_control=0,shopfront_quantity_mode=0,
            shopfront_count=shops,shopfront_count_min=0,shopfront_count_max=64,facade_overrides=0,
            architectural_trim_enabled=0,parapet_enabled=0,layout_seed=0,
            shopfront_face_0=1,shopfront_face_1=1,shopfront_face_2=1,shopfront_face_3=1))

    def output():
        return geometry(a,'SELECT_FACADE_MODULES')

    def doors(value=None):
        return [p for p in (value if value is not None else output()).points()
                if p.intAttribValue('floor_index')==0
                and p.stringAttribValue('module_role') in ('Entrance','GroundShopDoor')
                and not p.intAttribValue('preview_missing')]

    def door_signature():
        return tuple(sorted((p.intAttribValue('face_index'),p.intAttribValue('cell_index'),
                             p.intAttribValue('module_span'),p.stringAttribValue('unity_instance')) for p in doors()))

    def coverage(value):
        cells=[p for p in geometry(a,'BUILD_FACADE_CELLS').points() if p.intAttribValue('floor_index')==0]
        runs={(p.intAttribValue('face_index'),p.intAttribValue('cell_index')):
              p.intAttribValue('run_cell_count')-p.intAttribValue('run_local_cell') for p in cells}
        found=Counter()
        for p in value.points():
            if p.intAttribValue('floor_index')!=0 or p.stringAttribValue('module_role') not in (
                    'Entrance','GroundShopDoor','GroundShop','GroundWall'):continue
            face,cell,span=(p.intAttribValue(n) for n in ('face_index','cell_index','module_span'))
            require(not p.intAttribValue('preview_missing') and bool(p.stringAttribValue('unity_instance')),
                    'Complete fixture emitted a missing Prefab preview')
            require((face,cell) in runs and span<=runs[(face,cell)],'Final module crossed a facade run')
            for c in range(cell,cell+span):found[(face,c)]+=1
        require(set(found)==set(runs) and all(v==1 for v in found.values()),
                'Final door/shop/wall output leaves holes or overlaps')

    def front_shops(value):
        return sum(p.intAttribValue('floor_index')==0 and p.intAttribValue('face_index')==0
                   and p.stringAttribValue('module_role')=='GroundShop' for p in value.points())

    try:
        for use in (1,2):
            for wa,wb in ((1,1),(1,9),(9,1)):
                setup(catalog((('DoorWeightA',1,wa,15),('DoorWeightB',1,wb,15)),height=3 if use==1 else 4),use=use)
                counts=Counter()
                for seed in range(samples):
                    a.parm('layout_seed').set(seed)
                    got=doors()
                    require(len(got)==1,'Weight sampling changed the door count')
                    counts[got[0].stringAttribValue('module_variant')]+=1
                require(abs(counts['DoorWeightA']/samples-wa/(wa+wb))<=.08,
                        f'Biased door weights: {use,wa,wb,counts}')
                results.append(dict(use=use,weights=[wa,wb],counts=dict(counts)))
                cases+=1

        setup(catalog((('DoorWeightA',1,1,1),('DoorWeightB',6,1,1))))
        counts=Counter()
        for seed in range(samples):
            a.parm('layout_seed').set(seed)
            value=output()
            counts[doors(value)[0].stringAttribValue('module_variant')]+=1
            if seed<8:coverage(value)
        require(abs(counts['DoorWeightA']/samples-.5)<=.08,f'Position count leaked into weights: {counts}')
        results.append(dict(position_counts=[6,1],counts=dict(counts)))
        cases+=1

        raw=catalog((('DoorWeightA',1,1,15),('DoorWeightB',2,9,15)))
        setup(raw)
        for seed in range(12):
            a.parm('layout_seed').set(seed)
            before=door_signature()
            require(door_signature()==before,'Door changed on recook')
            rows=raw.splitlines()
            a.parm('unity_style_catalog').set('\n'.join([rows[0]]+list(reversed(rows[1:]))))
            require(door_signature()==before,'Catalog order changed a door')
            a.parm('unity_style_catalog').set(raw)
        # The existing catalog parser rejects invalid authoring before allocation.
        for weight in (0,-5):
            setup(catalog((('DoorInvalid',1,weight,15),('DoorValid',1,1,15))))
            target=a.node('StreetBuildingCore/PARSE_UNITY_INSTANCE_CATALOG')
            try:target.cook(force=True)
            except Exception:pass
            require(bool(target.errors()),'Invalid authoring weight reached generation')
        cases+=2

        setup(catalog((('DoorTwo',2,1,15),),walls=(2,)))
        positions=set()
        for seed in range(64):
            a.parm('layout_seed').set(seed)
            value=output()
            cell=doors(value)[0].intAttribValue('cell_index')
            require(cell in (0,2,4),'Six-cell wall selected an impossible door position')
            positions.add(cell)
            coverage(value)
        require(positions=={0,2,4},'Not all feasible door positions are reachable')
        cases+=1
        setup(catalog((('DoorImpossible',1,1000,15),('DoorPossible',2,1,15)),walls=(2,)))
        for seed in range(24):
            a.parm('layout_seed').set(seed)
            value=output()
            require(doors(value)[0].stringAttribValue('module_variant')=='DoorPossible',
                    'Infeasible high-weight door beat a feasible style')
            coverage(value)
        cases+=1

        # Exhaustive small tiling oracle is independent of production dynamic programming.
        @lru_cache(None)
        def tilings(length):
            if length==0:return frozenset({0})
            values=set()
            if length>=3:values.update(tilings(length-3))
            if length>=2:values.update(v+1 for v in tilings(length-2))
            return frozenset(values)
        exact={c for c in range(7) if any(l+r==3 for l in tilings(c) for r in tilings(6-c))}
        require(exact=={0,2,4,6},'Invalid exhaustive fixture')
        raw=catalog((('DoorOne',1,1,1),),walls=(3,),shops=(2,),shop_mask=1)
        raw+='\n'+style_row(2,SOURCE_PREFIX+'RearWallOne.fbx',height=4,floors=1,facades=8)
        setup(raw,width=14,shops=3)
        a.setParms(dict(shopfront_face_1=0,shopfront_face_2=0,shopfront_face_3=0))
        for seed in range(32):
            a.parm('layout_seed').set(seed)
            value=output()
            require(front_shops(value)==3,'Shop count compressed before trying feasible door positions')
            require(doors(value)[0].intAttribValue('cell_index') in exact,'Door escaped exhaustive feasible set')
            coverage(value)
        cases+=1

        # Five remaining cells require a three-cell shop plus a two-cell wall.
        setup(catalog((('DoorOne',1,1,1),),walls=(2,),shops=(3,),shop_mask=1),shops=2)
        a.setParms(dict(shopfront_face_1=0,shopfront_face_2=0,shopfront_face_3=0))
        for seed in range(12):
            a.parm('layout_seed').set(seed)
            value=output()
            require(front_shops(value)==1 and len(doors(value))==1,'True shop shortage changed doors or lost mixed tiling')
            report=geometry(a,'BUILD_METADATA').attribValue('ground_shopfront_report')
            require('requested=2 actual=1' in report and 'insufficient_contiguous_capacity_or_modules' in report,
                    'Shop shortage lacks request/actual/reason')
            require(a.evalParm('shopfront_count')==2,'Compression rewrote the request')
            coverage(value)
        a.setParms(dict(shopfront_control=1,shopfront_ratio=.6))
        require(front_shops(output())==1,'Ratio request lost mixed tiling')
        require('resolved_metric=3' in geometry(a,'BUILD_METADATA').attribValue('ground_shopfront_report'),
                'Ratio metric confused cells and modules')
        cases+=2

        raw=catalog((('DoorTwo',2,1,15),),walls=(1,),wall_mask=9)
        raw+='\n'+style_row(2,SOURCE_PREFIX+'SideWallThree.fbx',width=3,height=4,floors=1,facades=4)
        setup(raw,depth=10,number=3)
        for seed in range(24):
            a.parm('layout_seed').set(seed)
            value=output()
            require({p.intAttribValue('face_index') for p in doors(value)}=={0,1,2},
                    'Solver did not try the feasible side-face combination')
            coverage(value)
        cases+=1
        for shape in (0,1):
            for number in (1,2,3,4):
                setup(catalog((('DoorA',1,1,15),('DoorB',2,2,15))),width=16,number=number,shape=shape)
                value=output()
                got=doors(value)
                require(len(got)==number and len({p.intAttribValue('face_index') for p in got})==number,
                        'L segments or physical faces duplicated a door quota')
                coverage(value)
                cases+=1
        setup(catalog((('DoorA',1,1,15),)),number=3,rear=0)
        require({p.intAttribValue('face_index') for p in doors()}=={0,1,2},'Closed rear received a door')
        cases+=1

        for raw,number in ((catalog((('DoorOne',1,1,15),),walls=(2,)),1),
                           (catalog((('DoorOne',1,1,1),)),2)):
            setup(raw,number=number)
            target=a.node('StreetBuildingCore/ALLOCATE_FACADE_CAPACITY')
            try:target.cook(force=True)
            except Exception:pass
            require(bool(target.errors()),'Unsatisfiable precise request succeeded')
            require(a.evalParm('entrance_count_max')==number,'Failed solver changed the request')
            cases+=1

        setup(catalog((('DoorA',1,1,15),('DoorB',1,9,15),('DoorC',2,1,15)),walls=(1,2),shops=(1,2)),
              width=64,depth=64,number=4,shops=64)
        tick=time.perf_counter()
        value=output()
        elapsed=time.perf_counter()-tick
        coverage(value)
        report=geometry(a,'ALLOCATE_FACADE_CAPACITY').attribValue('ground_rule_report')
        checks=int(re.search(r'feasibility_checks=(\d+)',report).group(1))
        require(checks<=4*(1+32+31),'Same-width styles repeated the placement solver')
        return dict(status='PASS',cases=cases,seed_samples=samples,distributions=results,
                    six_cell_positions=sorted(positions),large_fixture_cook_seconds=round(elapsed,4),
                    feasibility_checks=checks,total_seconds=round(time.perf_counter()-started,3))
    finally:
        a.destroy()
