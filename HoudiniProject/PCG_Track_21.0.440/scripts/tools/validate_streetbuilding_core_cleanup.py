"""StreetBuilding flat-stage and retired-builder contracts; independent of patches.

The --record/--compare interface fingerprints every output for a refactor audit.
Run with hython: no changes are saved to the source HDA or HIP.
"""
import argparse
import hashlib
import json
from pathlib import Path

STAGES = {
    '00_INPUT_VALIDATE': ['EMPTY_GEOMETRY', 'IN_SITE_PARCELS', 'IN_FRONTAGE_GUIDES',
        'IN_MODULE_LIBRARY', 'INTERNAL_TEST_PARCEL', 'SELECT_SITE_SOURCE', 'CANONICALIZE_PARCELS'],
    '10_RULES_AND_CATALOG': ['RESOLVE_FRONTAGES', 'PARSE_GENERATION_RULES', 'PARSE_UNITY_INSTANCE_CATALOG'],
    '20_FACADE_CAPACITY': ['BUILD_FACADE_CELLS', 'ALLOCATE_FACADE_CAPACITY'],
    '30_FACADE_SELECTION': ['SELECT_FACADE_VARIANTS', 'SELECT_FACADE_MODULES'],
    '40_BUILDING_INSTANCES': ['DIRECT_UNITY_INSTANCE_FACADE', 'BUILD_DIRECT_SIDE_REAR_INSTANCES',
        'BUILD_DIRECT_ROOF_INSTANCES', 'BUILD_DIRECT_ROOF_EDGE_INSTANCES'],
    '50_ATTACHMENT_INSTANCES': ['SELECT_ATTACHMENT_MODULES', 'DETAIL_INSTANCE_POINTS'],
    '60_PROXY_MODEL': ['RESOLVE_MASSING', 'RESOLVE_FACADE_GRAMMAR', 'VALIDATE_MODULE_LIBRARY',
        'BUILD_LOD0', 'NORMAL_LOD0'],
    '70_UNITY_CONTRACT': ['MERGE_DIRECT_BUILDING_INSTANCES', 'FILTER_REAL_INSTANCES',
        'VALIDATE_DIRECT_BUILDING_INSTANCES', 'VALIDATE_DIRECT_DETAIL_INSTANCES',
        'PREVIEW_MISSING_MODULES', 'BUILD_METADATA', 'METADATA_ATTACHMENT_INPUTS', 'LOD0_MODULE_SOURCE_SWITCH', 'DETAIL_MODULE_SOURCE_SWITCH'],
    '80_OUTPUT_VALIDATE': ['OUT_BUILDING_LOD0', 'OUT_BUILDING_LOD1', 'OUT_BUILDING_LOD2',
        'OUT_DETAIL_INSTANCES', 'OUT_BUILDING_COLLISION', 'OUT_BUILDING_METADATA', 'OUT_BUILDING_PREVIEW'],
}
RETIRED = ('BUILD_LOD1', 'NORMAL_LOD1', 'BUILD_LOD2', 'NORMAL_LOD2',
           'BUILD_COLLISION', 'GRAYBOX_MODULE_LIBRARY')
EMPTY_OUTPUTS = ('OUT_BUILDING_LOD1', 'OUT_BUILDING_LOD2', 'OUT_BUILDING_COLLISION')
OUTPUTS = tuple(STAGES['80_OUTPUT_VALIDATE'])


def validate_core_cleanup(asset):
    import hou
    from validate_streetbuilding_contract import require, configure, geometry, STYLE_CATALOG, signature
    c = asset.node('StreetBuildingCore')
    require(set(n.name() for n in c.children()) == {n for names in STAGES.values() for n in names},
            'Core node inventory differs from the 40-node contract')
    boxes = {b.name(): b for b in c.networkBoxes()}
    require(set(boxes) == set(STAGES), 'Missing/obsolete stage boxes')
    for name, members in STAGES.items():
        b = boxes[name]
        actual = {i.name() for i in b.items() if isinstance(i, hou.Node)}
        require(actual == set(members), 'Stage membership mismatch: ' + name)
        require(any('\u4e00' <= ch <= '\u9fff' for ch in b.comment()), 'Missing Chinese stage title: ' + name)
        notes = [i for i in b.items() if isinstance(i, hou.StickyNote)]
        require(len(notes) == 1 and all(word in notes[0].text() for word in ('职责', '输入', '输出', '修改', '扩展')),
                'Missing maintenance note: ' + name)
        x, y = b.position(); w, h = b.size()
        for n in (c.node(item) for item in members):
            nx, ny = n.position()
            require(n.parentNetworkBox() == b and x <= nx <= x+w and y <= ny <= y+h,
                    'Node lies outside its stage: ' + n.name())
    bs = list(boxes.values())
    for i, a in enumerate(bs):
        ax, ay = a.position(); aw, ah = a.size()
        for b in bs[i+1:]:
            bx, by = b.position(); bw, bh = b.size()
            require(not (ax < bx+bw and bx < ax+aw and ay < by+bh and by < ay+ah),
                    'Overlapping stage boxes: ' + a.name() + '/' + b.name())
    for index, name in enumerate(OUTPUTS):
        require(c.node(name).evalParm('outputidx') == index, 'Output index changed: ' + name)
    for name in RETIRED:
        require(c.node(name) is None, 'Retired builder remains: ' + name)
    for name in EMPTY_OUTPUTS:
        require(c.node(name).input(0) == c.node('EMPTY_GEOMETRY'), 'Retired output is not empty: ' + name)
    require(asset.parmTemplateGroup().find('lod_outputs_enabled').isHidden(), 'Retired LOD toggle is visible')
    require(asset.type().definition().parmTemplateGroup().find('lod_outputs_enabled').isHidden(),
            'Definition did not preserve hidden LOD compatibility field')
    for n in c.children():
        if n.parm('snippet'):
            require('lod_outputs_enabled' not in n.evalParm('snippet'), 'Retired toggle still controls generation')
    a = asset.parent().createNode(asset.type().name(), 'VERIFY_CORE_HIDDEN_LOD')
    try:
        for source in (0, 1):
            configure(a, STYLE_CATALOG, module_source=source)
            before = {name: signature(geometry(a, name)) for name in OUTPUTS}
            a.parm('lod_outputs_enabled').set(1)
            require({name: signature(geometry(a, name)) for name in OUTPUTS} == before,
                    'Compatibility LOD value changes geometry')
            for name in EMPTY_OUTPUTS:
                g = geometry(a, name)
                require(not g.points() and not g.prims(), 'Retired output emits geometry')
    finally:
        a.destroy()
    return dict(status='PASS', nodes=40, stages=9, stable_outputs=7, retired_builders=6,
                lod_value_has_no_generation_semantics=True)


def geometry_fingerprint(g):
    """Topology and all point/vertex/primitive/detail values, not just counts."""
    def canonical(value):
        if isinstance(value, float):
            return round(value, 6) + 0.0
        if isinstance(value, (tuple, list)):
            return [canonical(v) for v in value]
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        return value
    def attrs(items, attributes):
        return {a.name(): [canonical(i.attribValue(a)) for i in items]
                for a in sorted(attributes, key=lambda a: a.name())}
    points, prims = g.points(), g.prims()
    vertices = [v for p in prims for v in p.vertices()]
    payload = dict(points=attrs(points, g.pointAttribs()), primitives=attrs(prims, g.primAttribs()),
                   vertices=attrs(vertices, g.vertexAttribs()),
                   detail={a.name(): canonical(g.attribValue(a)) for a in g.globalAttribs()},
                   topology=[(str(p.type()), [v.point().number() for v in p.vertices()]) for p in prims],
                   point_groups={x.name(): [p.number() for p in x.points()] for x in g.pointGroups()},
                   prim_groups={x.name(): [p.number() for p in x.prims()] for x in g.primGroups()})
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(sha256=digest, points=len(points), primitives=len(prims))


def output_matrix():
    import hou
    from validate_streetbuilding_contract import configure, geometry, STYLE_CATALOG
    scenarios = []
    for source in (0, 1):
        for shape, notch in ((0, 0), (1, 0), (1, 1), (1, 2), (1, 3)):
            scenarios.append((f'source{source}-shape{shape}-notch{notch}', STYLE_CATALOG,
                              dict(module_source=source, shape=shape, notch_side=notch), {}))
    for name, catalog, extra in (
        ('empty-hidden', 'STYLE|2|4|3', {'preview_missing_modules': 0}),
        ('empty-preview', 'STYLE|2|4|3', {'preview_missing_modules': 1}),
        ('sparse-preview', '\n'.join(STYLE_CATALOG.splitlines()[:2]), {'preview_missing_modules': 1}),
        ('fixed-zero', STYLE_CATALOG, {'facade_layout_mode': 0, 'window_count_min': 0}),
        ('fixed-two', STYLE_CATALOG, {'facade_layout_mode': 0, 'window_count_min': 2}),
        ('random-range', STYLE_CATALOG, {'facade_layout_mode': 1, 'window_count_min': 1, 'window_count_max': 3}),
        ('shop-ratio', STYLE_CATALOG, {'shopfront_control': 1, 'shopfront_ratio': .5}),
        ('attachments-off', STYLE_CATALOG, {'attachments_enabled': 0}),
        ('roof-off', STYLE_CATALOG, {'roof_enabled': 0, 'parapet_enabled': 0}),
        ('alternate-seed', STYLE_CATALOG, {'variation_seed': 73, 'layout_seed': 73}),
        ('arrangement-paired', STYLE_CATALOG, {'facade_rhythm': 4, 'ground_rhythm': 4}),
        ('retired-style', STYLE_CATALOG, {'style_rule_source': 1, 'unity_style_rules': 'obsolete ignored JSON'}),
    ):
        scenarios.append((name, catalog, {}, dict(ground_rule_schema_version=2, ground_floor_use=2,
                         entrance_count_max=1, facade_overrides=0, **extra)))
    result = {}
    for name, catalog, config, extra in scenarios:
        a = hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0', 'VERIFY_CORE_EQUIVALENCE')
        try:
            configure(a, catalog, **config)
            a.setParms(extra)
            if name.startswith(('empty-', 'sparse-')):
                # Exercise the existing partial-catalog contract. Explicit V2
                # Commercial correctly rejects missing required commercial roles.
                a.parm('ground_rule_schema_version').set(0)
            result[name] = {out: geometry_fingerprint(geometry(a, out)) for out in OUTPUTS}
        except Exception as error:
            raise AssertionError('Equivalence fixture failed: ' + name) from error
        finally:
            a.destroy()
    return result


def main():
    import hou
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hda', type=Path, required=True)
    p.add_argument('--record', type=Path)
    p.add_argument('--compare', type=Path)
    args = p.parse_args()
    hou.hda.installFile(str(args.hda.resolve()), change_oplibraries_file=False, force_use_assets=True)
    current = output_matrix()
    if args.record:
        args.record.write_text(json.dumps(current, indent=2), encoding='utf-8')
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding='utf-8'))
        differences = [name for name in baseline.keys() | current.keys() if baseline.get(name) != current.get(name)]
        if differences:
            raise AssertionError('Output changes: ' + ', '.join(differences))
    print(json.dumps(dict(status='PASS', cases=len(current), outputs_per_case=len(OUTPUTS),
                         action='compare' if args.compare else 'record')))


if __name__ == '__main__':
    main()
