"""The interface promotion must be shared by candidate and persist paths."""
import pathlib
import copy
import importlib.util
import sys
import types
import unittest
from unittest import mock


TOOLS = pathlib.Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('reference_attachment_interface_under_test',
                                            TOOLS / 'streetbuilding_attachment_interface.py')
INTERFACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTERFACE)


class EnumValue:
    def __init__(self, value):
        self.value = value

    def name(self):
        return self.value


class Template:
    def __init__(self, name, kind='Int', hidden=False, children=(), label=None, tags=None):
        self._name, self.kind, self.hidden = name, kind, hidden
        self.children, self._label = list(children), label or name
        self._tags = dict(tags or ({'group_type': 'simple'} if name == INTERFACE.FOLDER else {}))

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name

    def type(self):
        return EnumValue(self.kind)

    def label(self):
        return self._label

    def tags(self):
        return dict(self._tags)

    def setTags(self, tags):
        self._tags = dict(tags)

    def isHidden(self):
        return self.hidden

    def parmTemplates(self):
        return tuple(self.children)


class Group:
    def __init__(self, entries):
        self.items = list(entries)

    def entries(self):
        # HOM returns detached ParmTemplate copies; mutation requires replace.
        return tuple(copy.deepcopy(self.items))

    def parmTemplates(self):
        return self.entries()

    def _walk(self, entries=None):
        for entry in self.items if entries is None else entries:
            yield entry
            yield from self._walk(entry.children)

    def find(self, name):
        return next((entry for entry in self._walk() if entry.name() == name), None)

    def findFolder(self, labels):
        # Deliberately miss the English label path, exercising promotion's
        # existing attachments_enabled fallback without renaming the folder.
        return None

    def appendToFolder(self, folder, template):
        self.find(folder.name()).children.append(copy.deepcopy(template))

    def replace(self, name, template):
        def replace_in(entries):
            for index, entry in enumerate(entries):
                if entry.name() == name:
                    entries[index] = copy.deepcopy(template)
                    return True
                if replace_in(entry.children):
                    return True
            return False
        if not replace_in(self.items):
            raise KeyError(name)

    def remove(self, name):
        def remove_in(entries):
            for index, entry in enumerate(entries):
                if entry.name() == name:
                    del entries[index]
                    return True
                if remove_in(entry.children):
                    return True
            return False
        if not remove_in(self.items):
            raise KeyError(name)


class Definition:
    def __init__(self, templates):
        self.templates = templates

    def parmTemplateGroup(self):
        return copy.deepcopy(self.templates)


class NodeType:
    def __init__(self, definition):
        self._definition = definition

    def name(self):
        return 'pcgbike::StreetBuilding::1.0'

    def definition(self):
        return self._definition


class Asset:
    def __init__(self, templates, parameters=(), definition=None):
        self.templates = templates
        self.parameters = {parm.name(): parm for parm in parameters}
        self.set_count, self.definition = 0, definition

    def parmTemplateGroup(self):
        return copy.deepcopy(self.templates)

    def setParmTemplateGroup(self, templates):
        self.set_count += 1
        raise AssertionError('Pure identity projection cannot modify a node')

    def type(self):
        return NodeType(self.definition)

    def parms(self):
        return tuple(self.parameters.values())

    def parm(self, name):
        return self.parameters.get(name)


class Parm:
    def __init__(self, name, raw, kind='Int', keys=(), spare=False):
        self._name, self.raw, self.kind, self.keys = name, raw, kind, keys
        self.spare = spare

    def name(self):
        return self._name

    def rawValue(self):
        return self.raw

    def isSpare(self):
        return self.spare

    def parmTemplate(self):
        return Template(self._name, self.kind)

    def keyframes(self):
        return self.keys

    def eval(self):
        raise AssertionError('Capture identity projection cannot evaluate parameters')

    def set(self, value):
        self.raw = value

    def deleteAllKeyframes(self):
        self.keys = ()

    def setKeyframes(self, keys):
        self.keys, self.raw = keys, keys[0]


def fixture():
    def legacy():
        return [Template('attachments_enabled', 'Toggle')] + [
            Template(name, 'Float' if 'density' in name else 'Int')
            for name in INTERFACE.LEGACY_FIELDS]
    controls = [Template(name, kind) for name, kind in INTERFACE.EXPECTED_TYPES.items()]
    reference = Template('sb_reference_attachments', 'Folder', children=controls)
    target = Group([Template('canonical_attachments', 'Folder', children=legacy())])
    live = Group([Template('synthesized_attachments2', 'Folder', children=legacy() + [reference])])
    return target, live


class AttachmentInterfaceTests(unittest.TestCase):
    def test_shared_promotion_is_used_for_candidate_and_persistence(self):
        tools = pathlib.Path(__file__).resolve().parents[1] / 'tools'
        for filename in ('pcg_regression_gate.py', 'validate_streetbuilding_contract.py'):
            source = (tools / filename).read_text(encoding='utf-8')
            self.assertIn('streetbuilding_attachment_interface import promote', source)
            self.assertRegex(source, r'promote_attachments\((?:promoted_)?templates, asset\)')

    def test_valid_typed_controls_preserve_the_canonical_folder(self):
        target, live = fixture()
        result = INTERFACE.promote(target, Asset(live))
        self.assertEqual([entry.name() for entry in result.entries()], ['canonical_attachments'])
        self.assertIsNotNone(result.find('sb_reference_attachments'))
        for name, expected in INTERFACE.EXPECTED_TYPES.items():
            self.assertEqual(result.find(name).type().name(), expected)
            self.assertFalse(result.find(name).isHidden())
        for name in INTERFACE.LEGACY_FIELDS:
            self.assertEqual(result.find(name).type().name(), live.find(name).type().name())

    def test_float_spare_placeholders_are_rejected_before_promotion(self):
        for name in INTERFACE.FIELDS:
            with self.subTest(field=name):
                target, live = fixture()
                live.find(name).kind = 'Float'
                live.find(name).hidden = True
                with self.assertRaisesRegex(RuntimeError, name + r' must be .*got Float'):
                    INTERFACE.promote(target, Asset(live))
                self.assertIsNone(target.find('sb_reference_attachments'))
                self.assertEqual([entry.name() for entry in target.entries()], ['canonical_attachments'])

    def test_static_hidden_flag_is_rejected_for_every_approved_control(self):
        for name in INTERFACE.FIELDS:
            with self.subTest(field=name):
                target, live = fixture()
                live.find(name).hidden = True
                with self.assertRaisesRegex(RuntimeError, 'statically hidden: ' + name):
                    INTERFACE.promote(target, Asset(live))
                self.assertIsNone(target.find('sb_reference_attachments'))

    @staticmethod
    def suffixed_asset():
        _, live = fixture()
        # Preserve an unrelated pre-existing spare child switcher verbatim.
        live.items[0].children.insert(0, Template('sb_attachments_roof_props2', 'Folder',
            children=(Template('legacy_roof_option'),), tags={'sidefx::switcher': 'sb_attachments_roof_props'}))
        native = copy.deepcopy(live)
        live.find(INTERFACE.FOLDER).setName(INTERFACE.FOLDER + '2')
        live.find(INTERFACE.FOLDER + '2').setTags({'group_type': 'simple', 'sidefx::switcher': INTERFACE.FOLDER})
        parameters = [Parm(name, index) for index, name in enumerate(INTERFACE.FIELDS)]
        parameters += [Parm('layout_seed', 137), Parm('output_path', '$HIP/native.bgeo', 'String'),
                       Parm('building_width', 'ch("../width")', 'Float', ('ch("../width")',))]
        return Asset(live, parameters, Definition(native))

    def test_persistence_validates_definition_and_pure_projection_before_hip_save(self):
        source = (TOOLS / 'pcg_regression_gate.py').read_text(encoding='utf-8')
        check = source.index('validate_reference_templates(definition.parmTemplateGroup())')
        projection = source.index('validate_reference_templates(canonical_live_templates(asset))', check)
        self.assertLess(check, projection)
        self.assertLess(projection, source.index('hou.hipFile.save()', projection))
        self.assertNotIn('normalize_live_folder', source)

    def test_live_alias_projection_preserves_all_raw_values_channels_and_legacy_folders(self):
        asset = self.suffixed_asset()
        before = {parm.name(): parm.rawValue() for parm in asset.parms()}
        names = [entry.name() for entry in asset.templates._walk()]
        result = INTERFACE.canonical_live_templates(asset)
        INTERFACE.validate_reference_templates(result)
        self.assertEqual(before, {parm.name(): parm.rawValue() for parm in asset.parms()})
        self.assertEqual(asset.parm('building_width').keyframes(), ('ch("../width")',))
        self.assertEqual(asset.set_count, 0)
        self.assertEqual([entry.name() for entry in asset.templates._walk()], names)
        self.assertIsNotNone(asset.templates.find(INTERFACE.FOLDER + '2'))
        self.assertIsNone(result.find(INTERFACE.FOLDER + '2'))
        self.assertEqual(result.find(INTERFACE.FOLDER).tags(), {'group_type': 'simple'})
        self.assertEqual(result.find('sb_attachments_roof_props2').tags(),
                         {'sidefx::switcher': 'sb_attachments_roof_props'})
        self.assertEqual([entry.name() for entry in asset.templates.entries()], ['synthesized_attachments2'])

    def test_pure_projection_is_idempotent_but_still_validates_types(self):
        asset = self.suffixed_asset()
        projected = INTERFACE.canonical_live_templates(asset)
        projected_asset = Asset(projected, asset.parms(), asset.definition)
        twice = INTERFACE.canonical_live_templates(projected_asset)
        self.assertEqual([entry.name() for entry in projected._walk()], [entry.name() for entry in twice._walk()])
        self.assertEqual(asset.set_count, 0)
        asset.templates.find('water_tower_count').kind = 'Float'
        with self.assertRaisesRegex(RuntimeError, 'water_tower_count must be Int'):
            INTERFACE.canonical_live_templates(asset)
        self.assertEqual(asset.set_count, 0)

    def test_approved_roof_extension_can_promote_from_exact_original_native_schema(self):
        asset = self.suffixed_asset()
        native = asset.definition.templates.find(INTERFACE.FOLDER)
        native.children = native.children[:len(INTERFACE.ORIGINAL_FIELDS)]
        before = {parm.name(): parm.rawValue() for parm in asset.parms()}
        for name in INTERFACE.ROOF_PLACEMENT_FIELDS:
            asset.parm(name).spare = True
        result = INTERFACE.canonical_live_templates(asset)
        INTERFACE.validate_reference_templates(result)
        self.assertEqual(before, {parm.name(): parm.rawValue() for parm in asset.parms()})
        self.assertEqual(asset.set_count, 0)
        # The extension exception cannot turn an old native field into a spare.
        asset.parm('water_tower_count').spare = True
        with self.assertRaisesRegex(RuntimeError, 'field is not native: water_tower_count'):
            INTERFACE.canonical_live_templates(asset)

    def test_pending_roof_extension_still_rejects_float_placeholders(self):
        asset = self.suffixed_asset()
        native = asset.definition.templates.find(INTERFACE.FOLDER)
        native.children = native.children[:len(INTERFACE.ORIGINAL_FIELDS)]
        for name in INTERFACE.ROOF_PLACEMENT_FIELDS:
            asset.parm(name).spare = True
        asset.templates.find('roof_prop_position_mode').kind = 'Float'
        with self.assertRaisesRegex(RuntimeError, 'roof_prop_position_mode must be Menu'):
            INTERFACE.canonical_live_templates(asset)
        self.assertEqual(asset.set_count, 0)

    def test_live_projection_rejects_unapproved_structure_without_writes(self):
        for corruption in ('alias3', 'both', 'missing', 'reordered', 'float', 'hidden'):
            with self.subTest(corruption=corruption):
                asset = self.suffixed_asset()
                folder = asset.templates.find(INTERFACE.FOLDER + '2')
                if corruption == 'alias3':
                    folder.setName(INTERFACE.FOLDER + '3')
                elif corruption == 'both':
                    duplicate = copy.deepcopy(folder)
                    duplicate.setName(INTERFACE.FOLDER)
                    asset.templates.items.append(duplicate)
                elif corruption == 'missing':
                    folder.children.pop()
                elif corruption == 'reordered':
                    folder.children.reverse()
                elif corruption == 'float':
                    folder.children[0].kind = 'Float'
                else:
                    folder.children[0].hidden = True
                with self.assertRaises(RuntimeError):
                    INTERFACE.canonical_live_templates(asset)
                self.assertEqual(asset.set_count, 0)

    def test_projection_rejects_wrong_or_missing_switcher_origin_tags(self):
        for tags in ({}, {'group_type': 'simple'}, {'group_type': 'simple', 'sidefx::switcher': 'other'},
                     {'group_type': 'simple', 'sidefx::switcher': INTERFACE.FOLDER, 'extra': 'unknown'}):
            with self.subTest(tags=tags):
                asset = self.suffixed_asset()
                asset.templates.find(INTERFACE.FOLDER + '2').setTags(tags)
                with self.assertRaisesRegex(RuntimeError, 'unexpected tags'):
                    INTERFACE.canonical_live_templates(asset)
                self.assertEqual(asset.set_count, 0)

    def test_projection_rejects_every_spare_or_missing_reference_control(self):
        for name in INTERFACE.FIELDS:
            for missing in (False, True):
                with self.subTest(field=name, missing=missing):
                    asset = self.suffixed_asset()
                    if missing:
                        asset.parameters.pop(name)
                    else:
                        asset.parm(name).spare = True
                    with self.assertRaisesRegex(RuntimeError, 'field is not native: ' + name):
                        INTERFACE.canonical_live_templates(asset)
                    self.assertEqual(asset.set_count, 0)

    def test_projection_rejects_unverified_native_definition(self):
        for corruption in ('absent', 'missing', 'reordered', 'float', 'hidden', 'alias', 'extra_tag'):
            with self.subTest(corruption=corruption):
                asset = self.suffixed_asset()
                folder = asset.definition.templates.find(INTERFACE.FOLDER)
                if corruption == 'absent':
                    asset.definition = None
                elif corruption == 'missing':
                    folder.children.pop()
                elif corruption == 'reordered':
                    folder.children.reverse()
                elif corruption == 'float':
                    folder.children[0].kind = 'Float'
                elif corruption == 'hidden':
                    folder.children[0].hidden = True
                elif corruption == 'alias':
                    folder.setName(INTERFACE.FOLDER + '2')
                else:
                    folder.setTags({'group_type': 'simple', 'extra': 'unknown'})
                with self.assertRaises(RuntimeError):
                    INTERFACE.canonical_live_templates(asset)
                self.assertEqual(asset.set_count, 0)

    def test_alias_projection_is_shared_by_promotion_without_changing_canonical_host(self):
        target, _ = fixture()
        asset = self.suffixed_asset()
        result = INTERFACE.promote(target, asset)
        INTERFACE.validate_reference_templates(result)
        self.assertEqual([entry.name() for entry in result.entries()], ['canonical_attachments'])
        self.assertEqual(asset.set_count, 0)

    def test_rebuilt_hidden_fallback_controls_are_moved_once_and_promotion_is_idempotent(self):
        target, _ = fixture()
        legacy = Template('old_style_compat_rule', 'String', hidden=True, tags={'legacy': 'keep'})
        fallback = [Template(name, kind, hidden=True) for name, kind in INTERFACE.EXPECTED_TYPES.items()]
        target.items.append(Template('sb_internal', 'Folder', hidden=True,
                                     children=[legacy] + fallback, tags={'legacy-parent': 'keep'}))
        asset = self.suffixed_asset()
        before_values = {parm.name(): parm.rawValue() for parm in asset.parms()}
        result = INTERFACE.promote(target, asset)
        INTERFACE.validate_reference_templates(result)
        self.assertEqual([entry.name() for entry in result.entries()], ['canonical_attachments', 'sb_internal'])
        internal = result.find('sb_internal')
        self.assertTrue(internal.isHidden())
        self.assertEqual(internal.tags(), {'legacy-parent': 'keep'})
        self.assertEqual([entry.name() for entry in internal.parmTemplates()], ['old_style_compat_rule'])
        self.assertEqual(result.find('old_style_compat_rule').tags(), {'legacy': 'keep'})
        self.assertTrue(result.find('old_style_compat_rule').isHidden())
        for name, kind in INTERFACE.EXPECTED_TYPES.items():
            self.assertEqual(sum(entry.name() == name for entry in result._walk()), 1)
            self.assertEqual(result.find(name).type().name(), kind)
            self.assertFalse(result.find(name).isHidden())
        layout = lambda group: [(entry.name(), entry.type().name(), entry.isHidden(), entry.tags())
                                for entry in group._walk()]
        before_layout = layout(result)
        twice = INTERFACE.promote(result, asset)
        self.assertEqual(layout(twice), before_layout)
        self.assertEqual(before_values, {parm.name(): parm.rawValue() for parm in asset.parms()})
        self.assertEqual(asset.set_count, 0)

    def test_existing_reference_folder_does_not_silently_remove_other_duplicate_fields(self):
        target, _ = fixture()
        asset = self.suffixed_asset()
        result = INTERFACE.promote(target, asset)
        result.items.append(Template('sb_internal', 'Folder', hidden=True,
                                     children=[Template('water_tower_count', hidden=True)]))
        with self.assertRaisesRegex(RuntimeError, 'field is missing or duplicated: water_tower_count'):
            INTERFACE.promote(result, asset)
        self.assertIsNotNone(result.find('sb_internal').parmTemplates()[0])
        self.assertEqual(asset.set_count, 0)

    def test_remote_snapshot_projects_only_new_folder_identity(self):
        specification = importlib.util.spec_from_file_location('regression_gate_under_test', TOOLS / 'pcg_regression_gate.py')
        gate = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(gate)
        fake_hou = types.SimpleNamespace(hipFile=types.SimpleNamespace(path=lambda: str(TOOLS.parents[1] / 'probe.hip')))
        namespace = {}
        with mock.patch.dict(sys.modules, {'hou': fake_hou}):
            exec(gate.REMOTE_CAPTURE_CODE, namespace)
            asset = self.suffixed_asset()
            result = namespace['_pcg_public_interface'](asset)
        prefix = 'synthesized_attachments2/'
        self.assertIn(prefix + INTERFACE.FOLDER, result)
        self.assertNotIn(prefix + INTERFACE.FOLDER + '2', result)
        self.assertIn(prefix + 'sb_attachments_roof_props2/legacy_roof_option', result)
        self.assertEqual(result['synthesized_attachments2']['name'], 'synthesized_attachments2')
        self.assertEqual(asset.set_count, 0)


if __name__ == '__main__':
    unittest.main()
