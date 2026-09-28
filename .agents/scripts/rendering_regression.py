"""Unity-only regression transaction. Never connects to Houdini or resets Git.

Capture hashes the current working files (including untracked user assets), backs up
only the explicit whitelist and records exact existing Console messages. Restore
is explicit and only restores whitelist entries; no recursive directory deletion.
"""
import argparse, concurrent.futures, hashlib, json, pathlib, shutil, subprocess, time, uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
UNITY = shutil.which('unity')

def cli(name, **kwargs):
    args = [UNITY, 'command', name, '--caller', 'plugin', '--skill', 'unity-cli', '--json']
    for key, value in kwargs.items():
        args += ['--' + key, str(value)]
    p = subprocess.run(args, cwd=ROOT, capture_output=True, encoding='utf-8')
    data = json.loads(p.stdout)
    if p.returncode or not data.get('success'):
        raise RuntimeError(data)
    return data['data']['result']

def hashes():
    names = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    def one(name):
        path = ROOT / name
        if not name or not path.is_file(): return None
        with path.open('rb') as stream:
            return name, hashlib.file_digest(stream, 'sha256').hexdigest()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return dict(x for x in pool.map(one, set(names)) if x)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=['Capture','VerifyFast','VerifyFull','Apply','Restore'])
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / args.manifest).read_text(encoding='utf-8-sig'))
    base = ROOT / manifest['baseline']
    allowed = set(manifest['allowedFiles'])
    if args.stage == 'Apply':
        # Only persist a preset produced by a successful complete raster/compiler run.
        verdict = json.loads((base.parent / 'contracts.json').read_text(encoding='utf-8'))
        assert verdict.get('result', '').startswith('PAINTERLY_PASS'), verdict
        stamp = json.loads((base.parent / 'verified-hashes.json').read_text(encoding='utf-8'))
        assert hashes() == stamp, 'Working files changed since VerifyFull; validate again before Apply'
        expected = {}
        try:
            for label, path in manifest.get('applyMaterials', dict(zip(['sphere','crocodile'], manifest['materials']))).items():
                preset = json.loads((base.parent / (label + '-preset.json')).read_text(encoding='utf-8'))
                result = cli('set_material_properties', material=path, properties=json.dumps(preset),
                             disableKeywords=json.dumps(['_PROTECTINTERIOR_ON','_EDGEBANDENABLED_ON']))
                assert not result.get('unknown'), result
                expected[path] = preset
            (base.parent / 'applied.json').write_text(json.dumps(expected), encoding='utf-8')
            subprocess.run([shutil.which('python'), str(pathlib.Path(__file__).resolve()), '--stage', 'VerifyFull', '--manifest', args.manifest], cwd=ROOT, check=True)
        except BaseException:
            # Only task asset files are restored, preserving pre-existing user changes.
            for name in allowed:
                if not name.startswith('Assets/'): continue
                saved, dest = base / 'files' / name, ROOT / name
                if saved.exists(): shutil.copy2(saved, dest)
                elif dest.is_file(): dest.unlink()
            (base.parent / 'applied.json').unlink(missing_ok=True)
            cli('eval', code='UnityEditor.AssetDatabase.Refresh(); return "Capture assets restored";')
            raise
        print('PASS Rendering Apply + post-save VerifyFull')
        return
    if args.stage == 'Capture':
        if (base / 'snapshot.json').exists(): raise RuntimeError('Baseline already exists; do not overwrite it.')
        scenes = cli('list_open_scenes')['scenes']
        assert any(s['path'] == manifest['scene'] and not s['isDirty'] for s in scenes), 'Save/preserve existing scene first'
        base.mkdir(parents=True, exist_ok=True)
        for name in allowed:
            path = ROOT / name
            if path.is_file():
                dest = base / 'files' / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        snapshot = dict(hashes=hashes(), scenes=scenes, console=cli('console', tail=2000, level='warn'),
                        materials={p:cli('get_material_properties', material=p) for p in manifest['materials']})
        (base / 'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        snapshot = json.loads((base / 'snapshot.json').read_text(encoding='utf-8'))
        if args.stage == 'Restore':
            for name in allowed:
                saved, dest = base / 'files' / name, ROOT / name
                if saved.exists(): shutil.copy2(saved, dest)
                elif dest.is_file(): dest.unlink()
            print('Restored only whitelist files from Capture. Reimport before continuing.')
            return
        current = hashes()
        changed = {p for p in current.keys() | snapshot['hashes'].keys() if current.get(p) != snapshot['hashes'].get(p)}
        unexpected = changed - allowed
        assert not unexpected, 'Outside whitelist: ' + repr(sorted(unexpected))
        if args.stage == 'VerifyFull':
            applied = base.parent / 'applied.json'
            if applied.exists():
                for path, expected in json.loads(applied.read_text(encoding='utf-8')).items():
                    actual = {p['name']:p['value'] for p in cli('get_material_properties', material=path)['properties']}
                    for key, value in expected.items():
                        aa = actual[key] if isinstance(value,list) else [actual[key]]
                        bb = value if isinstance(value,list) else [value]
                        assert len(aa)==len(bb) and all(abs(a-b)<1e-5 for a,b in zip(aa,bb)), (path,key,aa,bb)
            # Pipeline's synchronous main-thread dispatcher has a 5 s deadline.
            # Schedule the full raster suite once, then await its unique completion file.
            done = base.parent / ('run-' + uuid.uuid4().hex + '.txt')
            code = (ROOT / '.agents/scripts/painterly_render_tests.cs').read_text(encoding='utf-8')
            code = code.replace('__PAINTERLY_OUTPUT__', base.parent.as_posix())
            started = cli('console', tail=1, level='warn')
            wrapped = ('UnityEditor.EditorApplication.CallbackFunction tick=null; tick=()=> { UnityEditor.EditorApplication.update-=tick; try { '
                       'System.Func<string> run = () => {' + code + '}; '
                       'System.IO.File.WriteAllText(' + json.dumps(str(done)) + ',run());'
                       '} catch(System.Exception e) { System.IO.File.WriteAllText('
                       + json.dumps(str(done)) + ',"ERROR " + e.ToString()); }}; UnityEditor.EditorApplication.update+=tick; return "scheduled";')
            ack = cli('eval', code=wrapped, timeout=60000)
            assert ack.get('success'), ack
            deadline = time.monotonic() + 180
            while not done.exists() and time.monotonic() < deadline: time.sleep(.5)
            assert done.exists(), 'Raster test timed out; inspect Editor before retrying'
            result = dict(success=True, result=done.read_text(encoding='utf-8-sig'))
            (base.parent / 'contracts.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            assert result.get('success') and 'PAINTERLY_PASS' in str(result.get('result')), result
            before = {e['message'] for e in snapshot['console']['entries']}
            now = cli('console', tail=2000, level='warn', since=started['cursor'], since_session=started['session'])
            extra = {e['message'] for e in now['entries']} - before
            assert not extra, 'New Console diagnostics: ' + repr(extra)
            for path, old in snapshot['materials'].items():
                new = cli('get_material_properties', material=path)
                assert new['shader'] == old['shader'], 'Shader reference changed'
                old_props = {p['name']:p['value'] for p in old['properties']}
                new_props = {p['name']:p['value'] for p in new['properties']}
                assert new_props.get('_BaseMap') == old_props.get('_BaseMap'), 'Captured base texture changed'
                (base.parent / (pathlib.Path(path).stem + '.json')).write_text(json.dumps(new, indent=2), encoding='utf-8')
            (base.parent / 'verified-hashes.json').write_text(json.dumps(hashes()), encoding='utf-8')
    print('PASS Rendering ' + args.stage)

if __name__ == '__main__': main()
