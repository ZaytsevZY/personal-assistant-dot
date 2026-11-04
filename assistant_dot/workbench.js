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
  for (const button of document.querySelectorAll("#refresh,#inspect,#pause,#preview-plans,#reconcile-plans,#preview-news,[data-run],[data-plan-run]")) button.disabled = busy;
  if (state) for (const button of document.querySelectorAll("[data-run],[data-plan-run]")) button.disabled = busy || state.settings.paused;
  for (const id of ["since","at"]) byId(id).disabled = busy;
  byId("news-at").disabled = busy;
  for (const input of document.querySelectorAll('[name="news-interest"]')) input.disabled = busy;
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
  clearNews();
  if (!byId("news-at").value) byId("news-at").value = state.news_preview.reference_at.slice(0,16);
}

const topicLabels = {politics:"时政",economics:"经济",technology:"科技"};
const laneLabels = {major_public:"重大公共信息",personal_relevant:"本次明确兴趣",exploration:"相邻探索"};
const newsWarnings = {synthetic_only_not_fact_checked:"合成内容，未经事实核查",single_origin_chain:"只有一条原始来源链",event_time_unknown:"事件日期未知",future_event_not_yet_occurred:"事件在分析时点尚未发生",event_time_disagreement:"报道的事件日期不同，需核对",old_event_recent_reporting:"旧事件近期发布报道，不代表事件刚刚发生"};
const newsWhy = {major_flag_independent_of_interests:"来源样例标为重大；不受本次兴趣影响",explicit_topic_for_this_preview:"匹配本次主动选择的主题",outside_explicit_topics:"本次明确兴趣之外的探索；没有推断画像"};

function node(parent, tag, value, className = "") {
  const element = document.createElement(tag);
  element.textContent = value;
  element.className = className;
  parent.appendChild(element);
  return element;
}

function clearNews() {
  byId("news-result").hidden = true;
  byId("news-summary").textContent = "";
}

function renderNews(result) {
  const sources = new Map(result.sources.map(source => [source.id, source]));
  const coverage = byId("news-coverage");
  coverage.replaceChildren();
  for (const [topic, value] of Object.entries(result.coverage)) {
    const card = node(coverage,"article","","module");
    node(card,"h4",topicLabels[topic]);
    node(card,"p",value.major_events ? value.major_events + " 个合成重大事件候选" : "没有符合条件的重大候选，覆盖有缺口");
    node(card,"p","不代表真实新闻已覆盖","small muted");
  }
  byId("news-summary").textContent = "合成分析时点：" + result.as_of + " · 未联网、未保存、未投递；置信度未评估。";
  byId("news-sources").textContent = "来源状态：" + result.source_status.map(source => sources.get(source.source_id).name + (source.status === "unavailable" ? "不可用" : "已载入合成样例")).join("；") + "。过滤报道：" + Object.entries(result.filtered_reports).map(([key,count]) => ({invalid:"无效",future:"尚未发布",stale:"过期",duplicate:"重复",conflict:"冲突"}[key]) + count).join(" / ") + "。兴趣/探索超限未展示：" + result.omitted_events.personal_relevant + "/" + result.omitted_events.exploration + "。";
  const lanes = byId("news-lanes");
  lanes.replaceChildren();
  for (const [lane, events] of Object.entries(result.lanes)) {
    const section = node(lanes,"section","","news-lane");
    node(section,"h3",laneLabels[lane] + " · " + events.length);
    if (!events.length) node(section,"p",lane === "personal_relevant" ? "没有匹配本次明确兴趣的候选；未选择兴趣时不生成此类推荐。" : "没有符合条件的候选。","muted small");
    for (const event of events) {
      const card = node(section,"article","","news-card");
      node(card,"span",topicLabels[event.topic],"badge");
      node(card,"h4",event.title);
      node(card,"p","推荐依据：" + newsWhy[event.why],"small");
      node(card,"p","声明的原始来源链：" + event.origin_chain_count + "；不同来源链不等于已独立核实。","small muted");
      node(card,"p",event.warnings.map(value => newsWarnings[value]).join("；"),"small muted");
      for (const report of event.reports) {
        const source = sources.get(report.source_id);
        const detail = node(card,"details","");
        node(detail,"summary",source.name + " · 查看报道、事实陈述与评论");
        node(detail,"p","报道标题：" + report.title,"small");
        node(detail,"p","报道链接：" + report.url + " · 原始链 " + source.origin_chain_id,"small mono");
        node(detail,"p","事件时间：" + (report.event_time || "未知，未推断") + "；发布时间：" + report.published_at + "；检索时间：无，未联网检索","small");
        for (const statement of report.statements) node(detail,"p",(statement.kind === "reported_fact" ? "来源事实陈述（未核实）：" : "来源评论：") + statement.text,statement.kind === "commentary" ? "small commentary" : "small");
        for (const uncertainty of report.uncertainties) node(detail,"p","不确定性：" + uncertainty,"small muted");
        if (report.correction_of) node(detail,"p","更正引用：" + report.correction_of + "（保留引用，不自动认定更正已生效）","small");
      }
    }
  }
  byId("news-result").hidden = false;
}

byId("preview-news").addEventListener("click",() => action(async () => {
  clearNews();
  const interests = [...document.querySelectorAll('[name="news-interest"]')].filter(input => input.checked).map(input => input.value);
  renderNews(await api("/api/news/preview",{at:isoInput("news-at"),interests}));
  message("已生成合成新闻预览；没有创建任务、保存兴趣或改变检索方向。");
}));
byId("news-at").addEventListener("input",clearNews);
for (const input of document.querySelectorAll('[name="news-interest"]')) input.addEventListener("change",clearNews);

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
