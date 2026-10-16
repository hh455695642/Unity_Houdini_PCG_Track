"""Panel contracts against a fresh locked instance, independent of the patch."""
from validate_streetbuilding_contract import configure, geometry, require, STYLE_CATALOG


def validate_panel(asset):
    templates = asset.parmTemplateGroup()
    for name in ('facade_override_shopfront_max#', 'facade_override_window_max#'):
        template = templates.find(name)
        require(template is not None and 'random_range' in str(template.conditionals()), 'Missing multiparm range condition: ' + name)
    require('parapet_enabled' in str(templates.find('parapet_height').conditionals()), 'Parapet height does not fold with its feature')
    require('／' not in templates.find('entrance_count_max').label() and '／' not in templates.find('window_count_min').label(), 'Ambiguous slash labels remain')
    cases = []
    for shape, side in [(0, 0)] + [(1, side) for side in range(4)]:
        configure(asset, STYLE_CATALOG, shape=shape, notch_side=side)
        asset.parm('ground_rule_schema_version').set(2)
        asset.parm('rear_facade_mode').set(2)
        cells = geometry(asset, 'BUILD_FACADE_CELLS')
        metadata = geometry(asset, 'OUT_BUILDING_METADATA')
        report = metadata.stringAttribValue('panel_facade_segments')
        require(report.startswith('v1\n'), 'Missing versioned facade mapping')
        rows = [r.split('|') for r in report.splitlines()[1:] if r]
        actual = [p for p in cells.points() if p.intAttribValue('floor_index') == 0 and p.intAttribValue('run_local_cell') == 0]
        require(len(rows) == len(actual), 'Facade report omitted or duplicated wall runs')
        cw = asset.node('StreetBuildingCore/PARSE_UNITY_INSTANCE_CATALOG').geometry().attribValue('style_cell_width')
        for row, point in zip(rows, actual):
            require(len(row) == 8, 'Malformed facade row')
            require(int(row[0]) == point.intAttribValue('face_index'), 'Physical face identity changed')
            require(int(row[1]) == point.intAttribValue('facade_target'), 'Coverage target identity changed')
            require(row[2] == point.stringAttribValue('surface_role'), 'Wall role changed')
            a = point.attribValue('placement_origin'); direction = point.attribValue('placement_right')
            count = point.intAttribValue('run_cell_count')
            b = tuple(a[i] + direction[i] * count * cw for i in range(3))
            require(all(abs(float(row[j]) - v) < .001 for j, v in zip((3, 4, 5, 6), (a[0], a[2], b[0], b[2]))), 'Wall mapping endpoint differs from Cook geometry')
            require(int(row[7]) == count, 'Wall run cell count changed')
        require(any(r[2] == 'secondary_front' for r in rows) == (shape == 1 and side >= 2), 'False secondary frontage in schematic')
        if shape == 1:
            require(any(sum(other[0] == row[0] for other in rows) > 1 for row in rows), 'Missing L shape shared physical quota')
        asset.parm('rear_facade_mode').set(0)
        closed = geometry(asset, 'OUT_BUILDING_METADATA').stringAttribValue('panel_facade_segments')
        require(not any(int(r.split('|')[1]) == 3 for r in closed.splitlines()[1:] if r), 'Closed rear facade shown as active wall')
        cases.append({'shape': shape, 'notch_side': side, 'wall_runs': len(rows)})
    configure(asset, STYLE_CATALOG)
    asset.parm('ground_rule_schema_version').set(2)
    asset.parm('facade_overrides').set(2)
    for row in (1, 2):
        asset.parm('facade_override_target' + str(row)).set(0)
        asset.parm('facade_override_floor_start' + str(row)).set(2)
        asset.parm('facade_override_floor_end' + str(row)).set(3)
        asset.parm('facade_override_layout_mode' + str(row)).set(2)
        asset.parm('facade_override_window_min' + str(row)).set(2)
        asset.parm('facade_override_window_max' + str(row)).set(64)
    before = geometry(asset, 'OUT_BUILDING_LOD0')
    sources = geometry(asset, 'OUT_BUILDING_METADATA').stringAttribValue('upper_window_report')
    require('source=instance_override:2' in sources, 'Actual winning override row is not reported: ' + sources)
    asset.updateParmStates()
    require(asset.parm('facade_override_window_max1').isHidden() and asset.parm('facade_override_window_max2').isHidden(), 'Fixed rows expose inactive random maxima')
    require(asset.parm('facade_override_shopfront_min1').isHidden(), 'Upper-only row exposes first-floor shopfront count')
    asset.parm('facade_override_layout_mode2').set(1)
    asset.updateParmStates()
    require(not asset.parm('facade_override_window_max2').isHidden() and asset.parm('facade_override_window_max1').isHidden(), 'Multiparm conditions are not isolated per row')
    asset.parm('facade_override_layout_mode2').set(2)
    signature = [(p.attribValue('name'), tuple(p.position())) for p in before.points()]
    for row in (1, 2): asset.parm('facade_override_window_max' + str(row)).set(0)
    after = geometry(asset, 'OUT_BUILDING_LOD0')
    require(signature == [(p.attribValue('name'), tuple(p.position())) for p in after.points()], 'Hidden random maxima affect fixed coverage')
    asset.parm('facade_overrides').set(0)
    return dict(status='PASS', topology_cases=cases, mode_isolation='PASS')
