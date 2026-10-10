"""Independent spatial oracle for AC footprints on final concave wall modules."""


def assert_notch_support(asset, host_name='SELECT_FACADE_MODULES'):
    from validate_streetbuilding_contract import geometry, require
    walls=geometry(asset,host_name).freeze()
    output=geometry(asset,'OUT_DETAIL_INSTANCES').freeze()
    cw=float(asset.evalParm('unity_style_catalog').splitlines()[0].split('|')[1])
    occupied=set(); count=0
    for p in output.points():
        if p.stringAttribValue('module_role')!='ACUnit' or not p.stringAttribValue('surface_role').startswith('notch_'):
            continue
        count+=1
        face=p.intAttribValue('face_index'); floor=p.intAttribValue('floor_index')
        surface=p.stringAttribValue('surface_role'); span=p.intAttribValue('module_span')
        require(surface in ('notch_inner','notch_rear') and face in (1,2,3) and floor>0,
                'Notch AC escaped an upper side/rear wall')
        matches=[h for h in walls.points() if h.intAttribValue('building_id')==p.intAttribValue('building_id')
                 and h.intAttribValue('face_index')==face and h.intAttribValue('floor_index')==floor
                 and h.stringAttribValue('surface_role')==surface]
        require(matches, 'Notch AC has no matching physical wall segment')
        # Derive the plane and tangent from authored final hosts, independently of AC keys.
        right=matches[0].attribValue('arrangement_right')
        tangent=(-right[0],0,right[2])
        pos=tuple(p.position())
        def interval(h):
            delta=tuple(h.position()[i]-pos[i] for i in range(3))
            u=sum(delta[i]*tangent[i] for i in range(3))
            if abs(delta[0]-u*tangent[0])>.001 or abs(delta[2]-u*tangent[2])>.001:
                return None
            return (u-h.intAttribValue('module_span')*cw*.5,u+h.intAttribValue('module_span')*cw*.5)
        solid=[]; holes=[]
        for h in matches:
            limits=interval(h)
            if limits is None: continue
            role=h.stringAttribValue('module_role')
            if role in ('MiddleBlank','SideWall','RearWall') and not h.intAttribValue('preview_missing') and h.stringAttribValue('unity_instance'):
                solid.append(limits)
            if role in ('MiddleWindow','GroundShop','GroundShopDoor','Entrance'): holes.append(limits)
        left=-span*cw*.5
        for c in range(span):
            lo,hi=left+c*cw,left+(c+1)*cw
            require(any(a<=lo+.001 and b>=hi-.001 for a,b in solid),
                    f'Notch AC has unsupported footprint: {surface}, floor={floor}, span={span}')
            require(not any(min(b,hi)-max(a,lo)>.001 for a,b in holes), 'Notch AC overlaps a window/door')
            center=tuple(round(pos[i]+tangent[i]*(lo+cw*.5),4) for i in (0,2))
            key=(p.intAttribValue('building_id'),face,floor,center)
            require(key not in occupied,'Notch AC footprints overlap')
            occupied.add(key)
        # Height follows the actual host floor, not an assumed material default.
        floor_y=matches[0].position()[1]
        require(abs(pos[1]-floor_y-.65)<.001,'Notch AC lost its host floor height')
    return count


def validate_ac_notches(parent):
    from validate_streetbuilding_contract import (configure,geometry,require,signature,
        STYLE_CATALOG,catalog_module_rows,style_row,DETAIL_PREFIX,ATTACHMENT_TOKENS,
        set_facade_override,set_attachment_overrides)
    a=parent.parent().createNode(parent.type().name(),'VERIFY_AC_NOTCHES')
    cases=0; checked=0
    def setup(side=0,span=1,windows=0,shape=1,seed=29):
        catalog='STYLE|2|4|3\n'+'\n'.join('|'.join(r) for r in catalog_module_rows(STYLE_CATALOG)
            if int(r[2])!=17)
        catalog+='\n'+style_row(17,DETAIL_PREFIX+'PF_AC_NotchFixture.prefab',width=span,height=.6,facades=12,floors=2)
        configure(a,catalog,shape=shape,notch_side=side,density=1,floors=3,seed=seed)
        a.parm('attachment_overrides').set(0)
        for token in ATTACHMENT_TOKENS: a.parm(token+'_density').set(1 if token=='wall_ac' else 0)
        a.parm('wall_ac_max_count').set(64)
        set_facade_override(a,floor_from=2,floor_to=12,mode=2,rhythm=1,window=(windows,windows),blank=(0,64))
        values={p.name()[:-1]:p.eval() for p in a.parms() if p.name().startswith('facade_override_') and p.name().endswith('1')}
        a.parm('facade_overrides').set(2)
        for i,target in ((1,2),(2,3)):
            for key,value in values.items(): a.parm(key+str(i)).set(value)
            a.parm('facade_override_target'+str(i)).set(target)
    try:
        for side in range(4):
            for span in (1,2,3):
                for windows in (0,2):
                    setup(side,span,windows)
                    count=assert_notch_support(a); checked+=count; cases+=1
                    output=geometry(a,'OUT_DETAIL_INSTANCES').freeze()
                    names=[p.stringAttribValue('instance_prefix') for p in output.points()]
                    require(len(names)==len(set(names)),'Inner/outer AC instance names collided')
                    if windows==0 and span<=2:
                        require(count>0,f'L side={side} omitted its usable concave walls')
                        surfaces={p.stringAttribValue('surface_role') for p in output.points() if p.stringAttribValue('module_role')=='ACUnit'}
                        require('notch_inner' in surfaces,'Inner side wall omitted')
                        if side<2: require('notch_rear' in surfaces,'Inset rear wall omitted')
                    if windows==0 and span==3:
                        require(count==0,'Three-cell AC crossed a two-cell notch run')
                    before=signature(output)
                    require(before==signature(geometry(a,'OUT_DETAIL_INSTANCES')),'Notch generation is nondeterministic')
                    require(all(p.stringAttribValue('surface_role')!='secondary_front' for p in output.points()
                        if p.stringAttribValue('module_role')=='ACUnit'),'AC appeared on secondary front')
        setup(shape=0)
        require(assert_notch_support(a)==0,'Rectangle generated notch AC'); cases+=1
        setup()
        lines=a.evalParm('unity_style_catalog').splitlines()
        a.parm('unity_style_catalog').set('\n'.join(r for r in lines if not r.startswith('M|') or int(r.split('|')[2]) not in (5,10,11)))
        require(assert_notch_support(a)==0,'Missing material walls generated notch AC'); cases+=1
        setup()
        shell=signature(geometry(a))
        for name in ('attachments_enabled','attachment_global_density','wall_ac_density','wall_ac_max_count'):
            p=a.parm(name); value=p.eval(); p.set(0)
            require(assert_notch_support(a)==0,'Notch AC ignored '+name)
            require(signature(geometry(a))==shell,'Attachment toggle changed shell layout')
            p.set(value); cases+=1
        setup()
        set_attachment_overrides(a,[(3,1,64,8,2,2)])
        require(assert_notch_support(a)>0,'Rear/floor override omitted notch rear')
        ac=[p for p in geometry(a,'OUT_DETAIL_INSTANCES').points() if p.stringAttribValue('module_role')=='ACUnit']
        require(all(p.intAttribValue('face_index')==3 and p.intAttribValue('floor_index')==1 for p in ac),'Notch AC ignored explicit facade/floor override'); cases+=1
        setup()
        a.parm('wall_ac_max_count').set(3)
        require(len([p for p in geometry(a,'OUT_DETAIL_INSTANCES').points() if p.stringAttribValue('module_role')=='ACUnit'])==3,
                'Outer and notch walls did not share maximum'); cases+=1
        # Every usable one-cell final wall must receive one AC at density=1/max=64.
        for side in range(4):
            setup(side=side,span=1,windows=0)
            hosts=geometry(a,'SELECT_FACADE_MODULES').freeze()
            expected=sum(p.intAttribValue('module_span') for p in hosts.points()
                if p.stringAttribValue('surface_role').startswith('notch_') and p.intAttribValue('floor_index')>0
                and p.stringAttribValue('module_role') in ('MiddleBlank','SideWall','RearWall')
                and p.stringAttribValue('unity_instance') and not p.intAttribValue('preview_missing'))
            require(assert_notch_support(a)==expected,f'Notch capacity not filled: side={side}, expected={expected}')
            cases+=1
        return dict(cases=cases,checked_instances=checked,four_corners=True,actual_wall_support=True,
                    no_openings=True,span_isolation=True,shared_budget=True,deterministic=True)
    finally:
        a.destroy()
