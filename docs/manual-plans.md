# 统一计划与持久运行账本

本版本实现手动驱动的合成计划，不是后台调度器。项目[中央注册表](../config/schedules.example.json)引用[计划模板](../config/plans.example.json)；真实每日新闻与每周开源任务继续禁用。模板中的 UTC 时刻是测试示例，不代表用户的正式安排。

## 配置与命令

计划支持每日或每周、IANA 时区、24 小时时刻与错过运行策略。每周星期使用 0=周一至 6=周日。只允许 `demo-news` 和 `demo-open-source`，没有网络、投递、账号或启用后台执行的配置字段。

```sh
python3 -B -m assistant_dot /plans
python3 -B -m assistant_dot /plans-preview --since 2026-11-01T00:00:00Z --at 2026-11-04T12:00:00Z
python3 -B -m assistant_dot --private-root "<private-root>" /plans-copy
python3 -B -m assistant_dot --private-root "<private-root>" /plans-reconcile --since 2026-11-01T00:00:00Z --at 2026-11-04T12:00:00Z
python3 -B -m assistant_dot --private-root "<private-root>" /plans-state
python3 -B -m assistant_dot --private-root "<private-root>" /plans-run "<occurrence-id>" --at 2026-11-04T12:00:00Z
```

私人目录先按[本地最小版本](local-mvp.md)初始化。`/plans-copy` 只复制一次至仓库外的 `plans.json`，不会覆盖已有文件；实际个人计划应在该文件中维护，禁止将个人时间和偏好提交公共仓库。无私有覆盖时读取项目示例。

预览没有写入或执行。登记只保存候选与跳过原因，首次必须明确 `--since`；后续从持久水位继续。窗口为 `(since, at]`，拒绝时间回退或静默改变起点。所有输入分析时间必须有 UTC offset。`/plans-run` 才执行一条仍然 eligible 的合成候选；不指定 `--at` 时使用实际当前 UTC，执行前会重新核对到该时点的错过策略。

## 明确的错过策略

- `coalesce_latest`：保留最新未运行候选，更早候选跳过。后续登记出现更新候选时，旧的 ready 候选也标为 superseded；已完成或结果未知的记录不被覆盖。
- `skip_expired`：迟到严格超过 `max_lateness_minutes` 就跳过，恰好到期限仍有效。执行前再次核对，避免拿很久以前的 ready 状态直接运行。
- 回看窗口最多 31 天。超过窗口的更早部分不会枚举或补跑；账本记录 `older_history_skipped` 与有效起点，不能当作已经完整检查全部历史。
- 账本最多 500 条（可设更小上限），达到容量时拒绝继续写入，不自动删除、归档或重置水位。归档和配置迁移工具尚未实现。

## 时区与中断

使用 Python 标准库的 IANA `zoneinfo`，依赖机器安装的时区数据库，不联网下载。数据库不存在时拒绝相应计划；规则可能随数据库更新变化，版本尚未固定。[Python 官方说明](https://docs.python.org/3/library/zoneinfo.html)

当地时间因时区跃迁不存在时，记录 skipped/dst_gap，`due_at` 为空；用于分配审计窗口的 anchor 不是实际执行时刻。当地时间重复时只取较早的 UTC 实例，每个当地日期最多一个候选。测试覆盖纽约春季缺失、秋季重复和加德满都的非整小时偏移。

`state/plans.json` 在私人目录保存配置摘要、水位、候选与任务关联。计划与核心运行器共用进程写锁；每条候选派生稳定幂等键，重复手动操作会复用核心记录。中断后核对已完成结果，不盲目重跑；结果不明时保持 uncertain。多个文件不是数据库事务，但在“核心已完成、账本更新失败”后能从核心记录恢复，避免再次生成草稿。

配置发生任何变化都会与已有账本摘要不符并被拒绝，需要明确迁移，不能靠删除账本重置历史。当前只支持同一机器、同一私人目录的前台操作；没有跨机器租约、自动重试、真实平台执行或后台触发。
