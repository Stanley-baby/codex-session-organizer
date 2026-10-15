# v0.1.0 验证说明

## 验证范围

单元与进程级回归测试覆盖命名/分区状态机、历史 ID 过滤、错误工具结果、错误会话/轮次、原生回读确认、手动标题、项目分区、置顶、歧义留白、持久化、私有权限、初始化验证、旧版冲突、重复初始化、暂停/恢复、空格路径和未初始化无副作用。

在 macOS、codex-cli `0.162.0-alpha.17.2` 的隔离 `CODEX_HOME` 验证 marketplace 注册、插件安装、Hook 发现及未自动信任、初始化、两轮合成事件、卸载及状态保留。

受测客户端仅放根目录 portable manifest 时，`hooks/list` 返回空列表；改用 `.codex-plugin/plugin.json` 后返回本插件两个 Hook，状态均为 untrusted，且无加载错误。因此发布包使用兼容格式，不同时放根目录 manifest。

原个人版的真实桌面两轮输入已验收：第一轮完成命名/分区并回读确认，第二轮没有重复改名/搬动。公开版延续这一状态机，增加通用配置与打包。**这不替代每位用户在其安装版本上的真实桌面两轮验收**；公开插件的安装/初始化、Hook 信任与原生工具组合仍请按 README 验收。

GitHub Actions 运行 macOS Python 3.9 与 3.13 测试；实际远端结果以仓库 Actions 页面为准，不将本地结果等同于云端通过。

## 复现

```sh
python3 -m unittest discover -s tests -v
sh -n hooks/run.sh scripts/python.sh
```

隔离安装示例（在仓库根目录执行）：

```sh
TEST_HOME=$(mktemp -d)
CODEX_HOME="$TEST_HOME" codex plugin marketplace add "$PWD"
CODEX_HOME="$TEST_HOME" codex plugin add codex-session-organizer@codex-session-organizer
CODEX_HOME="$TEST_HOME" codex plugin list --json
CODEX_HOME="$TEST_HOME" codex plugin remove codex-session-organizer@codex-session-organizer
```

此测试只检查打包/安装，不启动带真实账号的会话。临时目录请在检查完后自行清理。仓库不包含原用户的安装备份、状态或验收快照。
