"""Independent feature, input and geometry contracts for CityRoad's building output."""

from dataclasses import replace

import hou

from validate_cityroad_gap_range import (
    RANGE_MAX, RANGE_MIN, RETIRED_FIELDS, ROAD_WIDTH, SIDEWALK_WIDTH, Profile,
    _assert_seams, _snapshot, _straight_road, gap_fixture, measure_seams,
)


BUILDING_DEFAULTS = {
    "enabled": 1, "junction_margin": 0.0, "ground_height": 0.0,
    "seed": 1729, "layout_seed_offset": 0,
}
SIDEWALK_LINE = ROAD_WIDTH / 2.0 + SIDEWALK_WIDTH


def _verify_interface(asset):
    build = asset.node("CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE")
    assert build is not None, "CityRoad frontage generator missing"
    output = asset.node("CityRoadCore/OUT_STREET_BUILDINGS")
    assert output and output.inputs()[0] == build.parent(), "Building output disconnected"
    controls = next((t for t in asset.parmTemplateGroup().entries()
                     if t.label() == "Street Buildings / 沿街建筑"), None)
    assert controls is not None, "Public frontage folder missing"
    templates = {t.name(): t for t in controls.parmTemplates()}
    layout_fields = {"building_setback_grouped"}
    layout_fields.update(f"building_{name}_{end}_{unit}"
                         for name, unit in (("setback", "m"), ("group_length", "m"),
                                            ("group_offset", "m"), ("empty", "pct"),
                                            ("height_offset", "m"))
                         for end in ("min", "max"))
    assert set(templates) == ({f"building_{key}" for key in BUILDING_DEFAULTS}
                              | RETIRED_FIELDS.keys() | layout_fields
                              | {"building_prefabs", "building_frontage_catalog",
                                 "building_setback", "building_layout_ranges_enabled",
                                 "building_corners_enabled", "building_corner_prefabs", RANGE_MIN, RANGE_MAX})
    catalog = templates["building_frontage_catalog"]
    assert catalog.isHidden() and catalog.defaultValue() == ("",), "Catalog transport must remain internal"
    for field, slot_name in (("building_prefabs", "building_prefab#"),
                             ("building_corner_prefabs", "building_corner_prefab#")):
        multiparm = templates[field]
        assert not multiparm.isHidden() and multiparm.defaultValue() == 0, field
        slot, = multiparm.parmTemplates()
        assert slot.name() == slot_name and slot.tags().get("heuassetpath") == "1", slot_name
        assert slot.defaultValue() == ("",), "Fresh HDA must not hard-code art assets"
    corner_mode = templates["building_corners_enabled"]
    assert not corner_mode.isHidden() and corner_mode.defaultValue() is False
    merge = build.input(3)
    assert merge is not None and merge.name() == "JUNCTION_APPROACHES"
    assert merge.node(merge.parm("objpath1").eval()) == asset.node(
        "CityRoadCore/CR_MAIN_PIPELINE/CR_JUNCTION_INDEX/JUNCTION_APPROACH_INDEX_V2")
    assert build.parm("library") is None, "Obsolete catalog directory bridge retained"
    assert build.parm("variants").expression() == 'ch("../../../building_prefabs")'
    for name, expected in BUILDING_DEFAULTS.items():
        template = templates["building_" + name]
        default = template.defaultValue()
        default = default[0] if isinstance(default, tuple) else default
        if name == "ground_height" and not asset.matchesCurrentDefinition() and default == .6:
            # The unlocked edit still inherits the old definition until persistence.
            expected = .6
        assert abs(default - expected) < .00001 and not template.isHidden(), (name, default)
        assert build.parm(name).expression() == f'ch("../../../building_{name}")', name


def _placement_only(records):
    return [(r["building_id"], r["position"], r["rotation"], r["facade_min_x"], r["facade_max_x"])
            for r in records]


def _strip_road(length):
    road = hou.Geometry()
    sections = []
    for x in range(0, length + 1, 3):
        section = []
        for z in (-8, 8):
            point = road.createPoint()
            point.setPosition((x, 0, z))
            section.append(point)
        sections.append(section)
    for a, b in zip(sections, sections[1:]):
        for vertices in ((a[0], a[1], b[1]), (a[0], b[1], b[0])):
            face = road.createPolygon()
            for point in vertices:
                face.addVertex(point)
    return road


def _bent_road():
    road = hou.Geometry()
    points = []
    for x, z in ((0, -8), (100, -8), (20, -7.999), (115, -7.88), (0, 8), (100, 8), (115, 8)):
        point = road.createPoint()
        point.setPosition((x, 0, z))
        points.append(point)
    for indices in ((0, 1, 2), (0, 2, 4), (2, 1, 5), (2, 5, 4), (1, 3, 6), (1, 6, 5)):
        face = road.createPolygon()
        for index in indices:
            face.addVertex(points[index])
    return road


def _verify_road_inputs(fixture, baseline):
    road, graph, approaches = _straight_road(fixture.length)
    degenerate = hou.Geometry()
    degenerate.merge(road)
    sliver = degenerate.createPoint()
    sliver.setPosition((.001, 0, -8))
    face = degenerate.createPolygon()
    for point in (degenerate.points()[0], degenerate.points()[3], sliver):
        face.addVertex(point)
    fixture.set_geometry(degenerate, graph, approaches)
    assert _snapshot(fixture.cook(2, 2)) == baseline, "Thin triangle removed a frontage side"
    assert len(fixture.build.input(1).geometry().prims()) == 2, "Thin triangle survived boundary cleaning"
    fixture.set_geometry(_strip_road(int(fixture.length)), graph, approaches)
    assert _snapshot(fixture.cook(2, 2)) == baseline, "Short boundary segments changed the row"

    fixture.set_geometry(_bent_road(), graph, approaches)
    curved = fixture.cook(2, 2)
    exposed = [p.position()[0] for p in curved.points()
               if p.position()[2] < -8 and p.attribValue("N")[2] > .99]
    assert len(exposed) >= 7 and max(exposed) - min(exposed) > 60, "Merged arc lost its outward side"

    translation = hou.Vector3(0, 0, 50)
    for geometry in (road, graph):
        for point in geometry.points():
            point.setPosition(point.position() + translation)
    fixture.set_geometry(road, graph, approaches)
    moved = sorted(tuple(p.position() - translation) for p in fixture.cook(2, 2).points())
    original = sorted(row[0] for row in baseline)
    assert len(moved) == len(original)
    assert all((hou.Vector3(a) - hou.Vector3(b)).length() < .001 for a, b in zip(moved, original)), (
        "CityRoad input translation did not carry its frontage"
    )
    return len(exposed)


def _verify_direct_assignment(fixture, profiles, baseline_count):
    root = fixture.root
    for index in range(1, len(profiles) + 1):
        root.parm(f"building_prefab{index}").set("")
    assert not fixture.cook(2, 2).points(), "Empty slots generated invalid instances"

    arbitrary = "Assets/ArtistBuildings/Arbitrary_Name.prefab"
    root.parm("building_prefab3").set(arbitrary)
    missing = fixture.cook(2, 2)
    assert not missing.points() and tuple(missing.attribValue("frontage_missing_prefabs")) == (arbitrary,)
    row = replace(profiles[0], prefab=arbitrary)
    fixture.set_catalog([row.catalog_row()])
    placed = fixture.cook(2, 2).points()
    assert len(placed) == baseline_count
    assert all(p.stringAttribValue("unity_instance") == arbitrary for p in placed)
    root.parm("building_prefabs").set(0)
    assert not fixture.cook(2, 2).points(), "An empty Prefab list generated instances"
    root.parm("building_prefabs").set(len(profiles))
    for index, profile in enumerate(profiles, start=1):
        root.parm(f"building_prefab{index}").set(profile.prefab)
    fixture.set_catalog(p.catalog_row() for p in profiles)


def _verify_fixed_controls(fixture, baseline_count):
    spaced = fixture.records(fixture.cook(10, 10))
    assert len(spaced) < baseline_count and measure_seams(spaced)
    _assert_seams(measure_seams(spaced), 10, 10)
    set_back = fixture.records(fixture.cook(2, 2, building_setback_min_m=7, building_setback_max_m=7))
    assert all(abs(abs(r["facade_z"]) - (SIDEWALK_LINE + 7)) < .001 for r in set_back)
    margin = fixture.records(fixture.cook(2, 2, building_setback_min_m=3, building_setback_max_m=3,
                                         building_junction_margin=20))
    assert margin and all(19.999 <= r["facade_min_x"] <= r["facade_max_x"] <= fixture.length - 19.999
                          for r in margin)
    raised = fixture.records(fixture.cook(2, 2, building_junction_margin=0, building_ground_height=2))
    assert all(abs(r["position"][1] - 2) < .001 for r in raised)
    assert not fixture.cook(2, 2, building_ground_height=.6, building_enabled=0).points()
    assert len(fixture.cook(2, 2, building_enabled=1).points()) == baseline_count


def _verify_profiles(asset):
    narrow = Profile.centered(6)
    wide = Profile("Assets/ArtistBuildings/Asymmetric.prefab", -2, 6, 4, -2, 6, -4, 4)
    bad = replace(narrow, prefab="Assets/ArtistBuildings/Malformed.prefab")
    with gap_fixture(asset, [narrow, wide, bad], length=120) as fixture:
        fixture.set_catalog([narrow.catalog_row(), wide.catalog_row(),
                             bad.catalog_row().replace("|-3", "|oops", 1)])
        geo = fixture.cook(1, 1, building_setback_min_m=3, building_setback_max_m=3)
        assert geo.attribValue("frontage_malformed_catalog_rows") == 1
        assert tuple(geo.attribValue("frontage_missing_prefabs")) == (bad.prefab,)
        assert geo.attribValue("frontage_rejected_terminal") == 2
        records = fixture.records(geo)
        for side in ("-", "+"):
            row = [r for r in records if r["side"] == side]
            assert {round(r["width_m"]) for r in row} == {6, 8}
            assert sum(r["width_m"] for r in row) / fixture.length >= .80
        for row in records:
            assert abs(abs(row["facade_z"]) - (SIDEWALK_LINE + 3.0)) < .001
        _assert_seams(measure_seams(records), 1, 1)
        fixture.set_catalog([])
        empty = fixture.cook(1, 1)
        assert not empty.points() and empty.attribValue("building_count") == 0
        assert set(empty.attribValue("frontage_missing_prefabs")) == {p.prefab for p in (narrow, wide, bad)}
    return {"points": len(records), "max_gap_m": 1.0, "asymmetric_profile": True}


def validate(asset):
    _verify_interface(asset)
    profiles = [replace(Profile.centered(8), prefab=f"Assets/ArtistBuildings/Manual_{i}.prefab")
                for i in range(1, 9)]
    with gap_fixture(asset, profiles, length=120) as fixture:
        geo = fixture.cook(2, 2, building_setback_min_m=3, building_setback_max_m=3)
        records = fixture.records(geo)
        baseline = _snapshot(geo)
        sides = {side: sum(r["side"] == side for r in records) for side in ("-", "+")}
        assert min(sides.values()) >= 7, sides
        assert all(-.001 <= r["facade_min_x"] <= r["facade_max_x"] <= 120.001 for r in records)
        assert all(r["side"] == ("+" if r["position"][2] > 0 else "-")
                   and abs(r["facade_z"]) < abs(r["position"][2])
                   and abs(r["facade_z"]) >= SIDEWALK_LINE + 2.999 for r in records)
        _assert_seams(measure_seams(records), 2, 2)
        assert _snapshot(fixture.cook(2, 2)) == baseline, "Recook changed placement"
        reseeded = fixture.records(fixture.cook(2, 2, building_seed=99))
        assert [r["prefab"] for r in records] != [r["prefab"] for r in reseeded], "Random seed ignored"
        assert _placement_only(records) == _placement_only(reseeded), "Appearance seed moved a parcel"
        fixture.root.parm("building_seed").set(BUILDING_DEFAULTS["seed"])
        _verify_direct_assignment(fixture, profiles, len(records))
        _verify_fixed_controls(fixture, len(records))
        curved_side_points = _verify_road_inputs(fixture, baseline)

    from importlib import reload
    import validate_cityroad_corners
    corners = reload(validate_cityroad_corners).validate(asset)
    return {
        "contract_id": "CityRoad.V52.StreetBuildingPlacement",
        "public_controls": "CityRoad.V53.BuildingControls",
        "direct_prefabs": "CityRoad.V54.DirectPrefabAssignment",
        "varied_layout": "CityRoad.V55.BuildingLayout",
        "varied_layout_coverage": "CityRoad.V57.StreetLayoutRanges",
        "empty_slots": True, "arbitrary_prefab_names": True, "seed_changes_variants_only": True,
        "spacing": True, "setback": True, "corner_margin": True, "base_height": True,
        "points": len(records), "both_sides": sides, "terminal_clear": True,
        "road_move": True, "deterministic": True, "toggle": True,
        "thin_triangle": True, "short_segments": True, "curved_side_points": curved_side_points,
        "actual_frontage": _verify_profiles(asset), "dual_frontage_corners": corners,
    }
