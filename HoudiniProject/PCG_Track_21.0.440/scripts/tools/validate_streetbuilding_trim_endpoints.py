"""Front trim endpoint regression, independent of migration code."""
from pathlib import Path


def validate_trim_endpoints(parent):
    import hou
    from validate_streetbuilding_contract import (
        STYLE_CATALOG, configure, geometry, require, signature, quaternion_matches)
    asset = parent.parent().createNode(parent.type().name(), 'VERIFY_TRIM_ENDPOINTS')
    cases = 0
    try:
        # Double-width windows at run boundaries must not consume trim endpoints.
        rows = STYLE_CATALOG.splitlines()
        rows = [r for r in rows if not (r.startswith('M|') and r.split('|')[2] == '4'
                                      and r.split('|')[5] == '1')]
        full = '\n'.join(rows)
        sparse = '\n'.join(r for r in rows if not (r.startswith('M|') and r.split('|')[2] == '12'))
        for schema in (0, 2):
            for shape, side in ((0, 0), (1, 0), (1, 1), (1, 2), (1, 3)):
                for missing, catalog in ((False, full), (True, sparse)):
                    configure(asset, catalog, floors=3, shape=shape, notch_side=side,
                              rhythm=1, attachments=0)
                    asset.parm('ground_rule_schema_version').set(schema)
                    asset.parm('ground_floor_use').set(2)
                    asset.parm('architectural_trim_enabled').set(1)
                    asset.parm('window_count_min').set(2)
                    # Unity-space endpoints, including the recessed front of L shapes.
                    endpoints = [(-6., 0.), (6., 0.)]
                    if shape and side == 2:
                        endpoints = [(-2., 0.), (6., 0.), (-6., -4.), (-2., -4.)]
                    if shape and side == 3:
                        endpoints = [(-6., 0.), (2., 0.), (2., -4.), (6., -4.)]
                    value = geometry(asset, 'MERGE_DIRECT_BUILDING_INSTANCES')
                    columns = [p for p in value.points() if p.stringAttribValue('module_role') == 'FacadeColumn']
                    actual = sorted(tuple(round(float(v), 4) for v in p.position()) for p in columns)
                    expected = sorted((-x, y, z) for x, z in endpoints for y in (0., 4., 7.))
                    require(actual == expected,
                            f'Trim endpoints missing/duplicated schema={schema}, shape={shape}, side={side}: {actual} != {expected}')
                    require(len({p.stringAttribValue('name') for p in columns}) == len(columns),
                            'Trim endpoints have colliding stable names')
                    require(all(p.intAttribValue('preview_missing') == int(missing) for p in columns),
                            'Missing column must become a preview slot; present column must remain an instance')
                    require(all(quaternion_matches(p.attribValue('orient'), 0) for p in columns),
                            'Front column orientation changed')
                    frozen = value.freeze()
                    frozen.deletePoints([p for p in frozen.points() if p.stringAttribValue('module_role')
                                         in ('FacadeColumn', 'Cornice', 'FloorBand')])
                    require(signature(value) == signature(geometry(asset, 'MERGE_DIRECT_BUILDING_INSTANCES')),
                            'Trim output is not deterministic')
                    preview = geometry(asset, 'OUT_BUILDING_PREVIEW')
                    preview_columns = [p for p in preview.prims() if p.stringAttribValue('module_role') == 'FacadeColumn']
                    require(len(preview_columns) == (len(expected) * 30 if missing else 0),
                            'Preview mesh does not cover every missing column endpoint')
                    real = geometry(asset)
                    real_columns = [p for p in real.points() if p.stringAttribValue('module_role') == 'FacadeColumn']
                    require(len(real_columns) == (0 if missing else len(expected)),
                            'Preview columns leaked into real instance output')
                    asset.parm('architectural_trim_enabled').set(0)
                    disabled = geometry(asset, 'MERGE_DIRECT_BUILDING_INSTANCES').freeze()
                    require(not any(p.stringAttribValue('module_role') in ('FacadeColumn', 'Cornice', 'FloorBand')
                                    for p in disabled.points()), 'Trim toggle left active trim slots')
                    require(signature(disabled) == signature(frozen), 'Trim toggle changed non-trim instances')
                    cases += 1
        return {'cases': cases, 'front_endpoints': 'PASS', 'span_independent': 'PASS',
                'preview_and_toggle': 'PASS', 'non_trim_isolation': 'PASS'}
    finally:
        asset.destroy()


if __name__ == '__main__':
    import hou, json, sys
    root = Path(__file__).resolve().parents[4]
    hda = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'Assets/PCG/HDA/City/StreetBuilding.hda'
    hou.hda.installFile(str(hda))
    asset = hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0', 'TRIM_CONTRACT')
    print(json.dumps(validate_trim_endpoints(asset)))
