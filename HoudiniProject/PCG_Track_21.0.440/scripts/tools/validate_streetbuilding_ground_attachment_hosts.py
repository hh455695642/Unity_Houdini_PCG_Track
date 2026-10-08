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
        return {"status": "PASS", "cases": cases, "placement_default": 0,
                "main_front_cap": 2, "double_width_one_host": True}
    finally:
        asset.destroy()
