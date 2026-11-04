# personal-assistant-dot

一个本地优先、可审计、由用户控制的个人助手项目。把生活与工作流程、新闻发现、开源调研和推荐反馈放进同一套可持续改进的方法中。

**状态：已有可运行的本地交互工作台**，支持状态查看、私人笔记命令、合成任务、手动计划、持久账本与新闻推荐合成预览；另支持官方公开 RSS 手动获取，以及飞书显式 profile 与 Apple 日历的权限受限只读接口。日历通过固定身份的本机应用单独授权，系统弹窗由用户处理，见[接入流程](docs/real-connections.md)。模型、账号投递与后台调度仍未接入；真实账号读取受凭据、具体目标和系统授权限制。没有内置个人资料。

项目最初由 dot 协助开发和管理，dot 也可以成为初期主控制入口。名称保留这个起点，但核心策略、数据、提示词和调度契约不依赖 dot；后续可以换成其他 agent。控制入口、执行 agent 和输出渠道分别配置，见[agent 可替换设计](docs/agent-portability.md)。

## 从哪里开始

macOS / Linux、Python 3.9+；核心无需第三方 Python 包。真实 RSS 需要系统 curl，飞书接口需要已有官方 lark-cli，Apple 日历需要 Mac 与 Swift/EventKit。在仓库根目录先运行：

```sh
python3 -B -m assistant_dot /h
python3 -B -m assistant_dot /runtime
python3 -B -m assistant_dot /news-preview --interests technology
python3 -B tests/acceptance.py
```

要保存内容和运行演示，请按[本地最小版本](docs/local-mvp.md)选择仓库外、未被 Git 管理的私人目录并初始化。之后运行 `python3 -B -m assistant_dot --private-root "<private-root>" /workbench`，打开终端显示的本机地址。当前只运行合成工作流，不会自动获取新闻、调用模型、发送消息或创建日程；只有明确点击或运行 `/news-fetch` 才读取固定官方 RSS。

1. 阅读[助手工作说明](docs/charter.md)，确定助手如何记忆、建议和行动。
2. 阅读[系统设计](docs/architecture.md)与[数据隔离](docs/privacy.md)，在仓库之外建立私人资料目录。
3. 从[日常收集](prompts/capture.md)、[新闻简报](prompts/news-brief.md)和[每周回顾](prompts/weekly-review.md)中任选一个手工试用。只向获得授权的运行环境提供必要资料。
4. 用[反馈模板](templates/feedback.example.json)记录有效和无效的推荐；模板实例留在私人目录。
5. 使用 Python 3.9 或更高版本运行公开内容检查：`python3 scripts/check_public.py`。仅使用 Python 标准库，不需安装第三方包。

## 仓库导航

| 内容 | 入口 |
| --- | --- |
| 助手的角色、主动程度与权限 | [工作说明](docs/charter.md) |
| 组件、运行状态、可靠性与集成 | [架构](docs/architecture.md) |
| 可运行命令、私人目录、配置与验收 | [本地最小版本](docs/local-mvp.md) |
| 本地交互工作台、任务与计划操作 | [本地控制台](docs/local-console.md) |
| IANA 时区、错过策略、水位与手动候选运行 | [统一计划](docs/manual-plans.md) |
| dot 起步、其他 agent 接管与数据迁移 | [agent 可替换设计](docs/agent-portability.md) |
| 飞书 / dot 对话、命令与电脑控制台 | [入口设计](docs/interfaces.md) |
| 经济与股票查询的可选范围 | [经济与市场扩展](docs/market-extension.md) |
| 本地数据、备份和公开边界 | [隐私与发布](docs/privacy.md) |
| 新闻来源、许可边界、失败和覆盖缺口 | [来源审查](docs/news-sources.md) |
| 真实 RSS、飞书 profile 与 Apple 日历只读接口 | [真实连接](docs/real-connections.md) |
| 可插拔合成来源、重大覆盖与兴趣推荐预览 | [新闻预览](docs/news-preview.md) |
| 重大新闻、来源差异、事实与观点 | [信息发现](docs/discovery.md) |
| 个性化、探索与推荐方向调整 | [推荐政策](docs/recommendations.md) |
| 开源跟踪、改进提案和提交方案 | [迭代机制](docs/iteration.md) |
| 统一调度与移动端可达性 | [调度设计](docs/scheduling.md) |
| 如何判断助手是否有用 | [评估与路线图](docs/roadmap.md) |
| 候选框架及一手参考 | [参考资料](docs/references.md) |
| 通用运行配置 | [配置样例](config/policy.example.json) |
| 新闻源种子清单 | [来源样例](config/sources.example.json) |

## 建议的初始节奏

默认采用每日关注新闻、每周考察开源项目并整理改进建议，频率可调整。调度统一放在项目内的[调度样例](config/schedules.example.json)，不另外分散创建任务。个人回顾和每月质量评估作为可选方案。没有创建或启用定时任务，尚未配置具体时间；时区、时间、通知渠道、账号与预算均由私人配置决定。

新闻简报始终检查时政、经济、科技的重大变化；再安排个人相关与探索内容。发现反馈只能生成调整建议，不能自行修改用户目标、权限、来源规则或公开发布策略。

## 公开使用说明

公开目录只放通用设计、代码与合成示例。日记、账号、日历、偏好、阅读记录、日志、原文缓存和模型输入输出留在仓库之外。`.gitignore` 与检查脚本只是辅助，不能代替人工检查和完整的密钥扫描。发布步骤见[隐私与发布](docs/privacy.md)，材料范围见[内容来源说明](docs/content-provenance.md)。项目采用 [MIT 许可证](LICENSE)；第三方来源、数据与产品名称的使用条件仍需分别核实。
