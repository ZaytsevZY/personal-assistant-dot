# personal-assistant-dot

一个本地优先、可审计、由用户控制的个人助手设计初稿。把生活与工作流程、新闻发现、开源调研和推荐反馈放进同一套可持续改进的方法中。

**状态：设计与提示词模板，可以手工试运行；没有运行中的 agent、消息适配器、新闻爬虫或调度器。** 没有内置个人资料。

项目最初由 dot 协助开发和管理，dot 也可以成为初期主控制入口。名称保留这个起点，但核心策略、数据、提示词和调度契约不依赖 dot；后续可以换成其他 agent。控制入口、执行 agent 和输出渠道分别配置，见[agent 可替换设计](docs/agent-portability.md)。

## 从哪里开始

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
| dot 起步、其他 agent 接管与数据迁移 | [agent 可替换设计](docs/agent-portability.md) |
| 飞书 / dot 对话、命令与电脑控制台 | [入口设计](docs/interfaces.md) |
| 经济与股票查询的可选范围 | [经济与市场扩展](docs/market-extension.md) |
| 本地数据、备份和公开边界 | [隐私与发布](docs/privacy.md) |
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
