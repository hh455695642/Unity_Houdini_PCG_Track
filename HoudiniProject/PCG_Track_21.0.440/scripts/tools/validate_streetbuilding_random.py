"""Independent V2 contracts against actual HDA outputs; no patch dependency."""
import time
from collections import Counter


def validate_random(parent):
    from validate_streetbuilding_contract import configure, geometry, require, STYLE_CATALOG, style_row, SOURCE_PREFIX, make_external_input
    a = parent.parent().createNode(parent.type().name(), 'VERIFY_RANDOM_V2')
    start = time.perf_counter()
    cases = 0
    external = None
    probe_container = None

    def setup(**overrides):
        configure(a, STYLE_CATALOG, width=16, depth=16, floors=3, attachments=1, roof=1, rear=2)
        values = dict(random_algorithm=2, random_instance_id='contract-fixture', random_seed=71, random_feasible=0,
                      random_seq_massing=0, random_seq_ground=0, random_seq_upper=0, random_seq_attachments=0,
                      ground_rule_schema_version=2, unified_ground_walls=1, ground_floor_use=2,
                      entrance_count_min=1, entrance_count_max=1, ground_quantity_mode=0,
                      shopfront_control=0, shopfront_quantity_mode=0, shopfront_count=2,
                      facade_layout_mode=1, window_count_min=1, window_count_max=4, layout_seed=137,
                      variation_seed=29, facade_overrides=0, attachment_overrides=0)
        values.update(overrides); a.setParms(values)

    def signature():
        g = geometry(a, 'SELECT_FACADE_MODULES')
        return tuple(sorted((p.intAttribValue('floor_index'), p.intAttribValue('face_index'),
                             p.intAttribValue('cell_index'), p.intAttribValue('module_span'),
                             p.stringAttribValue('module_role'), p.stringAttribValue('unity_instance'),
                             tuple(round(v, 5) for v in p.position())) for p in g.points()))
    try:
        setup()
        initial = signature()
        require(initial == signature(), 'V2 identical context changed real facade output')
        for seq in (1, 19, 777):
            a.setParms(dict(generation_sequence=seq, random_seq_attachments=seq))
            require(signature() == initial, 'Attachment reroll/global audit sequence changed facades')
            cases += 1
        outcomes = set()
        for seq in range(24):
            a.parm('random_seq_upper').set(seq); outcomes.add(signature())
        require(len(outcomes) > 1, 'Upper group does not change actual facade layouts')
        a.setParms(dict(random_seq_upper=0, random_instance_id='contract-other'))
        other = signature()
        a.parm('random_instance_id').set('contract-fixture')
        require(signature() == initial, 'Identity restoration did not reproduce facade output')
        require(other != initial, 'Independent fixture identities share the same whole output')
        cases += 3
        raw = '\n'.join(row for row in STYLE_CATALOG.splitlines()
                        if not (row.startswith('M|') and int(row.split('|')[2]) in (4, 5, 10, 11)))
        raw += '\n' + '\n'.join(style_row(role, SOURCE_PREFIX+'RandomSpan'+str(role)+'.fbx', width=1 if role==4 else 2)
                                 for role in (4, 5, 10, 11))
        setup(random_feasible=1)
        a.parm('unity_style_catalog').set(raw)
        observed = set()
        for seq in range(24):
            a.parm('random_seq_upper').set(seq)
            rows = geometry(a, 'SELECT_FACADE_MODULES').points()
            counts = Counter((p.intAttribValue('floor_index'), p.intAttribValue('face_index')) for p in rows
                             if p.intAttribValue('floor_index') > 0 and p.stringAttribValue('module_role') == 'MiddleWindow')
            require(all(1 <= n <= 4 for n in counts.values()), 'Feasible sampling escaped request range')
            observed.update(counts.values()); cases += 1
        require(observed, 'Feasible test produced no actual windows')
        require(observed == {2,4}, 'Noncontiguous feasible set must contain exactly 2 and 4 windows')
        setup(massing_shape=1, l_notch_units=1, l_notch_width_cells=12, l_notch_depth_cells=2)
        node = a.node('StreetBuildingCore/PARSE_GENERATION_RULES')
        try: node.cook(force=True)
        except Exception: pass  # Negative contract: assert the concrete error and preserved request below.
        require(bool(node.errors()), 'V2 silently clamped an invalid fixed notch')
        require(a.evalParm('l_notch_width_cells') == 12, 'Invalid fixed request was overwritten')
        a.parm('l_notch_width_cells').set(2)
        geometry(a, 'OUT_BUILDING_METADATA'); cases += 1
        setup(random_algorithm=1)
        v1 = signature()
        a.setParms(dict(random_instance_id='', random_seed=777, random_feasible=1, random_seq_upper=999,
                        random_seq_ground=999, random_seq_attachments=999))
        require(signature() == v1, 'Legacy output changed through inactive V2 context')
        cases += 1
        setup(rear_facade_mode=0)
        require(all(row[1] != 3 for row in signature()), 'Closed rear facade emitted modules')
        cases += 1
        setup()
        external = make_external_input('VERIFY_RANDOM_PARCEL', [(-8,0,0),(8,0,0),(8,0,-16),(-8,0,-16)], closed=True)
        a.setInput(0, external); a.parm('site_source_auto').set(1)
        external_before = signature()
        # Reordering source primitives cannot become the random identity: use explicit building_id.
        source = external.node('BUILD_CONTRACT_GEOMETRY')
        code = source.evalParm('python'); source.parm('python').set(code.replace('poly.setAttribValue(bid,77)', 'poly.setAttribValue(bid,78)'))
        external_other = signature()
        source.parm('python').set(code)
        require(signature() == external_before, 'Stable external building_id did not reproduce')
        require(external_other != external_before, 'External stable building identity did not enter random context')
        cases += 2
        a.setInput(0, None); a.parm('site_source_auto').set(0)
        # Compile and execute the actual shared functions, rather than duplicate their implementation in this test.
        prefix = a.node('StreetBuildingCore/PARSE_GENERATION_RULES').evalParm('snippet').split('int sbr_key(')[0]
        probe_container = parent.parent().createNode('geo', 'VERIFY_RANDOM_HASH_VECTOR')
        probe = probe_container.createNode('attribwrangle', 'SHARED_FUNCTION_VECTOR')
        probe.parm('class').set(0)
        probe.parm('snippet').set(prefix+'\ni@hash_a=sbr_hash("A");i@hash_empty=sbr_hash("");int state=1;i@n1=sbr_next(state);i@n2=sbr_next(state);i@n3=sbr_next(state);i@long1=sbr_hash("2|contract-fixture|71|upper|24|window_count");i@long2=sbr_hash("2|0123456789abcdef0123456789abcdef|-2147483648|attachments|2147483647|roof_props_density");')
        g = probe.geometry()
        require([g.intAttribValue(n) for n in ('hash_a','hash_empty','n1','n2','n3','long1','long2')] == [2293,18,16807,282475249,1622650073,277052198,310214396], 'C#/VEX shared test vectors differ')
        cases += 1
        # 输出 null 自身不会传播上游 VEX 编译警告，必须逐个检查本功能修改的 SOP。
        setup()
        for name in ('PARSE_GENERATION_RULES','ALLOCATE_FACADE_CAPACITY','SELECT_FACADE_VARIANTS',
                     'SELECT_FACADE_MODULES','DETAIL_INSTANCE_POINTS','BUILD_METADATA'):
            geometry(a, name)
            node = a.node('StreetBuildingCore/' + name)
            for target in (node,) + tuple(node.allSubChildren()):
                require(not target.errors() and not target.warnings(), 'Random V2 compiler diagnostics: ' + target.path() + repr(target.errors() + target.warnings()))
        cases += 1
        return dict(status='PASS', cases=cases, upper_outputs=len(outcomes), feasible_counts=sorted(observed),
                    seconds=round(time.perf_counter()-start, 3))
    finally:
        if external is not None: external.destroy()
        if probe_container is not None: probe_container.destroy()
        a.destroy()
