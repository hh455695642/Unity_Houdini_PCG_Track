"""Independent contracts for material-only styles and instance-owned quotas."""
from collections import Counter
import json


def validate_instance_rules(parent):
    from validate_streetbuilding_contract import configure, geometry, require, STYLE_CATALOG, signature, style_row, SOURCE_PREFIX
    a = parent.parent().createNode(parent.type().name(), 'VERIFY_INSTANCE_RULES')
    cases = 0
    def setup():
        configure(a, STYLE_CATALOG, floors=5, attachments=0, roof=0, width=16, depth=12, rear=2)
        a.setParms(dict(ground_rule_schema_version=2, ground_floor_use=2,
            entrance_count_max=1, facade_layout_mode=0, window_count_min=1,
            style_rule_source=1, style_override_upper=0, facade_overrides=0,
            shopfront_face_0=1,shopfront_face_1=1,shopfront_face_2=1,shopfront_face_3=1,
            shopfront_quantity_mode=0,shopfront_count=2,ground_quantity_mode=0))
        r=dict(layoutMode=0,windowMin=2,windowMax=2,groundUse=2,commercialDoorMin=1,
            commercialDoorMax=1,shopfrontRatio=.65,trimEnabled=False,roofEnabled=False)
        a.parm('unity_style_rules').set(json.dumps(dict(version=2,ground=r,upper=r,roof=r)))
    def count(role):
        return Counter((p.intAttribValue('floor_index'),p.intAttribValue('face_index'))
            for p in geometry(a,'SELECT_FACADE_MODULES').points()
            if p.stringAttribValue('module_role')==role and not p.intAttribValue('preview_missing'))
    try:
        setup()
        require(set(count('MiddleWindow').values())=={1},'Style must not override instance window count 1')
        baseline=signature(geometry(a,'SELECT_FACADE_MODULES'))
        a.parm('unity_style_rules').set('invalid obsolete JSON')
        require(signature(geometry(a,'SELECT_FACADE_MODULES'))==baseline,'Retired JSON still controls generation')
        cases+=2
        for spans in ((1,),(2,),(1,2)):
            for number in (0,1,2):
                setup()
                catalog='\n'.join(r for r in STYLE_CATALOG.splitlines() if not(r.startswith('M|') and r.split('|')[2]=='0'))
                for span in spans: catalog+='\n'+style_row(0,SOURCE_PREFIX+f'ShopContract_{span}.fbx',width=span,height=4,floors=1)
                a.setParms(dict(unity_style_catalog=catalog,shopfront_control=0,shopfront_quantity_mode=0,
                    shopfront_count=number,shopfront_count_max=64,shopfront_facades=15))
                got=count('GroundShop')
                require(all(got[(0,f)]==number for f in range(4)),f'Shop module count differs: {spans,number,got}')
                require(sum(count('Entrance').values())+sum(count('GroundShopDoor').values())==1,'Shop count changed doors')
                geometry(a,'VALIDATE_DIRECT_BUILDING_INSTANCES')
                cases+=1
        setup();a.setParms(dict(shopfront_control=0,shopfront_count=2,shopfront_face_1=0,shopfront_face_2=0,shopfront_face_3=0))
        require(count('GroundShop')=={(0,0):2},'Shop mask ignored');cases+=1
        for ratio in (0,.5,1):
            setup();a.setParms(dict(shopfront_control=1,shopfront_ratio=ratio))
            g=geometry(a,'BUILD_METADATA'); report=g.attribValue('ground_shopfront_report')
            require('mode=ratio' in report,'Missing ratio diagnostic')
            if ratio==0:require(not count('GroundShop'),'Zero ratio emitted shops')
            cases+=1
        # Fixed quantity ignores both hidden random bounds, even after mode switches.
        setup();a.setParms(dict(shopfront_control=0,shopfront_count=1,shopfront_count_min=9,shopfront_count_max=12))
        require(set(count('GroundShop').values())=={1},'Hidden random limits affect fixed count');cases+=1
        for shape in (0,1):
            for rhythm in (0,1,3,4):
                setup();a.setParms(dict(massing_shape=shape,shopfront_control=0,shopfront_count=1,ground_rhythm=rhythm))
                require(count('GroundShop')=={(0,f):1 for f in range(4)},'Arrangement or L segments duplicate quota')
                geometry(a,'VALIDATE_DIRECT_BUILDING_INSTANCES');cases+=1
        for seed in range(8):
            setup();a.setParms(dict(shopfront_control=0,shopfront_quantity_mode=1,shopfront_count=64,
                shopfront_count_min=1,shopfront_count_max=3,layout_seed=seed))
            result=count('GroundShop')
            require(all(1<=result[(0,f)]<=3 for f in range(4)),'Random quota escaped interval')
            require(result==count('GroundShop'),'Random count is not deterministic');cases+=1
        missing='\n'.join(r for r in STYLE_CATALOG.splitlines() if not(r.startswith('M|') and r.split('|')[2]=='0'))
        for control in (0,1):
            setup();a.setParms(dict(unity_style_catalog=missing,shopfront_control=control,shopfront_count=0,shopfront_ratio=0))
            require(not count('GroundShop'),'Zero requires shop module')
            geometry(a,'VALIDATE_DIRECT_BUILDING_INSTANCES');cases+=1
        setup();a.setParms(dict(shopfront_control=0,shopfront_count=64,rear_facade_mode=0))
        report=geometry(a,'BUILD_METADATA').attribValue('ground_shopfront_report')
        require('insufficient_contiguous_capacity_or_modules' in report,'Capacity loss is silent')
        require(not any(f==3 for _,f in count('GroundShop')),'Disabled rear emits shops');cases+=1
        # Explicit local quotas remain above base instance counts, with a readable source.
        from validate_streetbuilding_contract import set_facade_override
        setup();a.setParms(dict(shopfront_control=0,shopfront_count=1))
        set_facade_override(a,floor_from=1,floor_to=1,mode=2,rhythm=3,shopfront=(3,3))
        require(count('GroundShop')[(0,0)]==3,'Explicit local quota ignored')
        require('source=instance_override' in geometry(a,'BUILD_METADATA').attribValue('ground_shopfront_report'),'Override source missing');cases+=1
        return dict(status='PASS',cases=cases)
    finally:a.destroy()
