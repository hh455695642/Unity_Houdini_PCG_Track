"""Build the editable Style1 reference geometry in an independent hython process.

Only the explicitly supplied staging directory is written. No HIP/HDA is loaded,
saved or rebuilt. The exported CPIO contains native Add/Attribute Wrangle/Normal
SOPs, so profile points and texture coordinates remain editable in Houdini.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


PALETTE = [
    {"name": "green", "color": "#183C32"},
    {"name": "green_light", "color": "#2B5545"},
    {"name": "stone", "color": "#B8AC91"},
    {"name": "dark_metal", "color": "#252A28"},
    {"name": "brass", "color": "#A98A47"},
    {"name": "wood", "color": "#4C3928"},
]
MATERIALS = ("Brick", "Trim", "Glass")
SOURCE_MARKER = "STYLE1_REFERENCE_NATIVE_SOP_20261024_V1"


def subtract(first, second):
    return tuple(first[index] - second[index] for index in range(3))


def cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def normal(points):
    result = cross(subtract(points[1], points[0]), subtract(points[2], points[0]))
    length = math.sqrt(sum(value * value for value in result))
    if length < 1e-9:
        raise ValueError("Degenerate profile")
    return tuple(value / length for value in result)


class Module:
    def __init__(self, name, width, role, description):
        self.name = name
        self.width = width
        self.role = role
        self.description = description
        self.parts = []

    def surface(self, label, points, material=1, palette=0):
        points = [tuple(float(value) for value in point) for point in points]
        face_normal = normal(points)
        if material == 0:
            coordinates = [(point[0], point[1]) for point in points]
        elif material == 1:
            coordinates = [((palette + 0.5) / len(PALETTE), 0.5)] * len(points)
        else:
            coordinates = [((point[0] + self.width / 2) / self.width, point[1] / 3) for point in points]
        self.parts.append({"name": label, "material": material, "points": points,
                           "uv": coordinates, "normal": face_normal})

    def panel(self, label, left, bottom, right, top, depth=0.0, material=1, palette=0):
        self.surface(label, [(left, bottom, depth), (right, bottom, depth),
                             (right, top, depth), (left, top, depth)], material, palette)

    def open_box(self, label, left, bottom, back, right, top, front, material=1, palette=0):
        self.panel(label + "_FRONT", left, bottom, right, top, front, material, palette)
        self.surface(label + "_TOP", [(left, top, front), (right, top, front),
                                      (right, top, back), (left, top, back)], material, palette)
        self.surface(label + "_BOTTOM", [(left, bottom, back), (right, bottom, back),
                                         (right, bottom, front), (left, bottom, front)], material, palette)
        self.surface(label + "_LEFT", [(left, bottom, back), (left, bottom, front),
                                       (left, top, front), (left, top, back)], material, palette)
        self.surface(label + "_RIGHT", [(right, bottom, front), (right, bottom, back),
                                        (right, top, back), (right, top, front)], material, palette)

    def arch_strip(self, label, center, inner_half, outer_half, spring, inner_rise,
                   outer_rise, front, back, palette=2, segments=10, joints=False):
        for segment in range(segments):
            first_angle = math.pi * segment / segments
            second_angle = math.pi * (segment + 1) / segments
            if joints:
                first_angle += 0.007
                second_angle -= 0.007
            inner_first = (center + inner_half * math.cos(first_angle),
                           spring + inner_rise * math.sin(first_angle))
            inner_second = (center + inner_half * math.cos(second_angle),
                            spring + inner_rise * math.sin(second_angle))
            outer_first = (center + outer_half * math.cos(first_angle),
                           spring + outer_rise * math.sin(first_angle))
            outer_second = (center + outer_half * math.cos(second_angle),
                            spring + outer_rise * math.sin(second_angle))
            profile = [inner_first, outer_first, outer_second, inner_second]
            self.surface(label + "_" + str(segment) + "_FACE",
                         [(point[0], point[1], front) for point in profile], 1, palette)
            self.surface(label + "_" + str(segment) + "_INNER",
                         [(inner_first[0], inner_first[1], front),
                          (inner_second[0], inner_second[1], front),
                          (inner_second[0], inner_second[1], back),
                          (inner_first[0], inner_first[1], back)], 1, palette)
            self.surface(label + "_" + str(segment) + "_OUTER",
                         [(outer_second[0], outer_second[1], front),
                          (outer_first[0], outer_first[1], front),
                          (outer_first[0], outer_first[1], back),
                          (outer_second[0], outer_second[1], back)], 1, palette)

    def data(self):
        groups = []
        for material, material_name in enumerate(MATERIALS):
            vertices, normals, coordinates, triangles = [], [], [], []
            for part in self.parts:
                if part["material"] != material:
                    continue
                start = len(vertices)
                vertices.extend(part["points"])
                normals.extend([part["normal"]] * len(part["points"]))
                coordinates.extend(part["uv"])
                for corner in range(1, len(part["points"]) - 1):
                    triangles.extend((start, start + corner, start + corner + 1))
            if vertices:
                groups.append({"material": material, "name": material_name, "vertices": vertices,
                               "triangles": triangles, "normals": normals, "uv": coordinates})
        all_vertices = [point for group in groups for point in group["vertices"]]
        return {"name": self.name, "role": self.role, "width": self.width, "height": 3.0,
                "description": self.description, "parts": self.parts, "material_groups": groups,
                "triangle_count": sum(len(group["triangles"]) // 3 for group in groups),
                "bounds_min": [min(point[axis] for point in all_vertices) for axis in range(3)],
                "bounds_max": [max(point[axis] for point in all_vertices) for axis in range(3)]}


def brick_wall():
    module = Module("Reference_BrickWall_2m", 2, "GroundWall/MiddleBlank",
                    "2米砖墙；单面开放壳体；砖UV每米重复一次")
    module.panel("BRICK_WALL", -1, 0, 1, 3, material=0)
    return module


def window_wall(paired=False, arched=True):
    width = 4 if paired else 2
    name = "Reference_Window_ArchPair_4m" if paired else (
        "Reference_Window_Arch_2m" if arched else "Reference_Window_Rect_2m")
    module = Module(name, width, "MiddleWindow",
                    "标准层窄高窗；真窗洞、内凹玻璃、独立浅石窗楣和窗台")
    centers = (-1, 1) if paired else (0,)
    for window_index, center in enumerate(centers):
        prefix = "WINDOW_" + str(window_index)
        left, right = center - 0.52, center + 0.52
        bottom, spring, rise = 0.70, 2.29, 0.16 if arched else 0.0
        module.panel(prefix + "_BRICK_LEFT", center - 1, 0, left, 3, material=0)
        module.panel(prefix + "_BRICK_RIGHT", right, 0, center + 1, 3, material=0)
        module.panel(prefix + "_BRICK_BELOW", left, 0, right, bottom, material=0)
        if arched:
            for segment in range(10):
                first_angle = math.pi * segment / 10
                second_angle = math.pi * (segment + 1) / 10
                first_x, first_y = center + .52 * math.cos(first_angle), spring + rise * math.sin(first_angle)
                second_x, second_y = center + .52 * math.cos(second_angle), spring + rise * math.sin(second_angle)
                module.surface(prefix + "_BRICK_ABOVE_" + str(segment),
                               [(second_x, second_y, 0), (first_x, first_y, 0),
                                (first_x, 3, 0), (second_x, 3, 0)], 0)
            module.arch_strip(prefix + "_STONE_ARCH", center, .515, .66,
                              spring, .16, .32, .075, -.04, joints=True)
            module.arch_strip(prefix + "_DARK_ARCH_FRAME", center, .455, .515,
                              spring, .105, .16, -.095, -.18, palette=3, segments=10)
            glass_profile = [(left + .065, bottom + .07, -.19),
                             (right - .065, bottom + .07, -.19),
                             (right - .065, spring, -.19)]
            for segment in range(1, 11):
                angle = math.pi * segment / 10
                glass_profile.append((center + .455 * math.cos(angle),
                                      spring + .105 * math.sin(angle), -.19))
            module.surface(prefix + "_GLASS", glass_profile, 2)
        else:
            module.panel(prefix + "_BRICK_ABOVE", left, spring, right, 3, material=0)
            module.open_box(prefix + "_STONE_LINTEL", center - .65, spring - .015, -.02,
                            center + .65, spring + .18, .065, palette=2)
            module.open_box(prefix + "_DARK_TOP_FRAME", left, spring - .065, -.19,
                            right, spring, -.095, palette=3)
            module.panel(prefix + "_GLASS", left + .065, bottom + .07,
                         right - .065, spring - .065, -.19, 2)
        module.surface(prefix + "_REVEAL_LEFT", [(left, bottom, 0), (left, bottom, -.19),
                                                (left, spring, -.19), (left, spring, 0)], 1, 2)
        module.surface(prefix + "_REVEAL_RIGHT", [(right, bottom, -.19), (right, bottom, 0),
                                                 (right, spring, 0), (right, spring, -.19)], 1, 2)
        module.open_box(prefix + "_FRAME_LEFT", left, bottom, -.19, left + .065, spring, -.095, palette=3)
        module.open_box(prefix + "_FRAME_RIGHT", right - .065, bottom, -.19, right, spring, -.095, palette=3)
        module.open_box(prefix + "_FRAME_BOTTOM", left, bottom, -.19, right, bottom + .07, -.095, palette=3)
        module.open_box(prefix + "_SASH_CROSSBAR", left + .065, 1.51, -.18, right - .065, 1.555, -.08, palette=3)
        module.open_box(prefix + "_SASH_CENTRE", center - .018, bottom + .07, -.18,
                        center + .018, spring - .065, -.09, palette=3)
        module.open_box(prefix + "_STONE_SILL_TOP", center - .66, .60, -.03,
                        center + .66, .72, .20, palette=2)
        module.open_box(prefix + "_STONE_SILL_BASE", center - .59, .54, -.025,
                        center + .59, .605, .12, palette=2)
    return module


def commercial(door=False):
    module = Module("Reference_Entrance_2m" if door else "Reference_Shopfront_2m", 2,
                    "Entrance" if door else "GroundShop",
                    "墨绿色商业门窗；开放背面；下裙板、框架、横梁与内凹玻璃")
    module.panel("BRICK_LEFT_REVEAL", -1, 0, -.87, 3, material=0)
    module.panel("BRICK_RIGHT_REVEAL", .87, 0, 1, 3, material=0)
    module.open_box("FRAME_LEFT", -.87, 0, -.06, -.755, 3, .075, palette=0)
    module.open_box("FRAME_RIGHT", .755, 0, -.06, .87, 3, .075, palette=0)
    module.open_box("PLINTH_LEFT", -.89, 0, -.06, -.735, .16, .105, palette=1)
    module.open_box("PLINTH_RIGHT", .735, 0, -.06, .89, .16, .105, palette=1)
    module.open_box("STRUCTURAL_TOP_BEAM", -.87, 2.52, -.06, .87, 2.73, .08, palette=0)
    module.open_box("STRUCTURAL_CROWN_BOTTOM", -1, 2.73, -.04, 1, 2.81, .14, palette=1)
    module.open_box("STRUCTURAL_FRIEZE", -1, 2.81, -.04, 1, 2.95, .11, palette=0)
    module.open_box("STRUCTURAL_CROWN_TOP", -1, 2.95, -.04, 1, 3, .19, palette=1)
    reveal_bottom = .04 if door else .53
    module.surface("OPENING_REVEAL_LEFT", [(-.755, reveal_bottom, -.06),
                                           (-.755, reveal_bottom, -.13),
                                           (-.755, 2.52, -.13), (-.755, 2.52, -.06)], 1, 0)
    module.surface("OPENING_REVEAL_RIGHT", [(.755, reveal_bottom, -.13),
                                            (.755, reveal_bottom, -.06),
                                            (.755, 2.52, -.06), (.755, 2.52, -.13)], 1, 0)
    module.surface("OPENING_REVEAL_TOP", [(-.755, 2.52, -.13), (.755, 2.52, -.13),
                                          (.755, 2.52, -.06), (-.755, 2.52, -.06)], 1, 0)
    module.surface("OPENING_REVEAL_BOTTOM", [(-.755, reveal_bottom, -.06),
                                             (.755, reveal_bottom, -.06),
                                             (.755, reveal_bottom, -.13),
                                             (-.755, reveal_bottom, -.13)], 1, 0)
    if door:
        module.panel("DOOR_LEFT_EDGE_SEAL", -.755, .04, -.74, 2.52, -.005, 1, 3)
        module.panel("DOOR_RIGHT_EDGE_SEAL", .74, .04, .755, 2.52, -.005, 1, 3)
        module.open_box("DOOR_STILE_LEFT", -.74, .04, -.10, -.66, 2.26, -.005, palette=1)
        module.open_box("DOOR_STILE_RIGHT", .66, .04, -.10, .74, 2.26, -.005, palette=1)
        module.open_box("DOOR_PANEL_FRAME", -.66, .04, -.10, .66, .77, -.015, palette=0)
        for panel_index, center in enumerate((-.32, .32)):
            module.panel("DOOR_RECESSED_PANEL_" + str(panel_index), center - .255, .15,
                         center + .255, .65, -.012, 1, 1)
        module.open_box("DOOR_MID_RAIL", -.66, .77, -.10, .66, .86, -.005, palette=1)
        module.panel("DOOR_MAIN_GLASS", -.66, .86, .66, 2.18, -.13, 2)
        module.surface("DOOR_GLASS_REVEAL_LEFT", [(-.66, .86, -.10), (-.66, .86, -.13),
                                                  (-.66, 2.18, -.13), (-.66, 2.18, -.10)], 1, 3)
        module.surface("DOOR_GLASS_REVEAL_RIGHT", [(.66, .86, -.13), (.66, .86, -.10),
                                                   (.66, 2.18, -.10), (.66, 2.18, -.13)], 1, 3)
        module.surface("DOOR_GLASS_REVEAL_TOP", [(-.66, 2.18, -.13), (.66, 2.18, -.13),
                                                 (.66, 2.18, -.10), (-.66, 2.18, -.10)], 1, 3)
        module.surface("DOOR_GLASS_REVEAL_BOTTOM", [(-.66, .86, -.10), (.66, .86, -.10),
                                                    (.66, .86, -.13), (-.66, .86, -.13)], 1, 3)
        module.open_box("DOOR_TOP_RAIL", -.74, 2.18, -.10, .74, 2.28, -.005, palette=1)
        module.panel("DOOR_TRANSOM_GLASS", -.74, 2.28, .74, 2.52, -.13, 2)
        module.open_box("DOOR_HANDLE", .48, 1.03, -.005, .505, 1.34, .04, palette=4)
        module.open_box("THRESHOLD", -.755, 0, -.12, .755, .04, .12, palette=2)
    else:
        module.open_box("SHOP_PLINTH", -.755, 0, -.10, .755, .12, .09, palette=1)
        module.open_box("SHOP_SKIRT_PANEL", -.755, .12, -.10, .755, .45, .045, palette=0)
        module.panel("SHOP_SKIRT_RECESS", -.67, .19, .67, .38, .048, 1, 1)
        module.open_box("SHOP_WINDOW_SILL", -.80, .45, -.07, .80, .53, .13, palette=1)
        module.panel("SHOP_MAIN_GLASS", -.755, .53, .755, 2.52, -.13, 2)
        module.open_box("SHOP_TRANSOM_RAIL", -.755, 2.13, -.07, .755, 2.19, .035, palette=1)
        module.open_box("SHOP_CENTRE_MULLION", -.022, .53, -.07, .022, 2.52, .035, palette=1)
    return module


def column(upper=False):
    module = Module("Reference_Column_Upper" if upper else "Reference_Column_Ground", .16,
                    "FacadeColumn", "边界立柱；不占用Bay；与窗墙边缘责任分离")
    if upper:
        module.open_box("STONE_SHAFT", -.055, .12, -.025, .055, 2.88, .065, palette=2)
        module.open_box("STONE_CAPITAL", -.08, 2.88, -.025, .08, 3, .095, palette=2)
        module.open_box("STONE_BASE", -.08, 0, -.025, .08, .12, .095, palette=2)
    else:
        module.open_box("GREEN_SHAFT", -.07, .28, -.025, .07, 2.62, .10, palette=0)
        module.open_box("GREEN_SHAFT_FACE", -.038, .36, .10, .038, 2.56, .115, palette=1)
        module.open_box("GREEN_BASE", -.095, 0, -.025, .095, .28, .15, palette=0)
        module.open_box("GREEN_BASE_LIP", -.105, .24, -.025, .105, .30, .17, palette=1)
        module.open_box("GREEN_CAPITAL", -.11, 2.62, -.025, .11, 2.78, .17, palette=0)
        module.open_box("GREEN_CAPITAL_LIP", -.13, 2.78, -.025, .13, 2.84, .20, palette=1)
        module.open_box("GREEN_UPPER_SHAFT", -.07, 2.84, -.025, .07, 3, .10, palette=0)
    return module


def floor_band():
    module = Module("Reference_FloorBand_2m", 2, "FloorBand",
                    "层间浅石腰线；根位于层界线；开放背面，不生成任何文字招牌")
    module.open_box("STONE_BAND", -1, -.105, -.025, 1, .045, .10, palette=2)
    module.open_box("STONE_CAP", -1, .045, -.025, 1, .095, .16, palette=2)
    return module


def create_native_source(hou, modules, output):
    if hou.isUIAvailable():
        raise RuntimeError("This tool only runs in independent hython; do not run in the Live Editor")
    root = hou.node("/obj")
    if root.node("Style1_ReferenceKit_Source") is not None:
        raise RuntimeError("Existing source network must not be overwritten")
    kit = root.createNode("subnet", "Style1_ReferenceKit_Source")
    kit.setUserData("pcg_art_marker", SOURCE_MARKER)
    note = kit.createStickyNote("READ_ME")
    note.setText("Style1参考主体模块\n单位米；Y向上；Z朝外；2米Bay；3米层高\n每材质族合并为一个可见网格\nAdd中编辑轮廓点；UV节点控制砖纹尺度或Palette区\n没有Python SOP；不依赖运行时Houdini Cook")
    for module_index, module in enumerate(modules):
        asset = kit.createNode("subnet", module.name)
        asset.setPosition(hou.Vector2(module_index * 5, 0))
        asset.setComment(module.description)
        asset.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        for material_index, material_name in enumerate(MATERIALS):
            parts = [part for part in module.parts if part["material"] == material_index]
            if not parts:
                continue
            geometry = asset.createNode("geo", material_name)
            geometry.setPosition(hou.Vector2(material_index * 4, 0))
            vertices = [point for part in parts for point in part["points"]]
            coordinates = [value for part in parts for value in part["uv"]]
            source = geometry.createNode("add", "EDIT_" + material_name.upper() + "_PROFILE_POINTS")
            source.parm("points").set(len(vertices))
            source.parm("prims").set(len(parts))
            for point_index, point in enumerate(vertices):
                source.parmTuple("pt" + str(point_index)).set(point)
            offset = 0
            for face_index, part in enumerate(parts):
                indices = list(range(offset, offset + len(part["points"])))
                source.parm("prim" + str(face_index)).set(" ".join(str(index) for index in reversed(indices)))
                source.parm("closed" + str(face_index)).set(1)
                offset += len(indices)
            source.setComment("原生多边形轮廓点；每个面独立点，保持硬边与UV边界。\n" + "\n".join(part["name"] for part in parts))
            source.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            mapping = geometry.createNode("attribwrangle", "EDIT_TEXTURE_COORDINATES")
            mapping.setInput(0, source)
            mapping.parm("class").set(2)
            values_u = ",".join(format(value[0], ".8f") for value in coordinates)
            values_v = ",".join(format(value[1], ".8f") for value in coordinates)
            mapping.parm("snippet").set("float values_u[]={" + values_u + "};\nfloat values_v[]={" + values_v + "};\nv@uv=set(values_u[@ptnum],values_v[@ptnum],0);")
            mapping.setComment("Brick每米重复1次；Trim采样六格Palette中心；Glass按立面归一化。")
            normals = geometry.createNode("normal", "HARD_SURFACE_NORMALS")
            normals.setInput(0, mapping)
            normals.parm("cuspangle").set(30)
            out = geometry.createNode("null", "OUT_FBX")
            out.setInput(0, normals)
            out.setDisplayFlag(True)
            out.setRenderFlag(True)
            out.cook(force=True)
            if out.errors() or out.warnings():
                raise RuntimeError(str((out.path(), out.errors(), out.warnings())))
            geometry.layoutChildren()
        asset.layoutChildren()
        exporter = hou.node("/out").createNode("filmboxfbx", "EXPORT_" + module.name)
        exporter.setParms({"startnode": asset.path(), "sopoutput": str(output / (module.name + ".fbx"))})
        exporter.render()
    kit.layoutChildren()
    root.saveItemsToFile([kit], str(output / "ReferenceKit_Source.cpio"))


def validate(data):
    for module in data:
        if module["triangle_count"] > 1000:
            raise ValueError("Geometry budget exceeded: " + module["name"])
        for group in module["material_groups"]:
            if not (len(group["vertices"]) == len(group["normals"]) == len(group["uv"])):
                raise ValueError("Attribute size mismatch")
            for start in range(0, len(group["triangles"]), 3):
                indices = group["triangles"][start:start + 3]
                positions = [group["vertices"][index] for index in indices]
                computed = normal(positions)
                expected = group["normals"][indices[0]]
                if sum(computed[axis] * expected[axis] for axis in range(3)) < .99:
                    raise ValueError("Inconsistent winding: " + module["name"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--geometry-only", action="store_true", help="Validate/export JSON without importing Houdini")
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    project = Path(__file__).resolve().parents[2]
    if output == project / "Assets" or project / "Assets" in output.parents:
        raise ValueError("Output must be a staging directory outside production Assets")
    output.mkdir(parents=True, exist_ok=True)
    modules = [brick_wall(), window_wall(), window_wall(paired=True), window_wall(arched=False),
               commercial(), commercial(door=True), column(), column(upper=True), floor_band()]
    data = [module.data() for module in modules]
    validate(data)
    palette = [{**entry, "u": (index + .5) / len(PALETTE), "v": .5}
               for index, entry in enumerate(PALETTE)]
    specification = {"marker": SOURCE_MARKER, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "coordinates": "Unity +Y up, +Z outward; conventional counterclockwise triangles; identity root",
                     "brick_uv_meters_per_repeat": 1, "palette": palette, "modules": data}
    if not arguments.geometry_only:
        import hou
        create_native_source(hou, modules, output)
    (output / "spec.json").write_text(json.dumps(specification, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output), "native_source": not arguments.geometry_only,
                      "modules": [{"name": entry["name"], "triangles": entry["triangle_count"],
                                   "material_groups": len(entry["material_groups"])} for entry in data]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
