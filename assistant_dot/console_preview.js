"use strict";

// UTC-only hypothetical calculations. No timers, persistence, requests or execution.
function previewSchedule(reference, dailyTime, weeklyDay, weeklyTime, count = 3) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(reference)) {
    throw new Error("请输入完整的 UTC 参考日期与时间。");
  }
  const start = new Date(reference + ":00Z");
  if (!Number.isFinite(start.getTime()) || start.toISOString().slice(0, 16) !== reference ||
      start.getUTCFullYear() < 1970 || start.getUTCFullYear() > 9998) {
    throw new Error("参考日期无效；支持 1970 至 9998 年。");
  }
  const clock = value => {
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) {
      throw new Error("演练时间需要使用 24 小时制 HH:MM。");
    }
    return value.split(":").map(Number);
  };
  const daily = clock(dailyTime);
  const weekly = clock(weeklyTime);
  if (!Number.isInteger(weeklyDay) || weeklyDay < 0 || weeklyDay > 6 ||
      !Number.isInteger(count) || count < 1 || count > 7) {
    throw new Error("请选择星期与 1 至 7 次预览。");
  }
  const day = 24 * 60 * 60 * 1000;
  const dailyFirst = new Date(start);
  dailyFirst.setUTCHours(daily[0], daily[1], 0, 0);
  if (dailyFirst <= start) dailyFirst.setUTCDate(dailyFirst.getUTCDate() + 1);
  const weeklyFirst = new Date(start);
  weeklyFirst.setUTCDate(weeklyFirst.getUTCDate() + (weeklyDay - start.getUTCDay() + 7) % 7);
  weeklyFirst.setUTCHours(weekly[0], weekly[1], 0, 0);
  if (weeklyFirst <= start) weeklyFirst.setUTCDate(weeklyFirst.getUTCDate() + 7);
  const times = (first, spacing) => Array.from({length: count}, (_, index) =>
    new Date(first.getTime() + index * spacing).toISOString());
  return {daily: times(dailyFirst, day), weekly: times(weeklyFirst, day * 7)};
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {previewSchedule};
}

if (typeof document !== "undefined") {
  const reference = document.getElementById("reference");
  const result = document.getElementById("preview-results");
  const error = document.getElementById("preview-error");
  document.getElementById("preview-button").addEventListener("click", () => {
    result.replaceChildren();
    error.textContent = "";
    try {
      const preview = previewSchedule(reference.value,
        document.getElementById("daily-time").value,
        Number(document.getElementById("weekly-day").value),
        document.getElementById("weekly-time").value,
        Number(document.getElementById("preview-count").value));
      for (const [label, dates] of [["每日新闻 · 假设", preview.daily], ["每周开源检查 · 假设", preview.weekly]]) {
        const block = document.createElement("section");
        const heading = document.createElement("h4");
        heading.textContent = label;
        block.appendChild(heading);
        const list = document.createElement("ol");
        for (const date of dates) {
          const item = document.createElement("li");
          item.textContent = date.replace("T", " ").replace(":00.000Z", " UTC");
          list.appendChild(item);
        }
        block.appendChild(list);
        result.appendChild(block);
      }
    } catch (failure) {
      error.textContent = failure.message;
    }
  });
  document.getElementById("task-filter").addEventListener("change", event => {
    for (const row of document.querySelectorAll("[data-workflow]")) {
      row.hidden = event.target.value !== "all" && row.dataset.workflow !== event.target.value;
    }
  });
}
