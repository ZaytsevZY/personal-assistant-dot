"use strict";
const byId = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
const pending = new Map();
let state = null;
let busy = false;
const labels = {succeeded:"已完成",failed:"失败",uncertain:"需核对",running:"需核对",ready:"待手动运行",skipped:"已跳过"};
const reasons = {due:"到达分析窗口",coalesced:"旧候选已合并",superseded:"已由新候选替代",expired:"超过有效期",dst_gap:"当地时间因夏令时不存在",core_task_state:"已核对运行记录",manual_claim:"手动执行中",interrupted_before_core_record:"中断后结果需核对"};
const workflows = {"demo-news":"合成新闻演示","demo-open-source":"合成开源调研"};

async function api(route, data) {
  const options = {headers:{"X-Local-Token":token},credentials:"omit",cache:"no-store"};
  if (data !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(data);
  }
  const response = await fetch(route, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "本地请求未完成");
  return result;
}

function message(text, error = false) {
  byId("message").textContent = text;
  byId("message").className = error ? "error" : "muted small";
}

function cell(row, value) {
  const td = document.createElement("td");
  td.textContent = value == null ? "—" : String(value);
  row.appendChild(td);
  return td;
}

function empty(tbody, columns, text) {
  const row = document.createElement("tr");
  cell(row, text).colSpan = columns;
  tbody.appendChild(row);
}

function isoInput(id) {
  const value = byId(id).value;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error("请填写完整的 UTC 日期与时间。");
  return value + ":00Z";
}

function controls() {
  for (const button of document.querySelectorAll("#refresh,#inspect,#pause,#preview-plans,#reconcile-plans,[data-run],[data-plan-run]")) button.disabled = busy;
  if (state) for (const button of document.querySelectorAll("[data-run],[data-plan-run]")) button.disabled = busy || state.settings.paused;
  for (const id of ["since","at"]) byId(id).disabled = busy;
}

function clearPreview() {
  byId("preview-panel").hidden = true;
  byId("preview-summary").textContent = "";
}

async function action(callback) {
  if (busy) return;
  busy = true;
  controls();
  try { await callback(); }
  catch (error) { message(error.message + "。如结果不确定，请先刷新或核对记录；页面不会自动重跑。", true); }
  finally { busy = false; controls(); }
}

function occurrences(target, items, actionable) {
  const body = byId(target);
  body.replaceChildren();
  for (const item of [...items].reverse()) {
    const row = document.createElement("tr");
    cell(row, item.plan_id);
    cell(row, item.local_time.replace("T"," ") + " / " + item.timezone);
    cell(row, (labels[item.status] || item.status) + " · " + (reasons[item.reason] || "待核对"));
    if (actionable) {
      const operation = cell(row, "");
      if (item.status === "ready") {
        const button = document.createElement("button");
        button.className = "secondary small";
        button.dataset.planRun = item.id;
        button.textContent = "手动运行合成候选";
        button.addEventListener("click", () => action(async () => {
          const result = await api("/api/plans/run", {id:item.id,at:isoInput("at")});
          await refresh();
          message("候选状态：" + (labels[result.occurrence.status] || result.occurrence.status) + " · " + (reasons[result.occurrence.reason] || "待核对"),
            ["failed","uncertain"].includes(result.occurrence.status));
        }));
        operation.appendChild(button);
      } else operation.textContent = "无需自动重跑";
    }
    body.appendChild(row);
  }
  if (!items.length) empty(body, actionable ? 4 : 3, actionable ? "尚无候选。先预览，再按需登记。" : "该窗口没有候选。");
}

async function refresh() {
  try { state = await api("/api/state"); }
  catch (error) {
    byId("connection").textContent = "本地状态不可用";
    byId("connection").className = "badge warn";
    throw error;
  }
  byId("connection").textContent = "本地服务已连接";
  byId("connection").className = "badge good";
  byId("updated").textContent = "最近读取：" + new Date().toISOString();
  byId("count-total").textContent = state.task_count;
  byId("count-complete").textContent = state.tasks.filter(task => task.state === "succeeded").length;
  byId("count-uncertain").textContent = state.tasks.filter(task => ["ready","running","uncertain"].includes(task.state)).length;
  byId("runner-status").textContent = state.settings.paused ? "手动运行器已暂停" : "手动运行器可用；仅允许合成任务";
  byId("pause").textContent = state.settings.paused ? "恢复手动运行器" : "暂停手动运行器";
  const rows = byId("task-rows");
  rows.replaceChildren();
  for (const task of [...state.tasks].reverse()) {
    const row = document.createElement("tr");
    cell(row, workflows[task.workflow_id] || "合成任务");
    cell(row, task.state === "running" || task.state === "ready" ? "需核对（快照）" : labels[task.state]);
    const created = new Date(task.created_at);
    cell(row,Number.isFinite(created.getTime()) ? created.toISOString().slice(0,19).replace("T"," ") + " UTC" : "时间待核对");
    cell(row, task.task_id.slice(0,8));
    rows.appendChild(row);
  }
  if (!state.tasks.length) empty(rows,4,"尚无任务。可手动运行一个合成演示。");
  const plans = byId("plan-rows");
  plans.replaceChildren();
  for (const plan of state.plan_config.plans) {
    const row = document.createElement("tr");
    cell(row,plan.id);
    cell(row,(plan.cadence === "daily" ? "每日" : "每周" + ["一","二","三","四","五","六","日"][plan.weekday]) + " " + plan.local_time);
    cell(row,plan.timezone);
    cell(row,plan.missed_policy === "coalesce_latest" ? "只保留最新未运行候选" : "迟到超过 " + plan.max_lateness_minutes + " 分钟则跳过");
    plans.appendChild(row);
  }
  byId("watermark").textContent = state.watermark || "尚未登记";
  occurrences("occurrence-rows",state.occurrences,true);
  clearPreview();
}

byId("refresh").addEventListener("click",() => action(async () => {await refresh(); message("状态已刷新。");}));
byId("inspect").addEventListener("click",() => action(async () => {await api("/api/inspect",{}); await refresh(); message("已核对中断记录，没有重跑任务。");}));
byId("pause").addEventListener("click",() => action(async () => {await api("/api/pause",{paused:!state.settings.paused}); await refresh(); message("手动运行器状态已更新，后台调度仍关闭。");}));
for (const button of document.querySelectorAll("[data-run]")) {
  button.addEventListener("click",() => action(async () => {
    const workflow = button.dataset.run;
    if (!pending.has(workflow)) pending.set(workflow,crypto.randomUUID());
    const result = await api("/api/run",{workflow_id:workflow,request_id:pending.get(workflow)});
    pending.delete(workflow);
    await refresh();
    message("合成任务：" + labels[result.task.state] + (result.reused ? "（复用已有记录）" : ""),["failed","uncertain"].includes(result.task.state));
  }));
}
byId("preview-plans").addEventListener("click",() => action(async () => {
  const result = await api("/api/plans/preview",{since:isoInput("since"),at:isoInput("at")});
  occurrences("preview-rows",result.records,false);
  byId("preview-panel").hidden = false;
  byId("preview-summary").textContent = "仅预览 " + result.records.length + " 条；没有保存或执行。" + (result.window.older_history_skipped ? "窗口超出回看上限，更早部分不枚举。" : "");
}));
byId("reconcile-plans").addEventListener("click",() => action(async () => {
  const payload = {at:isoInput("at")};
  if (!state.watermark) payload.since = isoInput("since");
  const result = await api("/api/plans/reconcile",payload);
  await refresh();
  message("候选已登记，没有执行。" + (result.ledger.last_window.older_history_skipped ? "更早的历史已按回看上限跳过，详见账本。" : ""));
}));
const clock = new Date();
for (const id of ["since","at"]) byId(id).addEventListener("input",clearPreview);
byId("at").value = clock.toISOString().slice(0,16);
byId("since").value = new Date(clock.getTime() - 24*60*60*1000).toISOString().slice(0,16);
action(refresh);
