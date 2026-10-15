#!/usr/bin/env python3
"""Local setup and diagnostics. No network, database, or Codex config writes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import sys
import time

from session_organizer import HOME, ROOT, read_json, save_json


def legacy_hooks_present():
    config = HOME / 'config.toml'
    text = config.read_text(encoding='utf-8') if config.exists() else ''
    return ('# BEGIN codex-session-organizer v1' in text
            or 'hooks/session_organizer.py' in text)


def initialize(config):
    if legacy_hooks_present():
        raise ValueError('检测到旧版内联 Hook，请先按旧版卸载说明移除，避免重复执行。')
    rows = config.get('sections') if isinstance(config, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError('sections 必须包含 1–20 个分区。')
    sections, descriptions = {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('每个分区必须是对象。')
        name, ident, description = (row.get(k) for k in ('name', 'id', 'description'))
        for value, limit in ((name, 60), (ident, 128), (description, 300)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError('分区 name/id/description 必须是非空单行文本，长度分别不超过 60/128/300。')
        if name in sections or ident in sections.values() or ident in ('pinned', 'chats', 'threads'):
            raise ValueError('分区名称和 ID 必须唯一，且不得使用系统分区。')
        sections[name] = ident
        descriptions[name] = description
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / 'settings.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = ROOT / 'settings.json'
        existed = path.exists()
        settings = read_json(path) if existed else {
            'installed_at_ms': time.time_ns() // 1_000_000,
            'enabled': True,
        }
        settings.update(sections=sections, section_descriptions=descriptions)
        save_json(path, settings)
    return {'status': 'initialized', 'section_count': len(sections),
            'existing_cutoff_preserved': existed, 'settings': str(path)}


def set_enabled(enabled):
    with (ROOT / 'settings.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        settings = read_json(ROOT / 'settings.json')
        settings['enabled'] = enabled
        save_json(ROOT / 'settings.json', settings)
    return {'status': 'enabled' if enabled else 'paused', 'history': 'untouched'}


def doctor():
    path = ROOT / 'settings.json'
    checks = {'macos': platform.system() == 'Darwin',
              'python_3_9_plus': sys.version_info >= (3, 9),
              'initialized': path.is_file(), 'no_legacy_inline_hooks': not legacy_hooks_present()}
    settings = read_json(path) if path.exists() else {}
    checks['enabled'] = settings.get('enabled', False) is True
    checks['private_settings'] = path.exists() and path.stat().st_mode & 0o077 == 0
    checks['section_mapping'] = bool(settings.get('sections'))
    return {'local_checks_pass': all(checks.values()), 'checks': checks,
            'state_directory': str(ROOT), 'python': sys.executable,
            'runtime_checks': '请在 Codex /hooks 确认两个 Hook 已信任；在桌面新会话确认原生命名/分区工具可用。'}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Read sections JSON from file or stdin (-).')
    init.add_argument('config', nargs='?', default='-')
    for name in ('doctor', 'pause', 'resume'):
        sub.add_parser(name)
    args = parser.parse_args()
    if args.command == 'init':
        value = json.load(sys.stdin) if args.config == '-' else read_json(Path(args.config))
        result = initialize(value)
    elif args.command == 'doctor':
        result = doctor()
    else:
        result = set_enabled(args.command == 'resume')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('local_checks_pass') is False else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as error:
        print('codex-session-organizer: ' + str(error), file=sys.stderr)
        sys.exit(1)
