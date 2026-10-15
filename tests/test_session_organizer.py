import json
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/session_organizer.py'
SID = str(uuid.UUID(int=(1800000000000 << 80) | (7 << 76) | (2 << 62) | 1))
OTHER = str(uuid.UUID(int=(1800000000000 << 80) | (7 << 76) | (2 << 62) | 2))


class HookFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / 'state/codex-session-organizer'
        self.root.mkdir(parents=True)
        self.settings = {'installed_at_ms': 1799999999999, 'excluded_session_ids': [], 'sections': {'公司': 'company', '品牌': 'brand', '开发工具': 'dev', '学习研究': 'study'}}
        self.write_settings()
        self.addCleanup(self.tmp.cleanup)

    def write_settings(self):
        (self.root / 'settings.json').write_text(json.dumps(self.settings))

    def call(self, event='UserPromptSubmit', sid=SID, turn='t1', **extra):
        data = dict(hook_event_name=event, session_id=sid, turn_id=turn, **extra)
        result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(data), text=True, capture_output=True,
                                env={**os.environ, 'CODEX_HOME': str(self.home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def state(self, sid=SID):
        return json.loads((self.root / (sid + '.json')).read_text())

    def tool(self, name, args=None, response=None, **extra):
        extra.setdefault('turn', self.state()['turn_id'])
        self.call('PostToolUse', tool_name='mcp__codex_app__' + name,
                  tool_input=args or {}, tool_response=response if response is not None else {'isError': False}, **extra)

    def snapshot(self, title='默认标题', section=None, project=None, pinned=False):
        thread = {'id': SID, 'kind': 'codex', 'title': title, 'projectId': project}
        key = 'codex:project:' + project if project else 'codex:thread:local:' + SID
        data = {'threads': [] if pinned else [thread], 'pinnedThreads': [thread] if pinned else [],
                'sections': [{'sectionId': section, 'itemKeys': [key]}] if section else []}
        self.tool('list_threads', response={'isError': False, 'content': [{'type': 'text', 'text': json.dumps(data)}]})

class HookTests(HookFixture):
    def test_first_prompt_has_guidance(self):
        out = json.loads(self.call())
        self.assertIn('主题对象｜持续目标', out['hookSpecificOutput']['additionalContext'])

    def test_existing_sessions_excluded(self):
        self.settings['excluded_session_ids'] = [SID]; self.write_settings()
        self.assertEqual(self.call(), '')
        self.assertFalse((self.root / (SID + '.json')).exists())

    def test_old_creation_time_excluded(self):
        self.settings['installed_at_ms'] = 1800000000001; self.write_settings()
        self.assertEqual(self.call(), '')

    def test_unknown_session_format_ignored(self):
        self.assertEqual(self.call(sid='../../bad'), '')
        self.assertEqual(self.call(sid=str(uuid.uuid4())), '')

    def test_sessions_isolated(self):
        self.call(); self.call(sid=OTHER, turn='t2')
        self.assertEqual(self.state()['turn_id'], 't1')
        self.assertEqual(self.state(OTHER)['turn_id'], 't2')

    def test_tool_success_alone_not_completed(self):
        self.call(); self.snapshot(); self.tool('set_thread_title', {'title': '插件｜稳定性'})
        self.assertFalse(self.state().get('title_done'))
        self.assertIn('additionalContext', self.call())

    def test_readback_commits_title_and_section(self):
        self.call(); self.snapshot()
        self.tool('set_thread_title', {'title': '插件｜稳定性'})
        self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'dev'})
        self.snapshot(title='插件｜稳定性', section='dev')
        self.assertTrue(self.state()['title_done']); self.assertTrue(self.state()['section_done'])
        self.assertEqual(self.state()['original_title'], '默认标题')
        self.assertIsNone(self.state()['original_section'])
        self.assertIn('目标校准', self.call(turn='t2'))

    def test_failed_tool_not_recorded(self):
        self.call(); self.snapshot()
        self.tool('set_thread_title', {'title': '插件｜稳定性'}, {'isError': True})
        self.snapshot()
        self.assertNotIn('pending_title', self.state())
        self.assertFalse(self.state().get('title_done'))

    def test_wrong_thread_not_recorded(self):
        self.call(); self.snapshot()
        self.tool('set_thread_title', {'threadId': OTHER, 'title': '插件｜稳定性'})
        self.tool('move_thread_to_sidebar_section', {'threadId': OTHER, 'sectionId': 'dev'})
        self.assertNotIn('pending_title', self.state()); self.assertNotIn('pending_section', self.state())

    def test_chatgpt_not_recorded(self):
        self.call(); self.snapshot()
        self.tool('set_thread_title', {'source': 'chatgpt', 'title': '插件｜稳定性'})
        self.assertNotIn('pending_title', self.state())

    def test_wrong_turn_not_recorded(self):
        self.call(); self.tool('set_thread_title', {'title': '插件｜稳定性'}, turn='child')
        self.assertNotIn('pending_title', self.state())

    def test_manual_title_change_preserved(self):
        self.call(); self.snapshot(); self.snapshot(title='我手动命名的标题')
        self.assertTrue(self.state()['title_preserved'])
        self.tool('set_thread_title', {'title': '其他标题'})
        self.assertNotIn('pending_title', self.state())

    def test_existing_section_preserved(self):
        self.call(); self.snapshot(section='brand')
        self.assertTrue(self.state()['section_preserved'])

    def test_pinned_preserved(self):
        self.call(); self.snapshot(pinned=True)
        self.assertTrue(self.state()['section_preserved'])

    def test_project_section_preserved(self):
        self.call(); self.snapshot(section='company', project='project-id')
        self.assertTrue(self.state()['section_preserved'])

    def test_unknown_section_target_ignored(self):
        self.call(); self.snapshot()
        self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'unknown'})
        self.assertNotIn('pending_section', self.state())

    def test_unclassified_decision_recorded(self):
        self.call(); self.snapshot()
        r = subprocess.run([sys.executable, str(SCRIPT), '--keep-unclassified', SID],
                           env={**os.environ, 'CODEX_HOME': str(self.home)}, capture_output=True)
        self.assertEqual(r.returncode, 0); self.assertTrue(self.state()['unclassified'])

    def test_missing_readback_does_not_complete(self):
        self.call(); self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'dev'})
        self.assertFalse(self.state().get('section_done'))

    def test_state_survives_new_process(self):
        self.call(); self.snapshot(); self.tool('set_thread_title', {'title': '插件｜稳定性'}); self.snapshot(title='插件｜稳定性')
        self.assertIn('命名已完成=True', self.call(turn='after-restart'))

    def test_missing_management_tools_instruction(self):
        self.assertIn('工具缺失时忽略管理要求', self.call())

    def test_malformed_tool_result_ignored(self):
        self.call(); self.tool('list_threads', response={'content': [{'type': 'text', 'text': 'not JSON'}]})
        self.assertNotIn('original_title', self.state())

    def test_no_expiry_and_private_state(self):
        self.call(); self.snapshot()
        self.assertNotIn('expires', self.state())
        self.assertEqual((self.root / (SID + '.json')).stat().st_mode & 0o777, 0o600)


class AdaptiveTitleTests(HookFixture):
    def seed_confirmed(self):
        self.call(); self.snapshot()
        self.tool('set_thread_title', {'title': '插件｜个人配置'})
        self.tool('move_thread_to_sidebar_section', {'threadId': SID, 'sectionId': 'dev'})
        self.snapshot(title='插件｜个人配置', section='dev')

    def control(self, action, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), action, SID], text=True, capture_output=True,
                                env={**os.environ, 'CODEX_HOME': str(self.home)})
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)

    def test_goal_change_confirmed_after_readback(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='插件｜个人配置', section='dev')
        self.tool('set_thread_title', {'title': '插件｜开源交付'})
        self.assertEqual(self.state()['managed_title'], '插件｜个人配置')
        self.snapshot(title='插件｜开源交付', section='dev')
        state = self.state()
        self.assertEqual(state['managed_title'], '插件｜开源交付')
        self.assertEqual(state['original_title'], '默认标题')
        self.assertEqual(state['managed_section'], 'dev')
        self.assertEqual(state['last_title_update_turn'], 't2')
        self.assertNotIn('title_preserved', state)

    def test_same_goal_is_noop(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='插件｜个人配置', section='dev')
        self.tool('set_thread_title', {'title': '插件｜个人配置'})
        self.assertNotIn('pending_title', self.state())
        self.snapshot(title='插件｜个人配置', section='dev')
        self.assertNotIn('title_preserved', self.state())

    def test_goal_update_requires_current_turn_snapshot(self):
        self.seed_confirmed(); self.call(turn='t2')
        self.tool('set_thread_title', {'title': '插件｜开源交付'})
        self.assertNotIn('pending_title', self.state())

    def test_topic_change_is_not_an_automatic_goal_update(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='插件｜个人配置', section='dev')
        self.tool('set_thread_title', {'title': '文案｜开源交付'})
        self.assertNotIn('pending_title', self.state())

    def test_at_most_one_confirmed_update_per_turn(self):
        self.seed_confirmed()
        self.tool('set_thread_title', {'title': '插件｜开源交付'})
        self.assertNotIn('pending_title', self.state())

    def test_failed_goal_update_does_not_commit(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='插件｜个人配置', section='dev')
        self.tool('set_thread_title', {'title': '插件｜开源交付'}, {'isError': True})
        self.snapshot(title='插件｜个人配置', section='dev')
        self.assertEqual(self.state()['managed_title'], '插件｜个人配置')
        self.assertNotIn('pending_title', self.state())

    def test_pending_goal_is_expired_on_next_turn(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='插件｜个人配置', section='dev')
        self.tool('set_thread_title', {'title': '插件｜开源交付'})
        self.call(turn='t3')
        self.assertNotIn('pending_title', self.state())
        self.snapshot(title='插件｜开源交付', section='dev')
        self.assertTrue(self.state()['title_preserved'])
        self.assertEqual(self.state()['managed_title'], '插件｜个人配置')

    def test_manual_change_after_management_locks_title(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='我指定的标题', section='dev')
        self.assertTrue(self.state()['title_preserved'])
        self.assertNotIn('本轮评估', self.call(turn='t3'))
        self.tool('set_thread_title', {'title': '插件｜其他目标'})
        self.assertNotIn('pending_title', self.state())

    def test_explicit_lock_protects_tool_rename(self):
        self.seed_confirmed(); self.call(turn='t2'); self.control('--lock-title')
        self.tool('set_thread_title', {'title': '自定｜我的标题'})
        self.snapshot(title='自定｜我的标题', section='dev')
        self.assertTrue(self.state()['title_preserved'])
        self.assertNotIn('本轮评估', self.call(turn='t3'))

    def test_explicit_unlock_adopts_observed_title(self):
        self.seed_confirmed(); self.call(turn='t2'); self.snapshot(title='自定｜我的目标', section='dev')
        self.control('--unlock-title')
        self.assertFalse(self.state()['title_preserved'])
        self.assertEqual(self.state()['managed_title'], '自定｜我的目标')
        self.assertIn('目标校准', self.call(turn='t3'))

    def test_unlock_without_formatted_readback_fails(self):
        self.call(); self.control('--lock-title'); self.control('--unlock-title', ok=False)
        self.assertTrue(self.state()['title_preserved'])

    def test_unlock_requires_current_turn_readback(self):
        self.seed_confirmed(); self.control('--lock-title'); self.call(turn='t2')
        self.control('--unlock-title', ok=False)
        self.assertTrue(self.state()['title_preserved'])

    def test_v010_confirmed_state_is_reviewed_without_reset(self):
        path = self.root / (SID + '.json')
        path.write_text(json.dumps({'title_done': True, 'managed_title': '插件｜个人配置',
                                    'section_done': True, 'managed_section': 'dev', 'last_title': '插件｜个人配置'}))
        self.assertIn('目标校准', self.call(turn='upgrade'))
        self.assertEqual(self.state()['managed_section'], 'dev')

    def test_v010_preserved_title_remains_protected(self):
        (self.root / (SID + '.json')).write_text(json.dumps({'title_done': True, 'title_preserved': True, 'section_done': True}))
        self.assertNotIn('本轮评估', self.call(turn='upgrade'))

    def test_protected_title_can_discover_explicit_resume_without_setup_skill(self):
        self.seed_confirmed(); self.control('--lock-title')
        out = self.call(turn='t2')
        self.assertIn('--unlock-title', out)
        self.assertIn('用户未要求恢复时，不调用这些管理工具', out)
        self.assertNotIn('目标校准', out.split('正常完成用户任务')[0])

    def test_guidance_distinguishes_goal_from_steps_and_manual_titles(self):
        self.seed_confirmed()
        out = self.call(turn='t2')
        for rule in ('整段会话主线', '普通补充', '临时支线', '左侧主题对象保持不变', '--lock-title', '--unlock-title'):
            self.assertIn(rule, out)


if __name__ == '__main__':
    unittest.main()
