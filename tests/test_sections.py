import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from test_session_organizer import HookFixture, SCRIPT, SID, OTHER


class SectionTests(HookFixture):
    def setUp(self):
        super().setUp()
        self.settings['auto_create_sections'] = True
        self.write_settings()

    def live(self, rows=(), section=None, **thread_fields):
        thread = {'id': SID, 'kind': 'codex', 'title': '默认标题', **thread_fields}
        sections = [{'sectionId': i, 'name': n, 'itemKeys': (
            ['codex:thread:local:' + SID] if i == section else [])} for i, n in rows]
        self.tool('list_threads', response={'threads': [thread], 'sections': sections})

    def prepare(self, name='旅行生活', description='旅行计划与日常生活', ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), '--prepare-section', SID, name, description],
                                env={**os.environ, 'CODEX_HOME': str(self.home)}, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return json.loads(result.stdout) if ok else None

    def saved(self):
        return json.loads((self.root / 'settings.json').read_text())

    def stage(self):
        self.call(); self.live([('dev', '开发工具')]); self.prepare()

    def test_create_register_move_needs_both_native_readbacks(self):
        self.stage()
        self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.assertNotIn('旅行生活', self.saved()['sections'])
        self.live([('dev', '开发工具'), ('travel', '旅行生活')])
        self.assertEqual(self.saved()['sections']['旅行生活'], 'travel')
        self.assertEqual(self.saved()['section_descriptions']['旅行生活'], '旅行计划与日常生活')
        self.assertFalse(self.state().get('section_done'))
        self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'travel'})
        self.assertFalse(self.state().get('section_done'))
        self.live([('travel', '旅行生活')], section='travel')
        self.assertEqual(self.state()['managed_section'], 'travel')
        self.assertNotIn('pending_section', self.state())

    def test_existing_unconfigured_group_reused_without_create(self):
        self.call(); self.live([('travel', '旅行生活')])
        self.assertEqual(self.prepare()['action'], 'reuse')
        self.assertNotIn('旅行生活', self.saved()['sections'])
        self.live([('travel', '旅行生活')])
        self.assertEqual(self.saved()['sections']['旅行生活'], 'travel')

    def test_failed_or_unprepared_create_not_registered(self):
        for response in ({'isError': True}, 'not JSON'):
            self.call(turn=str(response)); self.live(); self.prepare()
            self.tool('create_sidebar_section', {'name': '旅行生活'}, response)
            self.live([('travel', '旅行生活')])
            self.assertNotIn('旅行生活', self.saved()['sections'])
        self.call(turn='unprepared'); self.live()
        self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.live([('travel', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_wrong_name_turn_and_missing_readback_do_not_register(self):
        self.stage()
        self.tool('create_sidebar_section', {'name': '错误名称'})
        self.tool('create_sidebar_section', {'name': '旅行生活'}, turn='wrong-turn')
        self.live([('travel', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])
        self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_duplicate_native_names_do_not_register_or_merge(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.live([('a', '旅行生活'), ('b', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])
        self.call(turn='t2'); self.live([('a', '旅行生活'), ('b', '旅行生活')])
        self.prepare(ok=False)

    def test_create_readback_requires_new_id(self):
        self.call(); self.live([('dev', '开发工具')]); self.prepare()
        self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.live([('dev', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_reuse_id_cannot_be_swapped_between_snapshots(self):
        self.call(); self.live([('a', '旅行生活')]); self.prepare()
        self.live([('b', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_one_preparation_per_turn_and_next_turn_uses_real_group(self):
        self.stage(); self.prepare(ok=False)
        self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.call(turn='t2'); self.live([('travel', '旅行生活')])
        self.assertEqual(self.prepare()['action'], 'reuse')
        self.live([('travel', '旅行生活')])
        self.assertEqual(self.saved()['sections']['旅行生活'], 'travel')

    def test_creation_registration_survives_failed_move(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.live([('travel', '旅行生活')])
        self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'travel'}, {'isError': True})
        self.call(turn='t2'); self.live([('travel', '旅行生活')])
        self.assertEqual(self.prepare()['action'], 'reuse')
        self.assertFalse(self.state().get('section_done'))

    def test_disabled_and_non_boolean_options_are_inert(self):
        for enabled in (False, 'true', 1, None):
            self.settings['auto_create_sections'] = enabled; self.write_settings()
            self.call(turn=str(enabled)); self.live()
            self.prepare(ok=False)
            self.assertNotIn('自动新建已开启', self.call())

    def test_preparation_requires_fresh_snapshot(self):
        self.call(); self.prepare(ok=False)
        self.live(); self.call(turn='t2'); self.prepare(ok=False)

    def test_completed_and_pinned_and_project_chats_are_protected(self):
        self.call(); self.snapshot(pinned=True); self.prepare(ok=False)
        self.assertTrue(self.state()['section_preserved'])
        self.assertNotIn('自动新建已开启', self.call(turn='t2'))

    def test_project_without_custom_section_is_protected(self):
        self.call(); self.live(projectId='project-a'); self.prepare(ok=False)
        self.assertTrue(self.state()['section_preserved'])

    def test_remote_host_is_not_eligible(self):
        self.call(); self.live(hostId='remote'); self.prepare(ok=False)

    def test_ambiguous_kept_chat_is_not_reopened(self):
        self.call(); self.live()
        result = subprocess.run([sys.executable, str(SCRIPT), '--keep-unclassified', SID],
                                env={**os.environ, 'CODEX_HOME': str(self.home)}, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.state()['unclassified'])
        self.assertNotIn('自动新建已开启', self.call(turn='t2'))
        self.prepare(ok=False)

    def test_invalid_name_description_and_reserved_ids(self):
        self.call(); self.live()
        for name, description in (('', 'x'), ('x\ny', 'x'), ('x' * 61, 'x'), ('x', ''), ('x', 'y' * 301)):
            self.prepare(name, description, ok=False)
        self.prepare(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.live([('pinned', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_cap_is_checked_before_creation_and_registration(self):
        self.settings['sections'] = {'分类' + str(i): 'id' + str(i) for i in range(20)}
        self.write_settings(); self.call(); self.live(); self.prepare(ok=False)
        self.settings['sections'].pop('分类19'); self.write_settings()
        self.prepare(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.settings['sections']['其他'] = 'other'; self.write_settings()
        self.live([('travel', '旅行生活')])
        self.assertEqual(len(self.saved()['sections']), 20)
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_deleted_configured_name_is_not_resurrected(self):
        self.call(); self.live(); self.prepare('开发工具', ok=False)

    def test_manual_rename_reuses_id_and_preserves_description(self):
        self.settings['section_descriptions'] = {'开发工具': '原归属说明'}; self.write_settings()
        self.call(); self.live([('dev', '软件工具')])
        self.assertEqual(self.prepare('软件工具')['action'], 'reuse')
        self.live([('dev', '软件工具')])
        saved = self.saved()
        self.assertEqual(saved['sections']['软件工具'], 'dev')
        self.assertNotIn('开发工具', saved['sections'])
        self.assertEqual(saved['section_descriptions']['软件工具'], '原归属说明')

    def test_latest_settings_merged_and_permissions_preserved(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.settings.update(extra='keep', manage_existing=True)
        self.settings['sections']['财务'] = 'finance'; self.write_settings()
        self.live([('travel', '旅行生活')])
        saved = self.saved()
        self.assertEqual(saved['sections']['财务'], 'finance')
        self.assertTrue(saved['manage_existing']); self.assertEqual(saved['extra'], 'keep')
        self.assertEqual(saved['installed_at_ms'], self.settings['installed_at_ms'])
        self.assertEqual((self.root / 'settings.json').stat().st_mode & 0o777, 0o600)

    def test_disabled_after_create_does_not_register(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        self.settings['auto_create_sections'] = False; self.write_settings()
        self.live([('travel', '旅行生活')])
        self.assertNotIn('旅行生活', self.saved()['sections'])
        self.assertFalse(self.state().get('section_done'))

    def test_pause_after_create_does_not_mutate_state(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        before = (self.root / (SID + '.json')).read_bytes()
        self.settings['enabled'] = False; self.write_settings()
        self.live([('travel', '旅行生活')])
        self.assertEqual(before, (self.root / (SID + '.json')).read_bytes())
        self.assertNotIn('旅行生活', self.saved()['sections'])

    def test_two_processes_register_without_lost_updates(self):
        self.stage(); self.tool('create_sidebar_section', {'name': '旅行生活'})
        state = self.state(); state['pending_section_registration']['name'] = '家庭生活'
        (self.root / (OTHER + '.json')).write_text(json.dumps(state))
        def register(sid):
            self.call('PostToolUse', sid=sid, tool_name='mcp__codex_app__list_threads',
                      tool_input={}, tool_response={'threads': [{'id': sid, 'kind': 'codex', 'title': '默认标题'}],
                      'sections': [{'sectionId': 'travel', 'name': '旅行生活'},
                                   {'sectionId': 'family', 'name': '家庭生活'}]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(register, [SID, OTHER]))
        self.assertEqual(self.saved()['sections']['旅行生活'], 'travel')
        self.assertEqual(self.saved()['sections']['家庭生活'], 'family')

    def test_guidance_preserves_task_priority_and_native_boundary(self):
        out = self.call()
        for text in ('先正常完成用户实质任务', '先复用真实侧栏', '--prepare-section',
                     '类别明确', '单次事项不建', '原生创建工具缺失时不创建', '每轮最多准备一次'):
            self.assertIn(text, out)

    def test_section_snapshot_does_not_persist_other_chat_membership(self):
        self.call()
        self.tool('list_threads', response={'threads': [{'id': SID, 'kind': 'codex', 'title': '默认标题'}],
                  'sections': [{'sectionId': 'travel', 'name': '旅行生活', 'itemKeys': ['private-other-id']}]})
        self.assertNotIn('private-other-id', json.dumps(self.state()))
