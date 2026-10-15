import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
MANAGE = REPO / 'scripts/manage.py'
HOOK = REPO / 'scripts/session_organizer.py'
SID = '01a3185c-5000-7000-8000-000000000001'  # Synthetic UUIDv7, 2027 timestamp.


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='organizer test ')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / 'state/codex-session-organizer'
        self.env = dict(os.environ, CODEX_HOME=str(self.home))
        self.config = {'sections': [{'name': '开发工具', 'id': 'sample-dev', 'description': '软件与插件'}]}

    def manage(self, *args, config=None, ok=True):
        result = subprocess.run([sys.executable, str(MANAGE), *args], env=self.env,
                                input=json.dumps(config or self.config), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return result

    def settings(self):
        return json.loads((self.root / 'settings.json').read_text())

    def hook(self, value):
        result = subprocess.run(['sh', str(REPO / 'hooks/run.sh')], env=self.env,
                                input=json.dumps(value), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_no_setup_is_inert(self):
        self.assertEqual(self.hook({'session_id': SID, 'hook_event_name': 'UserPromptSubmit'}), '')
        self.assertFalse(self.root.exists())

    def test_init_private_and_no_config_write(self):
        self.manage('init')
        settings = self.settings()
        self.assertEqual(settings['sections'], {'开发工具': 'sample-dev'})
        self.assertTrue(settings['enabled'])
        self.assertEqual((self.root / 'settings.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.home / 'config.toml').exists())

    def test_reinitialize_preserves_cutoff_and_state(self):
        self.manage('init')
        cutoff = self.settings()['installed_at_ms']
        state = self.root / (SID + '.json')
        state.write_text('{"title_done": true}')
        self.manage('pause')
        self.config['sections'][0]['id'] = 'sample-other'
        self.manage('init')
        self.assertEqual(self.settings()['installed_at_ms'], cutoff)
        self.assertFalse(self.settings()['enabled'])
        self.assertTrue(json.loads(state.read_text())['title_done'])

    def test_pause_and_resume_keep_state(self):
        self.manage('init')
        value = {'session_id': SID, 'turn_id': 'sample-turn', 'hook_event_name': 'UserPromptSubmit'}
        self.assertIn('additionalContext', self.hook(value))
        before = (self.root / (SID + '.json')).read_bytes()
        self.manage('pause')
        self.assertEqual(self.hook(value), '')
        self.assertEqual(before, (self.root / (SID + '.json')).read_bytes())
        self.manage('resume')
        self.assertIn('additionalContext', self.hook(value))

    def test_legacy_conflict_leaves_config_intact(self):
        path = self.home / 'config.toml'
        path.write_text('# BEGIN codex-session-organizer v1\n')
        before = path.read_bytes()
        self.manage('init', ok=False)
        self.assertFalse(self.root.exists())
        self.assertEqual(before, path.read_bytes())

    def test_invalid_mapping_leaves_existing_settings_intact(self):
        self.manage('init')
        before = (self.root / 'settings.json').read_bytes()
        for rows in ([], [{'name': 'x'}], [1], self.config['sections'] * 2,
                     [{'name': 'x', 'id': 'pinned', 'description': 'x'}],
                     [{'name': 'x\ny', 'id': 'sample', 'description': 'x'}]):
            self.manage('init', config={'sections': rows}, ok=False)
            self.assertEqual(before, (self.root / 'settings.json').read_bytes())

    def test_doctor_not_initialized_fails(self):
        result = json.loads(self.manage('doctor', ok=False).stdout)
        self.assertFalse(result['checks']['initialized'])
        self.assertIn('runtime_checks', result)

    def test_custom_section_description_in_guidance(self):
        self.manage('init')
        out = self.hook({'session_id': SID, 'hook_event_name': 'UserPromptSubmit'})
        self.assertIn('软件与插件', out)
        self.assertNotIn('公司=', out)

    def test_paths_with_spaces_and_plugin_copy(self):
        copy = self.home / 'plugin copy'
        shutil.copytree(REPO / 'scripts', copy / 'scripts')
        shutil.copytree(REPO / 'hooks', copy / 'hooks')
        self.manage('init')
        result = subprocess.run(['sh', str(copy / 'hooks/run.sh')], input=json.dumps({
            'session_id': SID, 'hook_event_name': 'UserPromptSubmit'}), env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('additionalContext', result.stdout)

    def test_non_object_hook_input_ignored(self):
        self.manage('init')
        for value in (None, [], 'string', 1):
            self.assertEqual(self.hook(value), '')


if __name__ == '__main__':
    unittest.main()
