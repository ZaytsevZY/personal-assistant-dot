"""Export a self-contained local dashboard; never serve or execute tasks from it."""

import base64
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path

from .runtime import TaskRunner
from .storage import LocalError, now


ASSETS = Path(__file__).resolve().parent
LABELS = {"demo-news": "合成新闻演示", "demo-open-source": "合成开源调研"}


def load_schedule_registry(project):
    value = json.loads((Path(project) / "config/schedules.example.json").read_text())
    if (not isinstance(value, dict) or value.get("registry_mode") != "single_project_registry"
            or value.get("scheduler_implemented") is not False
            or not isinstance(value.get("tasks"), list)
            or any(value.get(key) is not None for key in ("backend", "timezone", "output_channel"))):
        raise LocalError("central schedule registry is unsupported or attempts to enable delivery")
    tasks = value["tasks"]
    if len(tasks) != 2 or any(not isinstance(task, dict) or not isinstance(task.get("id"), str) for task in tasks):
        raise LocalError("central schedule registry must contain the two disabled task definitions")
    expected = {"daily-news": "daily", "weekly-open-source-review": "weekly"}
    if ({task.get("id") for task in tasks} != set(expected)
            or any(task.get("enabled") is not False or task.get("cadence") != expected[task["id"]]
                   or task.get("local_time") is not None or task.get("weekday") is not None for task in tasks)):
        raise LocalError("this MVP only previews the disabled, unconfigured central schedules")
    return value


def _hash(content):
    return base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")


def render_console(snapshot, registry, generated_at):
    css = (ASSETS / "console.css").read_text()
    script = (ASSETS / "console_preview.js").read_text()
    policy = ("default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; "
              "object-src 'none'; img-src 'none'; font-src 'none'; "
              "script-src 'sha256-" + _hash(script) + "'; style-src 'sha256-" + _hash(css) + "'")
    tasks = [task for task in snapshot["tasks"] if task.get("synthetic") is True]
    counts = Counter("uncertain" if task["state"] in {"ready", "running"} else task["state"] for task in tasks)
    total = len(tasks)
    finished = counts["succeeded"] + counts["failed"]
    success_rate = str(round(counts["succeeded"] / finished * 100)) + "%" if finished else "—"
    rows = []
    names = {"succeeded": ("已完成", "good"), "failed": ("失败", "bad"), "uncertain": ("需核对", "warn")}
    for task in reversed(tasks[-50:]):
        state = "uncertain" if task["state"] in {"ready", "running"} else task["state"]
        label, color = names[state]
        rows.append('<tr data-workflow="' + escape(task["workflow_id"], quote=True) + '"><td>'
                    + LABELS[task["workflow_id"]] + '<br><span class="mono">'
                    + escape(task["task_id"][:8]) + '</span></td><td><span class="badge ' + color + '">'
                    + label + '</span></td><td class="mono">'
                    + escape(str(task.get("created_at", "未知"))[:80]) + '</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="3" class="muted">暂无合成任务。可在命令入口手动运行 /run demo-news 后重新导出。</td></tr>')
    bars = "".join('<div><div class="bar-label"><span>' + label + '</span><strong>' + str(counts[state])
                   + '</strong></div><progress class="' + state + '" value="' + str(counts[state])
                   + '" max="' + str(max(total, 1)) + '" aria-label="' + label + '"></progress></div>'
                   for state, label in (("succeeded", "已完成"), ("failed", "失败"), ("uncertain", "需核对")))
    schedule_cards = "".join('<article class="schedule-card"><span class="badge">未启用 · 未设时区</span><h3>'
                             + ("每日新闻" if task["cadence"] == "daily" else "每周开源检查与建议")
                             + '</h3><div class="mono">' + escape(task["id"]) + '</div>'
                             + '<p class="muted small">具体时间、执行后端与输出渠道尚未配置。</p></article>'
                             for task in registry["tasks"])
    module_cards = "".join('<article class="module"><h3>' + title + '</h3><span class="badge '
                           + ("good" if state == "已实现" else "") + '">' + state
                           + '</span><p>' + detail + '</p></article>' for title, state, detail in (
                               ("私人收集", "已实现", "本地保存未分类笔记，不推断承诺。"),
                               ("演示运行器", "已实现", "合成工作流、状态、幂等与暂停。"),
                               ("本地控制台", "已实现", "只读快照、任务筛选与 UTC 演练。"),
                               ("真实新闻与研究", "未接入", "当前没有实时检索、来源核实或模型调用。"),
                               ("飞书 / dot 渠道", "未接入", "没有主动推送或外部对话适配。"),
                               ("日历与行情", "未接入", "没有日历访问、行情数据或交易能力。")))
    paused = "手动运行已暂停" if snapshot["settings"]["paused"] else "手动运行可用"
    excluded = len(snapshot["tasks"]) - total
    reference = escape(generated_at[:16], quote=True)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(policy, quote=True)}">
<title>Personal Assistant · 本地控制台</title><style>{css}</style></head>
<body><div class="shell"><aside class="sidebar"><div class="brand">Personal<br>Assistant</div><div class="eyebrow">LOCAL · SNAPSHOT</div>
<nav aria-label="控制台导航"><a href="#overview">此刻概览</a><a href="#tasks">合成任务</a><a href="#schedules">统一调度</a><a href="#modules">功能模块</a></nav>
<p class="side-note">dot 是初始控制宿主。<br>工作流与数据保持可移植。<br><br>本地文件 · 无后台服务</p></aside>
<main class="main"><header><div><div class="eyebrow">PERSONAL ASSISTANT / LOCAL CONSOLE</div><h1>把状态看清楚，再决定下一步。</h1><p class="muted">只读快照 · {escape(generated_at)} · UTC</p></div><span class="badge good">{paused}</span></header>
<div class="notice">当前仅展示合成任务记录，不是真实新闻统计。页面不读取笔记、连接账号或执行任务；数据更新后请重新导出。</div>
<section id="overview" class="stats" aria-label="合成任务概览"><article class="stat"><div class="muted small">合成任务</div><div class="number">{total}</div></article><article class="stat"><div class="muted small">已完成</div><div class="number">{counts['succeeded']}</div></article><article class="stat"><div class="muted small">需核对</div><div class="number">{counts['uncertain']}</div></article><article class="stat"><div class="muted small">已启用定时任务</div><div class="number">0</div></article></section>
<div class="grid"><section class="panel"><h2>合成任务状态</h2><p class="small muted">完成样本成功率：<strong>{success_rate}</strong><br>仅计算成功与失败；不衡量新闻准确性。</p><div class="bars">{bars}</div><p class="small muted">残留待执行或运行中记录显示为需核对；本页不修改其状态。</p></section>
<section id="tasks" class="panel"><div class="panel-heading"><h2>最近合成任务</h2><label>类型筛选<select id="task-filter"><option value="all">全部合成任务</option><option value="demo-news">合成新闻</option><option value="demo-open-source">合成开源调研</option></select></label></div><div class="table-wrap"><table><thead><tr><th>任务 / 短 ID</th><th>状态</th><th>创建时间 UTC</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p class="small muted">最多展示最近 50 条；未展示非合成记录 {excluded} 条。幂等键、笔记与草稿正文均未导出。</p></section></div>
<section id="schedules" class="panel"><h2>统一调度</h2><p class="muted small">来自项目中央注册表。全部未启用，没有下一次实际执行时间。</p><div class="schedule-cards">{schedule_cards}</div>
<div class="preview"><h3>演练下一次时间</h3><p class="muted small">以下都是临时假设，以 UTC 计算；不会保存、启用或触发任务，也不代表你的个人时区。</p>
<div class="fields"><label>假设参考时间 · UTC<input id="reference" type="datetime-local" value="{reference}" min="1970-01-01T00:00" max="9998-12-31T23:59"></label><label>假设每日时间<input id="daily-time" type="time" value="08:00"></label><label>假设每周星期<select id="weekly-day"><option value="1">星期一</option><option value="2">星期二</option><option value="3">星期三</option><option value="4">星期四</option><option value="5">星期五</option><option value="6">星期六</option><option value="0">星期日</option></select></label><label>假设每周时间<input id="weekly-time" type="time" value="09:00"></label><label>预览次数<input id="preview-count" type="number" min="1" max="7" value="3"></label></div>
<button id="preview-button" type="button">仅计算预览</button><p id="preview-error" class="error small" role="alert"></p><div id="preview-results" class="results" aria-live="polite"></div></div></section>
<section id="modules" class="panel"><h2>功能模块</h2><div class="modules">{module_cards}</div></section>
<footer class="footer">这是本地导出的快照，不是联网服务。刷新页面不会获取新状态；更改演练参数不会修改中央配置。网络、投递与后台调度均关闭。</footer></main></div><script>{script}</script></body></html>'''


def export_console(store, project):
    runner = TaskRunner(store)
    snapshot = runner.snapshot()
    registry = load_schedule_registry(project)
    generated_at = now()
    document = render_console(snapshot, registry, generated_at)
    relative = "resources/console.html"
    with store.lock():
        store.write_text(relative, document)
        store.audit("console_exported")
    return {"status": "exported", "mode": "read_only_local_snapshot", "private_file": relative,
            "generated_at": generated_at, "scheduler_enabled": False, "network_enabled": False}
