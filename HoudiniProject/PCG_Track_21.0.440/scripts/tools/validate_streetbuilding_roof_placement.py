"""Behavior contracts for roof placement, independent of the patch recipe.

The caller supplies its existing fixture/configuration helpers and a base module
catalog. This suite never edits definitions or saves a scene/HIP.
"""


def assert_roof_placement(asset, configure, geometry, catalog):
    def require(condition, message):
        if not condition:
            raise RuntimeError('Roof placement: ' + message)

    # Independent unknown filenames and declared real source bounds. These rows
    # must work without the planner guessing a subtype from a production name.
    source_bounds = {}
    rows = []
    for subtype, name, size, minimum in (
        (1, 'RoofContractTank', (1.8, 3.5, 1.8), (-.9, 0, -.9)),
        (2, 'RoofContractFlue', (.6, 1.4, .6), (-.3, 0, -.3)),
    ):
        path = 'Assets/PCG/ContractFixtures/' + name + '.prefab'
        rows += [f'M|7|18|{name}|{path}|1|1|3|0|1|15|4|'
                 + '|'.join(str(x) for x in (*size, *minimum)),
                 f'X|1|{path}|{subtype}|0']
        source_bounds[path] = (minimum, size)
    fixture_catalog = catalog + '\n' + '\n'.join(rows)
    old = {p.name(): (p.rawValue() if p.parmTemplate().type().name() == 'String' else p.eval(),
                      p.keyframes()) for p in asset.parms() if not p.isMultiParmParent()}
    samples = []

    def state():
        out = geometry(asset, 'OUT_DETAIL_INSTANCES')
        planner = geometry(asset, 'PLAN_TYPED_ROOF_PROPS')
        actual = {1: 0, 2: 0}
        groups = {1: set(), 2: set()}
        signature = []
        footprints = []
        has_subtype = out.findPointAttrib('attachment_subtype') is not None
        for point in out.points():
            subtype = point.intAttribValue('attachment_subtype') if has_subtype else 0
            if subtype not in actual:
                continue
            path = point.stringAttribValue('unity_instance')
            actual[subtype] += 1
            groups[subtype].add(point.stringAttribValue('attachment_group_id'))
            pos = tuple(point.position())
            signature.append((subtype, path, *[round(x, 6) for x in pos]))
            require(path in source_bounds, 'synthetic fixture picked unexpected asset ' + path)
            minimum, size = source_bounds[path]
            # Engine output x is mirrored. Planner source bounds are Unity local.
            origin = (-pos[0], pos[1], pos[2])
            lo = tuple(origin[i] + minimum[i] for i in range(3))
            hi = tuple(lo[i] + size[i] for i in range(3))
            require(lo[0] >= -asset.evalParm('building_width')*.5+.249
                    and hi[0] <= asset.evalParm('building_width')*.5-.249
                    and lo[2] >= -asset.evalParm('building_depth')+.249 and hi[2] <= -.249,
                    'source geometry extends outside the supported roof')
            for alo, ahi in footprints:
                overlap_x = min(hi[0], ahi[0]) - max(lo[0], alo[0])
                overlap_z = min(hi[2], ahi[2]) - max(lo[2], alo[2])
                require(overlap_x <= -.299 or overlap_z <= -.299,
                        'accepted roof sources lost the 0.3m reservation gap')
            footprints.append((lo, hi))
        requests, quantity_seeds, position_seeds = {}, {}, {}
        require(len(groups[1]) == actual[1] and len(groups[2]) == actual[2]
                and not groups[1].intersection(groups[2]),
                'roof group identities collide across subtypes or within one subtype')
        for subtype, token in ((1, 'water'), (2, 'chimney')):
            requests[subtype] = planner.intAttribValue('reference_' + token + '_requested')
            require(actual[subtype] == planner.intAttribValue('reference_' + token + '_actual'),
                    token + ' diagnostic does not match the final output')
            require(actual[subtype] <= requests[subtype], token + ' output exceeded its request')
            quantity_seeds[subtype] = planner.intAttribValue('reference_' + token + '_quantity_seed')
            position_seeds[subtype] = planner.intAttribValue('reference_' + token + '_position_seed')
        return dict(requests=requests, actual=actual, quantity_seeds=quantity_seeds,
                    position_seeds=position_seeds, signature=tuple(sorted(signature)))

    try:
        configure(asset, fixture_catalog, width=16, depth=12, floors=3, seed=17, density=0)
        asset.setParms(dict(roof_props_layout_mode=1, water_tower_count=1, chimney_count=2,
                            water_tower_count_mode=0, chimney_count_mode=0,
                            roof_prop_position_mode=0, fire_escape_layout_mode=0,
                            fire_escape_max_count=0, drainpipe_enabled=0, random_algorithm=1))
        # Legacy fixed mode ignores invalid hidden range fields and retains the
        # old exact first-fit position order for known synthetic bounds.
        asset.setParms(dict(water_tower_count_min=5, water_tower_count_max=2,
                            chimney_count_min=5, chimney_count_max=2))
        legacy = state()
        require(legacy['requests'] == {1: 1, 2: 2} and legacy['actual'] == {1: 1, 2: 2},
                'fixed quantities changed because hidden range values were edited')
        header = fixture_catalog.splitlines()[0].split('|')
        expected_roof = float(header[2]) + 2*float(header[3])
        require(any(row[0] == 1 and row[2:] == (6.5, expected_roof, -1.5) for row in legacy['signature']),
                'Legacy no longer uses the captured first legal tower location')
        asset.parm('variation_seed').set(999)
        require(state()['signature'] == legacy['signature'], 'Legacy placement changed with a new seed')

        asset.setParms(dict(roof_prop_position_mode=1, water_tower_count_mode=1,
                            water_tower_count_min=0, water_tower_count_max=1,
                            chimney_count_mode=1, chimney_count_min=1, chimney_count_max=3))
        for seed in range(32):
            asset.parm('variation_seed').set(seed)
            first = state()
            # Explicit dirty/re-cook proves determinism, not a cached geometry read.
            asset.node('StreetBuildingCore/PLAN_TYPED_ROOF_PROPS').cook(force=True)
            again = state()
            require(first == again, 'same seed and inputs did not reproduce the same output')
            require(0 <= first['requests'][1] <= 1 and 1 <= first['requests'][2] <= 3,
                    'RandomRange request escaped its closed integer range')
            require(first['actual'] == first['requests'], 'spacious control fixture hit unexpected capacity')
            samples.append(dict(seed=seed, **first))
        require(len({row['requests'][1] for row in samples}) == 2, 'tower random quantity did not vary')
        require(len({row['requests'][2] for row in samples}) >= 2, 'chimney random quantity did not vary')
        require(len({row['signature'] for row in samples}) >= 8, 'Seeded positions were effectively uniform')

        # Changing tower count does not advance the chimney's quantity/position
        # random stream. Its final placement can still move to avoid real props.
        asset.parm('variation_seed').set(13)
        before = state()
        asset.setParms(dict(water_tower_count_mode=0, water_tower_count=0))
        after = state()
        for key in ('requests', 'quantity_seeds', 'position_seeds'):
            require(before[key][2] == after[key][2], 'tower configuration leaked into chimney ' + key)

        asset.setParms(dict(random_algorithm=2, random_instance_id='roof-contract-stable-id',
                            random_seed=17, random_seq_attachments=0,
                            water_tower_count_mode=1, water_tower_count_min=0, water_tower_count_max=1))
        v2 = state()
        require(state() == v2, 'V2 same identity/master/sequence did not reproduce the same roof')
        asset.parm('random_seq_ground').set(asset.evalParm('random_seq_ground')+1)
        ground_redraw = state()
        require(v2 == ground_redraw, 'ground-group redraw changed the independent roof stream')
        asset.parm('random_seq_attachments').set(1)
        attachment_redraw = state()
        require(attachment_redraw['position_seeds'] != v2['position_seeds']
                and attachment_redraw['quantity_seeds'] != v2['quantity_seeds'],
                'attachment-group redraw did not reach the roof random domains')
        asset.parm('random_seed').set(91)
        master_redraw = state()
        require(master_redraw['position_seeds'] != attachment_redraw['position_seeds'],
                'V2 master seed did not reach the roof position stream')
        asset.setParms(dict(roof_prop_position_mode=0, water_tower_count_mode=0,
                            chimney_count_mode=0, water_tower_count=1, chimney_count=2))
        v2_legacy = state()
        asset.setParms(dict(random_seed=991, random_seq_attachments=8))
        require(state()['signature'] == v2_legacy['signature'], 'V2 redraw changed Legacy fixed placement')
        asset.setParms(dict(random_algorithm=1, roof_prop_position_mode=1,
                            water_tower_count_mode=1, chimney_count_mode=1))

        asset.setParms(dict(water_tower_count_mode=1, water_tower_count_min=2, water_tower_count_max=2,
                            chimney_count_min=0, chimney_count_max=0))
        point_range = state()
        require(point_range['requests'] == {1: 2, 2: 0}, 'equal range endpoints were not exact')
        asset.setParms(dict(building_width=4, building_depth=4, water_tower_count_min=4,
                            water_tower_count_max=4))
        limited = state()
        require(limited['requests'][1] == 4 and limited['actual'][1] < 4,
                'capacity reduction changed the request or allowed too many props')
        require(asset.evalParm('water_tower_count_min') == 4, 'capacity rewrote the instance request')

        asset.setParms(dict(building_width=32, building_depth=32, roof_prop_position_mode=0,
                            water_tower_count_min=33, water_tower_count_max=33,
                            chimney_count_min=1, chimney_count_max=1))
        large = state()
        require(large['requests'] == {1: 33, 2: 1} and large['actual'] == large['requests'],
                'large roof did not preserve distinct identities above the old 32-group namespace')

        # A bad active range is a real configuration error, not normalized input.
        asset.setParms(dict(water_tower_count_min=3, water_tower_count_max=1))
        rejected = False
        try:
            geometry(asset, 'PLAN_TYPED_ROOF_PROPS')
        except Exception as exc:
            rejected = 'random count requires' in str(exc) or bool(
                asset.node('StreetBuildingCore/PLAN_TYPED_ROOF_PROPS').errors())
        require(rejected, 'invalid active range was silently normalized')
        return dict(status='PASS', seeds=len(samples),
                    tower_quantities=sorted({row['requests'][1] for row in samples}),
                    chimney_quantities=sorted({row['requests'][2] for row in samples}),
                    distinct_signatures=len({row['signature'] for row in samples}),
                    legacy_signature=legacy['signature'], large_roof_actual=large['actual'],
                    v2_master_and_attachment_redraw=True, v2_ground_redraw_isolated=True, samples=samples)
    finally:
        for name, (value, keyframes) in old.items():
            parm = asset.parm(name)
            if parm is not None:
                if keyframes:
                    parm.deleteAllKeyframes()
                    parm.setKeyframes(keyframes)
                else:
                    parm.set(value)
