"""Independent geometry contracts for grid notches and front-facing recesses."""
import math
from streetbuilding_notch_interface import migrate


def validate_notches(parent):
    from validate_streetbuilding_contract import configure, STYLE_CATALOG, geometry as geo, require
    asset = parent.parent().createNode(parent.type().name(), 'VERIFY_NOTCH_CORNERS')
    cases = []
    try:
        for cw in (2.0, 3.0):
            catalog = STYLE_CATALOG.replace('STYLE|2|', 'STYLE|' + str(cw) + '|', 1)
            for side in range(4):
                configure(asset, catalog, width=6*cw, depth=5*cw, shape=1, notch_side=side, density=1)
                asset.setParms({'l_notch_units': 1, 'l_notch_width_cells': 2, 'l_notch_depth_cells': 2})
                g = geo(asset, 'OUT_BUILDING_LOD0')
                points = g.points()
                roof = [p for p in points if p.stringAttribValue('module_role') == 'RoofSurface']
                require(len(roof) == 26, 'Four-corner roof area is incorrect')
                for p in roof:
                    x, y, z = p.position(); x = -x
                    in_x = x < -cw if side % 2 == 0 else x > cw
                    in_z = z < -3*cw if side < 2 else z > -2*cw
                    require(not(in_x and in_z), 'Roof tile entered the notch')
                entrances = [p for p in points if p.intAttribValue('is_building_entrance')]
                require(len(entrances) == 1, f'Notch must retain exactly one primary entrance: cw={cw} side={side} count={len(entrances)}')
                require(abs(entrances[0].position()[2]) < .001, 'Entrance left the primary front')
                corners = [p for p in points if p.stringAttribValue('module_role') == 'ParapetCorner']
                concave = [p for p in points if p.stringAttribValue('module_role') == 'ParapetConcaveCorner']
                require(len(corners)==5 and len(concave)==1, 'L corner topology changed')
                cells = geo(asset, 'BUILD_FACADE_CELLS').points()
                if side >= 2:
                    recess = [p for p in cells if p.intAttribValue('face_index')==0 and p.stringAttribValue('surface_role')=='secondary_front']
                    require(len(recess)==8, 'Front recess must use secondary-front rules on every floor')
                    require(all(abs(p.position()[2]+2*cw)<.001 for p in recess), 'Recess support plane mismatch')
                details = geo(asset, 'OUT_DETAIL_INSTANCES').points()
                for p in details:
                    if side>=2 and p.stringAttribValue('module_role') in ('Awning','Sign'):
                        x,y,z=p.position();x=-x
                        if p.intAttribValue('face_index')==0:
                            is_recess=p.stringAttribValue('surface_role')=='secondary_front'
                            require(abs(z-(-2*cw if is_recess else 0)-.22)<.001, 'Front attachment is floating')
                            if not is_recess:
                                require(x>=-cw-.001 if side==2 else x<=cw+.001, 'Attachment entered removed frontage')
                cases.append({'cell_width':cw,'corner':side,'roof_tiles':len(roof),'entrances':len(entrances),'details':len(details)})
        # Strict minimum and oversized inputs: effective values preserve one-cell wings.
        configure(asset, STYLE_CATALOG, shape=1, notch_side=2)
        asset.setParms({'l_notch_units':1,'l_notch_width_cells':99,'l_notch_depth_cells':99})
        rules=geo(asset,'PARSE_GENERATION_RULES')
        require(rules.attribValue('effective_notch_width')==10 and rules.attribValue('effective_notch_depth')==8,'Oversized grid notch is not bounded')
        geo(asset,'OUT_BUILDING_LOD0')
        asset.setParms({'l_notch_width_cells':1,'l_notch_depth_cells':1})
        geo(asset,'OUT_BUILDING_LOD0')
        asset.parm('massing_shape').set(0)
        require(len([p for p in geo(asset,'OUT_BUILDING_LOD0').points() if p.stringAttribValue('module_role')=='RoofSurface'])==30,'Rectangle switching retained a notch')
        # Existing exact metre values migrate without changing size; inexact stay intact.
        configure(asset, STYLE_CATALOG, shape=1, notch_width=6, notch_depth=4)
        require(migrate(asset)=='grid','Exact old values failed migration')
        require(asset.evalParm('l_notch_width_cells')==3 and asset.evalParm('l_notch_depth_cells')==2,'6m x 4m did not become 3 x 2 cells')
        configure(asset, STYLE_CATALOG, shape=0, notch_width=5, notch_depth=4)
        require(migrate(asset)=='legacy-metres-retained' and asset.evalParm('l_notch_width')==5,'Non-grid legacy values were changed')
        return {'cases':cases,'bounds':'PASS','migration':'PASS'}
    finally:
        asset.destroy()

