"""Independent active-field contracts; always count real locked HDA outputs."""
import json
from validate_streetbuilding_contract import configure, geometry, require, STYLE_CATALOG


def validate_active_fields(parent):
    a=parent.parent().createNode(parent.type().name(),'VERIFY_PANEL_ACTIVE_FIELDS')
    cases=0
    def setup(start=1,end=3,use=2,mode=0,rhythm=0):
        configure(a,STYLE_CATALOG)
        a.setParms(dict(ground_rule_schema_version=2,ground_floor_use=use,ground_quantity_mode=0,
            entrance_count_max=1,facade_layout_mode=0,window_count_min=3,shopfront_control=0,
            shopfront_quantity_mode=0,shopfront_count=3,facade_overrides=1))
        a.setParms(dict(facade_override_target1=0,facade_override_floor_start1=start,
            facade_override_floor_end1=end,facade_override_layout_mode1=mode,facade_override_rhythm1=rhythm))
        for p in a.parms():
            if p.name().startswith('facade_override_') and ('_min' in p.name() or '_max' in p.name()):p.set(0)
    def check(expected,source='instance'):
        nonlocal cases
        g=geometry(a,'OUT_BUILDING_LOD0');meta=geometry(a,'OUT_BUILDING_METADATA')
        for floor,count in expected.items():
            role='GroundShop' if floor==1 else 'MiddleWindow'
            actual=sum(p.stringAttribValue('module_role')==role and p.intAttribValue('floor_index')==floor-1
                and p.intAttribValue('face_index')==0 for p in g.points())
            require(actual==count,f'Active fields F{floor}: expected {count}, got {actual}')
            report=meta.stringAttribValue('ground_shopfront_report' if floor==1 else 'upper_window_report')
            line=next((r for r in report.splitlines() if r.startswith('Face0 ' if floor==1 else f'F{floor} Face0 ')),'')
            require('source='+source+' ' in line,f'Wrong effective source: {line}')
        require(not a.errors() and not a.warnings(),'Unexpected Cook diagnostics')
        cases+=1
    try:
        for name in ('facade_override_shopfront_max1','facade_override_window_max1',
                     'facade_override_entrance_max1','facade_override_blank_min1'):
            setup()
            for value in (0,64):
                a.parm(name).set(value);a.updateParmStates()
                if name in ('facade_override_shopfront_max1','facade_override_window_max1'):
                    require(a.parm(name).isHidden(),'Probe must use an inactive hidden field: '+name)
                check({1:3,2:3,3:3})
                require(a.parm(name).evalAsInt()==value,'Hidden input was overwritten')
        for start,end,hidden in ((2,3,'shopfront_min'),(1,1,'window_min')):
            setup(start,end)
            a.parm('facade_override_'+hidden+'1').set(64)
            check({1:3,2:3,3:3})
        setup(use=1)
        a.parm('facade_override_shopfront_min1').set(64)
        check({2:3,3:3})
        for use in (1,2):
            setup(use=0)
            for seed in range(1,100):
                a.parm('variation_seed').set(seed)
                if geometry(a,'OUT_BUILDING_METADATA').intAttribValue('effective_ground_use')==use:break
            else:raise AssertionError('Random ground use fixture did not reach requested use')
            a.parm('facade_override_shopfront_max1').set(64)
            check({2:3,3:3})
        # Stored inactive values survive switching and become effective again in random mode.
        setup(mode=1)
        a.setParms(dict(facade_override_shopfront_min1=1,facade_override_shopfront_max1=1,
            facade_override_window_min1=1,facade_override_window_max1=1))
        check({1:1,2:1,3:1},'instance_override:1')
        a.parm('facade_override_layout_mode1').set(0)
        check({1:1,2:1,3:1},'instance_override:1')
        a.setParms(dict(facade_override_shopfront_min1=0,facade_override_window_min1=0))
        check({1:3,2:3,3:3})
        a.parm('facade_override_layout_mode1').set(2)
        check({1:0,2:0,3:0},'instance_override:1')
        a.parm('facade_override_layout_mode1').set(0)
        a.parm('facade_override_rhythm1').set(1)
        check({1:0,2:0,3:0},'instance_override:1')
        # Later inactive rows cannot shadow an earlier explicit override.
        setup(mode=2);a.setParms(dict(facade_override_shopfront_min1=2,facade_override_window_min1=2,facade_overrides=2))
        a.setParms(dict(facade_override_target2=0,facade_override_floor_start2=1,facade_override_floor_end2=3,
            facade_override_layout_mode2=0,facade_override_rhythm2=0,facade_override_shopfront_max2=64,
            facade_override_window_max2=64))
        check({1:2,2:2,3:2},'instance_override:1')
        # Same O payload parser applies to external parcel overrides.
        from validate_streetbuilding_contract import make_external_input
        parcel=make_external_input('VERIFY_ACTIVE_PARCEL',[(-6,0,0),(6,0,0),(6,0,-10),(-6,0,-10)],closed=True,
            payload='O|0|1|3|0|0|0|0|0|0|0|64|0|64|0|0')
        a.setInput(0,parcel);a.parm('site_source_auto').set(1)
        check({1:2,2:2,3:2},'instance_override:1')
        a.setInput(0,None);parcel.destroy()
        require(geometry(a,'OUT_BUILDING_METADATA').stringAttribValue('panel_rule_revision')=='active_fields_v2','Missing active-field revision')
        return dict(status='PASS',cases=cases,actual_output_counts=True)
    finally:a.destroy()
