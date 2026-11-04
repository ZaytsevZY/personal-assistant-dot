# 本地最小版本

当前实现：Python 命令入口、私人 JSON 存储、同步任务运行器、合成数据适配器、状态查询、手动暂停和[只读本地控制台](local-console.md)。支持 macOS 和 Linux、Python 3.9+，运行器只使用标准库。不包含新闻抓取、模型调用、后台调度、实时图形控制或真实平台适配器。

## 运行

在仓库根目录运行，先通过帮助了解已实现范围：

```sh
python3 -B -m assistant_dot /h
python3 -B -m assistant_dot /runtime
python3 -B -m assistant_dot /schedule
```

选择一个绝对私有目录替换 `<private-root>`。初始化只接受不存在或空的、当前用户拥有的目录；目录不得位于任何 Git 工作树中，也不得包含本项目。如果个人主目录本身被 Git 管理，应另选未被 Git 管理的位置。根目录和子目录要求仅所有者可访问；程序不会放宽或自动修改已有目录权限。

```sh
python3 -B -m assistant_dot --private-root "<private-root>" init
printf '%s\n' '合成笔记：考虑整理一份阅读清单' | python3 -B -m assistant_dot --private-root "<private-root>" /capture --stdin
python3 -B -m assistant_dot --private-root "<private-root>" /run demo-news --key example
python3 -B -m assistant_dot --private-root "<private-root>" /tasks
python3 -B -m assistant_dot --private-root "<private-root>" /console
python3 -B -m assistant_dot --private-root "<private-root>" /status "<task-id>"
python3 -B -m assistant_dot --private-root "<private-root>" /pause
python3 -B -m assistant_dot --private-root "<private-root>" /resume
```

`--private-root` 放在命令前。`/capture` 只保存为未分类笔记，不推断承诺或时间。推荐 `--stdin`，避免笔记文本进入 shell 历史和进程参数。`demo-news` 与 `demo-open-source` 只生成明确标记的合成草稿，不查询真实新闻或项目。`/news`、`/calendar`、`/market`、`/review` 返回未配置；自然语言输入尚不能执行。

输出为 JSON；退出码 0 表示命令已处理（具体能力可能是 not_configured），2 表示参数、配置或本地存储被拒绝，3 表示查询或运行的任务为 failed/uncertain。应同时检查 JSON 状态，不把退出码 0 当成已完成真实检索或投递。

## 状态与配置

公共初值集中在 [local-runtime.example.json](../config/local-runtime.example.json)，初始化后私人 `settings.json` 是该目录的有效本地配置。只允许合成适配器、手动暂停状态，以及保持为 false 的网络、投递和调度开关；未知配置、非法 JSON 或试图启用外部动作会被拒绝，不静默回退。`/runtime` 显示程序可用能力，不读取或声称已检查某个私人目录。

中央调度注册表仍是 [schedules.example.json](../config/schedules.example.json)。`/schedule` 只读取该表；没有安装定时器、生成系统任务或启用云任务。`/resume` 仅恢复手动合成运行。

私人目录只保存 `inbox/` 笔记、`state/tasks.json`、`resources/drafts/` 草稿、`audit/events.jsonl` 与设置。审计不复制笔记正文。任务记录包含策略版本、适配器、幂等键、状态和相对产物路径，便于其他 agent 理解与接管。

同一工作流与显式幂等键复用已有记录；不指定键时每次视为新任务。写入使用独占进程锁、所有者权限、临时文件和原子替换；拒绝符号链接、多重硬链接及权限过宽的文件。持有锁后发现残留 ready/running 任务，会标为 uncertain，不自动重跑。任务失败或未知时仍能查询记录，不自动重试。

## 模块边界

- [存储](../assistant_dot/storage.py)：路径与权限检查、原子 JSON 写入、独占锁、笔记及审计。
- [运行器与适配接口](../assistant_dot/runtime.py)：平台无关的 `TaskRequest`、`Draft`、`AgentAdapter.prepare/run`，以及持久状态和重复执行保护。
- [命令入口](../assistant_dot/__main__.py)：明确命令分发和 JSON 输出；不执行 shell 文本，不动态加载配置指定的 Python 代码。

CLI 只启用内置合成适配器。Python 接口支持注入另一个受信任适配器以验证接管；这不是运行未知插件的安全沙箱。未来接入真实模型或平台，需要单独实现权限、数据外发与端到端验证。取消接口、跨机器租约、自动备份与完整数据迁移尚未实现。

## 验证与边界

```sh
python3 -B tests/acceptance.py
node tests/console_preview.js
python3 -B scripts/check_public.py
```

验收仅使用临时合成目录，覆盖 CLI、目录隔离、权限、链接攻击、幂等、暂停、配置拒绝、锁冲突、进程中断及适配器替换。不会读写真实账号、日历或用户资料。

文件权限不等于加密；本版本没有加密备份或系统级沙箱。多个文件之间不是数据库事务，异常断电仍可能留下部分本地产物；应检查 uncertain 状态后处理。单个 JSON 状态文件面向小规模原型，当前未提供历史压缩或自动保留期。字节码缓存由 `.gitignore` 排除，不属于公开候选快照；其他未知目录仍阻止公开检查通过。
