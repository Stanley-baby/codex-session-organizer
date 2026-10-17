import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_manifest_and_resources_resolve(self):
        manifest = json.loads((ROOT / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['name'], 'codex-session-organizer')
        self.assertEqual(manifest['license'], 'MIT')
        for resource in (manifest['skills'], manifest['hooks'],
                         manifest['extensions']['com.openai']['onboardingSkill']):
            path = (ROOT / resource).resolve()
            self.assertIn(ROOT, path.parents)
            self.assertTrue(path.exists())
        # shortcut: tested client skips hooks with a root portable manifest; retest before switching formats.
        self.assertFalse((ROOT / 'plugin.json').exists())

    def test_marketplace_and_hooks_contract(self):
        market = json.loads((ROOT / '.agents/plugins/marketplace.json').read_text())
        self.assertEqual(market['name'], 'codex-session-organizer')
        self.assertEqual(market['plugins'][0]['source']['path'], './')
        hooks = json.loads((ROOT / 'hooks/hooks.json').read_text())['hooks']
        self.assertEqual(set(hooks), {'UserPromptSubmit', 'PostToolUse'})
        self.assertIn('create_sidebar_section', hooks['PostToolUse'][0]['matcher'])
        for event in hooks.values():
            self.assertEqual(event[0]['hooks'][0]['command'], 'sh "${PLUGIN_ROOT}/hooks/run.sh"')


if __name__ == '__main__':
    unittest.main()
