"""Promote only the approved reference attachment interface from Live.

Shared by disposable candidate and production persistence; generator values
remain on instances and never come from a material catalog.
"""

ORIGINAL_FIELDS = (
    'roof_props_layout_mode', 'water_tower_count', 'chimney_count',
    'fire_escape_layout_mode', 'fire_escape_group_count', 'fire_escape_face_mask',
    'fire_escape_floor_start', 'fire_escape_floor_end', 'fire_escape_roof_access',
    'drainpipe_enabled', 'drainpipe_count', 'drainpipe_face_mask',
)
ROOF_PLACEMENT_FIELDS = (
    'water_tower_count_mode', 'water_tower_count_min', 'water_tower_count_max',
    'chimney_count_mode', 'chimney_count_min', 'chimney_count_max',
    'roof_prop_position_mode',
)
FIELDS = ORIGINAL_FIELDS + ROOF_PLACEMENT_FIELDS
LEGACY_FIELDS = ('roof_props_density', 'roof_props_max_count',
                 'fire_escape_density', 'fire_escape_max_count', 'attachment_global_density')
MODE_FIELDS = ('roof_props_layout_mode', 'fire_escape_layout_mode',
               'water_tower_count_mode', 'chimney_count_mode', 'roof_prop_position_mode')
TOGGLE_FIELDS = ('fire_escape_roof_access', 'drainpipe_enabled')
EXPECTED_TYPES = {name: ('Menu' if name in MODE_FIELDS else
                         'Toggle' if name in TOGGLE_FIELDS else 'Int')
                  for name in FIELDS}
FOLDER = 'sb_reference_attachments'


def _kind(template):
    kind = template.type()
    return kind.name() if callable(getattr(kind, 'name', None)) else str(kind).rsplit('.', 1)[-1]


def _reference_folder(templates, allowed_names=(FOLDER,), fields=None):
    fields = FIELDS if fields is None else fields
    def walk(entries):
        for template in entries:
            yield template
            if hasattr(template, 'parmTemplates'):
                yield from walk(template.parmTemplates())

    entries = tuple(walk(templates.entries()))
    folders = [entry for entry in entries if entry.name().startswith(FOLDER)]
    if len(folders) != 1 or folders[0].name() not in allowed_names or _kind(folders[0]) != 'Folder':
        raise RuntimeError('Reference attachment folder is missing, duplicated or unexpected')
    folder = folders[0]
    if tuple(field.name() for field in folder.parmTemplates()) != fields:
        raise RuntimeError('Reference attachment folder contents changed')
    for name in fields:
        if sum(entry.name() == name for entry in entries) != 1:
            raise RuntimeError('Reference attachment field is missing or duplicated: ' + name)
    return folder


def validate_reference_templates(templates):
    """Reject Houdini's hidden Float spare placeholders before definition writes.

    Uses the template's public enum interface, so the guard is also testable
    outside Houdini without importing a migration or depending on its recipe.
    Conditional HideWhen rules are allowed; a static hidden flag is not.
    """
    _reference_folder(templates)
    _validate_reference_fields(templates)


def _validate_reference_fields(templates, fields=None):
    for name in FIELDS if fields is None else fields:
        expected = EXPECTED_TYPES[name]
        template = templates.find(name)
        if template is None:
            raise RuntimeError('Reference attachment field is missing: ' + name)
        actual = _kind(template)
        if actual != expected:
            raise RuntimeError('Reference attachment field {} must be {}, got {}'.format(name, expected, actual))
        if template.isHidden():
            raise RuntimeError('Reference attachment field is statically hidden: ' + name)


def canonical_live_templates(asset):
    """Project only the diagnosed internal switcher identity, without mutation.

    HOM uses an instance-only spare switcher for an edited native folder. The
    Houdini 21.0 SDK calls ``sidefx::switcher`` its original pre-rename name.
    Renaming that switcher on the node creates the alias again, so compare and
    promote a detached template copy instead. All pre-existing parent folders
    and every control remain untouched; no arbitrary numeric suffix is accepted.
    """
    group = asset.parmTemplateGroup()
    folder = _reference_folder(group, (FOLDER, FOLDER + '2'))
    _validate_reference_fields(group)
    if folder.name() == FOLDER:
        return group

    if folder.tags() != {'group_type': 'simple', 'sidefx::switcher': FOLDER}:
        raise RuntimeError('Reference attachment switcher alias has unexpected tags')
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError('Reference attachment switcher alias has no native definition')
    native = definition.parmTemplateGroup()
    native_folder = native.find(FOLDER)
    native_names = tuple(field.name() for field in native_folder.parmTemplates()) if native_folder else ()
    # During save=False development the captured native definition still has
    # the original 12 controls. Only the seven explicitly approved roof fields
    # may be added as typed Live spare controls until cumulative verification
    # permits definition promotion. Partial/unknown native schemas still fail.
    native_fields = ORIGINAL_FIELDS if native_names == ORIGINAL_FIELDS else FIELDS
    _reference_folder(native, fields=native_fields)
    _validate_reference_fields(native, native_fields)
    if native.find(FOLDER).tags() != {'group_type': 'simple'}:
        raise RuntimeError('Reference attachment native folder has unexpected tags')
    for name in FIELDS:
        parm = asset.parm(name)
        pending_roof_field = name in ROOF_PLACEMENT_FIELDS and native.find(name) is None
        if parm is None or (parm.isSpare() and not pending_roof_field):
            raise RuntimeError('Reference attachment alias field is not native: ' + name)

    before = {parm.name(): parm.rawValue() for parm in asset.parms()}
    old_name = folder.name()
    folder.setName(FOLDER)
    folder.setTags({'group_type': 'simple'})
    group.replace(old_name, folder)
    validate_reference_templates(group)
    if {parm.name(): parm.rawValue() for parm in asset.parms()} != before:
        raise RuntimeError('Reference attachment identity projection changed instance raw values')
    return group


def promote(templates, asset):
    """Return a copied group with approved fields, preserving canonical folders."""
    result = templates
    live = canonical_live_templates(asset)
    # A definition rollback can leave referenced spare controls as invisible
    # Float placeholders. Never promote those as the approved integer API.
    validate_reference_templates(live)
    group = live.find('sb_reference_attachments')
    if result.find('sb_reference_attachments') is None:
        # The existing panel compiler rebuilds its known groups and parks
        # unknown definition-owned fields in hidden compatibility data. On a
        # second promotion these approved controls already exist there. Move
        # only these exact names into their verified group, never duplicate
        # them or remove unrelated compatibility fields/parent folders.
        for name in FIELDS:
            if result.find(name) is not None:
                result.remove(name)
        # Removal invalidates HOM layout placeholders; find the host afterward.
        host = result.findFolder(('附件 / Attachments',))
        if host is None:
            host = next((t for t in result.entries() if hasattr(t, 'parmTemplates')
                         and any(x.name() == 'attachments_enabled' for x in t.parmTemplates())), None)
        if host is None:
            raise RuntimeError('Canonical attachment folder is missing')
        result.appendToFolder(host, group)
    else:
        result.replace('sb_reference_attachments', group)
    for name in LEGACY_FIELDS:
        source = live.find(name)
        if source is None or result.find(name) is None:
            raise RuntimeError('Required legacy attachment interface missing: ' + name)
        result.replace(name, source)
    for name in FIELDS:
        if result.find(name) is None:
            raise RuntimeError('Approved attachment field not promoted: ' + name)
    validate_reference_templates(result)
    return result
