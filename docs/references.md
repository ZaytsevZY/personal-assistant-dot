# 参考资料与考察种子

以下项目仅作为研究对象，没有安装、性能对比或安全审计。采用前重新检查官方文档、许可证、发行、安全公告与数据流。本页链接于 2026-11-04 通过网页阅读核对；日期是查阅时间，不代表版本冻结或所有功能已经核实。

| 对象 | 借鉴问题 | 一手入口 |
| --- | --- | --- |
| OpenClaw | 个人助手的整体组织与渠道边界 | [官方仓库](https://github.com/openclaw/openclaw) |
| Hermes Agent | 持续使用的工作流与工具组织 | [官方仓库](https://github.com/NousResearch/hermes-agent) |
| LangGraph | 中断、短期检查点和长期存储的区分 | [官方持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence) |
| Letta | 有状态 agent 与记忆组织 | [官方概念文档](https://docs.letta.com/v1-sdk/concepts/stateful-agents) |

LangGraph 文档区分线程内检查点与跨线程存储；可用来设计恢复与长期记忆。其余候选先看具体任务能否受益，不依据项目名称、热度或口号做采用决定。公开 API 或渠道支持可能变化，必须在实现时确认。

GTD 可作为“收集、澄清、下一步、等待、回顾”的实践灵感；PARA 可作为“项目、责任、资源、归档”的目录灵感。这里采用的是通用组织思路，不复制原方法的受版权保护材料，也不把方法视为普遍有效的研究结论。

新闻与经济来源种子见[配置](../config/sources.example.json)。该清单没有实现抓取、RSS、付费访问或数据授权；来源主页可用不代表可批量抓取、实时获取或再分发数据。
