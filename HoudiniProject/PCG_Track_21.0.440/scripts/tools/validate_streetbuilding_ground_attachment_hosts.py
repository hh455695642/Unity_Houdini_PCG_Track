"""Cumulative behavior contract for the optional ground-floor host placement."""

from pathlib import Path


def validate_ground_attachment_hosts(parent):
    from validate_streetbuilding_contract import (
        STYLE_CATALOG, configure, geometry, require, set_attachment_overrides,
        signature, style_row,
    )

    asset = parent.parent().createNode(parent.type().name(), "VERIFY_GROUND_HOST_ATTACHMENTS")
    cases = 0
    source = "Assets/PCG/Art/Building_Test/Style1/Prefabs/"

    def catalog(shop_span=1):
        rows = [row for row in STYLE_CATALOG.splitlines()
                if not (row.startswith("M|") and int(row.split("|")[2]) in (0, 14, 15))]
        rows.append(style_row(0, source + "FirstFloor_Window_Host_Test.prefab",
                              width=shop_span, height=4, facades=1, floors=1))
        rows.append(style_row(14, source + "FirstFloor_Awning_A.prefab",
                              height=.293, facades=1, floors=1))
        rows.append(style_row(15, source + "FirstFloor_Sign_A.prefab",
                              height=.22, facades=1, floors=1))
        return "\n".join(rows)

    def setup(*, shape=0, notch_side=0, shop_span=1):
        configure(asset, catalog(shop_span), floors=3, roof=0, attachments=1,
                  density=1, shape=shape, notch_side=notch_side)
        asset.setParms(dict(
            ground_attachment_placement=1, ground_rule_schema_version=2,
            ground_floor_use=2, ground_quantity_mode=0, entrance_count_max=1,
            shopfront_control=0, shopfront_quantity_mode=0, shopfront_count=1,
            shopfront_face_0=1, shopfront_face_1=0,
            shopfront_face_2=0, shopfront_face_3=0,
            awning_density=1, sign_density=1,
            awning_max_count=2, sign_max_count=2,
        ))
        set_attachment_overrides(asset, [(0, 1, 2, 1, 1, 1),
                                         (1, 1, 2, 1, 1, 1)])

    def hosts():
        result = {}
        for point in geometry(asset, "SELECT_FACADE_MODULES").points():
            if (point.intAttribValue("floor_index") != 0 or point.intAttribValue("preview_missing")):
                continue
            role = point.stringAttribValue("module_role")
            if role not in ("Entrance", "GroundShopDoor", "GroundShop"):
                continue
            key = (point.intAttribValue("building_id"),
                   point.intAttribValue("facade_target"),
                   point.intAttribValue("floor_index"),
                   point.intAttribValue("cell_index"))
            require(key not in result, "Duplicate allocated ground host")
            result[key] = (role, point.intAttribValue("module_span"))
        return result

    def details():
        return [point for point in geometry(asset, "DETAIL_INSTANCE_POINTS").points()
                if point.stringAttribValue("module_role") in ("Awning", "Sign")]

    def module_bounds(payload=None):
        """Read declared source geometry independently of generated mount metadata."""
        result = {}
        for row in (payload or asset.parm("unity_style_catalog").eval()).splitlines():
            fields = row.split("|")
            if fields[0] != "M":
                continue
            require(len(fields) == 18, "Malformed bounds fixture")
            minimum = tuple(float(value) for value in fields[15:18])
            size = tuple(float(value) for value in fields[12:15])
            result[fields[4]] = (minimum, tuple(minimum[axis] + size[axis] for axis in range(3)))
        return result

    def replace_bounds(payload, roles, *, minimum=None, size=None):
        rows = []
        for row in payload.splitlines():
            fields = row.split("|")
            if fields[0] == "M" and int(fields[2]) in roles:
                if minimum is not None:
                    fields[15:18] = [str(value) for value in minimum]
                if size is not None:
                    fields[12:15] = [str(value) for value in size]
            rows.append("|".join(fields))
        return "\n".join(rows)

    def front_host_geometry():
        bounds = module_bounds()
        result = {}
        for point in geometry(asset, "SELECT_FACADE_MODULES").points():
            if (point.intAttribValue("floor_index") != 0
                    or point.intAttribValue("facade_target") != 0
                    or point.intAttribValue("preview_missing")
                    or point.stringAttribValue("module_role") not in ("Entrance", "GroundShopDoor", "GroundShop")):
                continue
            path = point.stringAttribValue("unity_instance")
            lo, hi = bounds[path]
            position = tuple(point.position())
            # These tests intentionally use physical front face 0, whose Unity
            # source bounds only need the established Houdini X reflection.
            require(point.intAttribValue("face_index") == 0, "Front fixture acquired an unexpected physical face")
            key = (point.intAttribValue("building_id"), 0, point.intAttribValue("floor_index"),
                   point.intAttribValue("cell_index"))
            result[key] = dict(top=position[1] + hi[1], wall=position[2] + hi[2],
                               center_x=-position[0] + (lo[0] + hi[0]) * .5,
                               width=hi[0] - lo[0], path=path)
        return result

    def mounted_bounds():
        allocated = front_host_geometry()
        bounds = module_bounds()
        result = {}
        for point in details():
            require(point.intAttribValue("face_index") == 0, "Mounted bounds fixture escaped physical front")
            key = (point.intAttribValue("building_id"), 0, point.intAttribValue("floor_index"),
                   point.intAttribValue("cell_index"))
            require(key in allocated, "Commercial attachment appeared over an unallocated solid-wall cell")
            lo, hi = bounds[point.stringAttribValue("unity_instance")]
            position = tuple(point.position())
            unity_position = (-position[0], position[1], position[2])
            world_lo = tuple(unity_position[axis] + lo[axis] for axis in range(3))
            world_hi = tuple(unity_position[axis] + hi[axis] for axis in range(3))
            role = point.stringAttribValue("module_role")
            identity = (point.stringAttribValue("attachment_host_id"), role)
            require(identity not in result, "A single commercial host received duplicate attachment modules")
            result[identity] = dict(role=role, host=allocated[key], lo=world_lo, hi=world_hi,
                                    position=unity_position, path=point.stringAttribValue("unity_instance"))
        return result

    def assert_bounds_mounts():
        actual = mounted_bounds()
        require(actual, "Mount geometry fixture emitted no attachments")
        bounds = module_bounds()
        for item in actual.values():
            source_lo, source_hi = bounds[item["path"]]
            horizontal = item["role"] == "Sign" and source_hi[0] - source_lo[0] >= source_hi[2] - source_lo[2]
            expected = item["host"]["top"] + (.02 if horizontal else -.04 if item["role"] == "Awning" else -.02)
            measured = item["lo"][1] if horizontal else item["hi"][1]
            require(abs(measured - expected) < 1e-4,
                    f"{item['role']} ignored actual host/source bounds: measured={measured}, expected={expected}")
            require(item["lo"][1] >= 2.35 - 1e-4, f"{item['role']} failed real lowest-point clearance")
            require(abs(item["lo"][2] - item["host"]["wall"]) < 1e-4,
                    f"{item['role']} retained a fixed wall standoff instead of its wall-side source mount")
            if item["role"] == "Awning" or horizontal:
                host_left = item["host"]["center_x"] - item["host"]["width"] * .5
                host_right = item["host"]["center_x"] + item["host"]["width"] * .5
                require(item["lo"][0] >= host_left - .02 and item["hi"][0] <= host_right + .02,
                        f"{item['role']} geometry crossed its real host into a neighbouring wall cell")
        return actual

    try:
        require(asset.parm("ground_attachment_placement") is not None,
                "Optional host placement menu is missing")
        require(asset.parm("ground_attachment_placement").eval() == 0,
                "Legacy grid placement is not the default")
        for shape, side in ((0, 0), (1, 0), (1, 2), (1, 3)):
            setup(shape=shape, notch_side=side)
            allocated = hosts()
            front_hosts = {key: value for key, value in allocated.items() if key[1] == 0}
            require(len(front_hosts) >= 2, f"Test fixture has fewer than two front hosts: {shape}/{side}")
            facade_signature = signature(geometry(asset, "SELECT_FACADE_MODULES"))
            actual = details()
            for role in ("Awning", "Sign"):
                group = [p for p in actual if p.stringAttribValue("module_role") == role]
                require(len(group) == 2, f"{role} count differs from capped front hosts: {shape}/{side}")
                identities = []
                for point in group:
                    key = (point.intAttribValue("building_id"), 0,
                           point.intAttribValue("floor_index"),
                           point.intAttribValue("cell_index"))
                    require(key in front_hosts, f"{role} is not attached to an allocated host")
                    require(point.stringAttribValue("attachment_host_role") == front_hosts[key][0],
                            f"{role} host role metadata differs")
                    require(point.intAttribValue("attachment_host_span") == front_hosts[key][1],
                            f"{role} host span metadata differs")
                    require(point.stringAttribValue("attachment_host_id"),
                            f"{role} host id is empty")
                    require(point.intAttribValue("face_index") == 0,
                            f"{role} escaped the main-front mask")
                    identities.append(point.stringAttribValue("attachment_host_id"))
                require(len(identities) == len(set(identities)), f"{role} host was duplicated")
            require(signature(geometry(asset, "DETAIL_INSTANCE_POINTS")) ==
                    signature(geometry(asset, "DETAIL_INSTANCE_POINTS")),
                    "Recook changed host attachment output")
            require(signature(geometry(asset, "SELECT_FACADE_MODULES")) == facade_signature,
                    "Attachment mode changed facade allocation")
            assert_bounds_mounts()
            asset.parm("ground_attachment_placement").set(0)
            legacy = signature(geometry(asset, "DETAIL_INSTANCE_POINTS"))
            asset.parm("ground_attachment_placement").set(1)
            asset.parm("ground_attachment_placement").set(0)
            require(signature(geometry(asset, "DETAIL_INSTANCE_POINTS")) == legacy,
                    "Legacy grid output changed after a mode round trip")
            cases += 1

        setup(shop_span=2)
        double_hosts = {key: value for key, value in hosts().items()
                        if key[1] == 0 and value[0] == "GroundShop"}
        require(len(double_hosts) == 1 and next(iter(double_hosts.values()))[1] == 2,
                "Double-width shop must be one host module")
        require(len([p for p in details() if p.stringAttribValue("module_role") == "Awning"]) == 2,
                "Double-width shop duplicated an awning")
        cases += 1

        setup()
        asset.parm("attachment_global_density").set(0)
        require(not details(), "Zero global density still emitted ground attachments")
        cases += 1
        setup()
        set_attachment_overrides(asset, [(0, 1, 1, 1, 1, 1), (1, 1, 1, 1, 1, 1)])
        require(len([p for p in details() if p.stringAttribValue("module_role") == "Awning"]) == 1,
                "Ground host mode ignored the attachment maximum")
        cases += 1
        setup()
        set_attachment_overrides(asset, [(0, 1, 2, 0, 1, 1), (1, 1, 2, 0, 1, 1)])
        require(not details(), "Disabled facade masks still emitted attachments")
        cases += 1
        setup()
        asset.parm("attachments_enabled").set(0)
        require(not details(), "Attachment switch did not disable host mode")
        cases += 1
        setup()
        asset.setParms(dict(ground_floor_use=1, residential_door_enabled=0,
                            shopfront_count=0))
        require(not hosts(), "Residential no-opening fixture unexpectedly has a host")
        require(not details(), "No-opening ground floor emitted attachments")
        cases += 1

        # Bounds-derived installation must compensate source Pivot Y changes.
        # The displayed geometry stays fixed although the source origin changes.
        setup()
        baseline = assert_bounds_mounts()
        moved = replace_bounds(catalog(), {14}, minimum=(-1, -1.25, -.1))
        moved = replace_bounds(moved, {15}, minimum=(-1, .65, -.1))
        asset.parm("unity_style_catalog").set(moved)
        shifted = assert_bounds_mounts()
        require(set(shifted) == set(baseline), "Changing a source Pivot changed attachment allocation")
        for identity in baseline:
            for endpoint in ("lo", "hi"):
                require(max(abs(a - b) for a, b in zip(baseline[identity][endpoint], shifted[identity][endpoint])) < 1e-4,
                        f"Pivot shift moved installed geometry: {identity}/{endpoint}")
        cases += 1

        # An explicit source installation point has full XYZ semantics. Check
        # that point in world space rather than merely trusting reported bounds.
        setup()
        explicit = replace_bounds(catalog(), {14}, minimum=(-.7, -.8, .2))
        awning_path = source + "FirstFloor_Awning_A.prefab"
        anchor = (.3, -.507, .2)
        explicit += "\nA|1|" + awning_path + "|" + "|".join(str(value) for value in anchor)
        asset.parm("unity_style_catalog").set(explicit)
        actual = mounted_bounds()
        awnings = [item for item in actual.values() if item["role"] == "Awning"]
        require(len(awnings) == 2, "Explicit mount fixture lost valid hosts")
        for item in awnings:
            world_anchor = tuple(item["position"][axis] + anchor[axis] for axis in range(3))
            expected = (item["host"]["center_x"], item["host"]["top"] - .04, item["host"]["wall"])
            require(max(abs(a - b) for a, b in zip(world_anchor, expected)) < 1e-4,
                    "Explicit XYZ attachment mount was ignored")
        cases += 1

        # The declared floor height remains 4m; only the actual host geometry
        # is shorter. A floor-top constant would incorrectly accept the awning.
        setup()
        short_hosts = replace_bounds(catalog(), {0, 1, 3}, size=(2, 2.5, .2))
        asset.parm("unity_style_catalog").set(short_hosts)
        actual = details()
        require(not [point for point in actual if point.stringAttribValue("module_role") == "Awning"],
                "Low real host geometry emitted a head-height awning")
        require(len([point for point in actual if point.stringAttribValue("module_role") == "Sign"]) == 2,
                "Rejected awnings consumed the independent valid sign quota")
        cases += 1

        setup()
        asset.parm("unity_style_catalog").set(replace_bounds(catalog(), {14}, size=(2.4, .293, .2)))
        require(not [point for point in details() if point.stringAttribValue("module_role") == "Awning"],
                "An over-wide awning escaped real host width fitting")
        cases += 1

        # Logical span is unchanged, but the real shop is narrower. Fitting
        # must use source geometry, not span*cellWidth as an invented width.
        setup()
        asset.parm("unity_style_catalog").set(replace_bounds(catalog(), {0}, size=(1.5, 4, .2)))
        actual = mounted_bounds()
        awnings = [item for item in actual.values() if item["role"] == "Awning"]
        require(len(awnings) == 1 and awnings[0]["host"]["width"] >= 2 - 1e-4,
                "Logical module span incorrectly allowed an awning over a narrower real shop")
        cases += 1

        setup()
        blade = replace_bounds(catalog(), {15}, size=(.2, .6, .8))
        asset.parm("unity_style_catalog").set(blade)
        actual = assert_bounds_mounts()
        require(len([item for item in actual.values() if item["role"] == "Sign"]) == 2,
                "Blade-sign fixture lost valid source bounds")
        cases += 1

        setup()
        taller_hosts = replace_bounds(catalog(), {0, 1, 3}, minimum=(-1, -.35, -.1))
        asset.parm("unity_style_catalog").set(taller_hosts)
        assert_bounds_mounts()
        cases += 1
        return {"status": "PASS", "cases": cases, "placement_default": 0,
                "main_front_cap": 2, "double_width_one_host": True,
                "actual_bounds_mounts": True, "pivot_y_compensation": True,
                "explicit_xyz_mount": True, "solid_wall_has_no_commercial_awning": True,
                "lowest_point_clearance": 2.35, "actual_host_width_fitting": True}
    finally:
        asset.destroy()
