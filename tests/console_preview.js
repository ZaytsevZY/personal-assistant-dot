"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const {previewSchedule} = require("../assistant_dot/console_preview.js");

let result = previewSchedule("2026-11-02T08:00", "08:00", 1, "09:00", 3);
assert.deepEqual(result.daily, ["2026-11-03T08:00:00.000Z", "2026-11-04T08:00:00.000Z", "2026-11-05T08:00:00.000Z"]);
assert.equal(result.weekly[0], "2026-11-02T09:00:00.000Z");
result = previewSchedule("2026-11-02T09:00", "08:00", 1, "09:00");
assert.equal(result.weekly[0], "2026-11-09T09:00:00.000Z");
assert.equal(previewSchedule("2028-02-28T23:59", "00:00", 0, "00:00").daily[0], "2028-02-29T00:00:00.000Z");
assert.equal(previewSchedule("2026-12-31T23:59", "00:00", 0, "00:00").daily[0], "2027-01-01T00:00:00.000Z");
assert.equal(previewSchedule("2026-11-07T23:00", "08:00", 0, "09:00").weekly[0], "2026-11-08T09:00:00.000Z");
for (const reference of ["2026-02-30T12:00", "invalid", "2026-11-02T08:00Z", "1969-01-01T00:00", "9999-01-01T00:00"]) {
  assert.throws(() => previewSchedule(reference, "08:00", 1, "09:00"));
}
for (const invalid of ["24:00", "8:00", "08:60", "bad"]) {
  assert.throws(() => previewSchedule("2026-11-02T08:00", invalid, 1, "09:00"));
  assert.throws(() => previewSchedule("2026-11-02T08:00", "08:00", 1, invalid));
}
for (const invalid of [-1, 7, 1.5, "1"]) {
  assert.throws(() => previewSchedule("2026-11-02T08:00", "08:00", invalid, "09:00"));
}
for (const invalid of [0, 8, 1.5, "3"]) {
  assert.throws(() => previewSchedule("2026-11-02T08:00", "08:00", 1, "09:00", invalid));
}
assert.equal(previewSchedule("2026-11-02T08:00", "08:00", 1, "09:00", 7).daily.length, 7);
console.log("PASS: UTC preview boundaries, equality, leap day, year rollover and invalid input");

// Exercise event wiring without a browser, network access or a server.
class Element {
  constructor(value = "") { this.value = value; this.children = []; this.handlers = {}; this.textContent = ""; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  addEventListener(name, callback) { this.handlers[name] = callback; }
}
const elements = Object.fromEntries(["reference", "preview-results", "preview-error", "preview-button", "daily-time", "weekly-day", "weekly-time", "preview-count", "task-filter"].map(id => [id, new Element()]));
elements.reference.value = "2026-11-02T08:00";
elements["daily-time"].value = "08:00";
elements["weekly-day"].value = "1";
elements["weekly-time"].value = "09:00";
elements["preview-count"].value = "3";
const rows = [{dataset: {workflow: "demo-news"}}, {dataset: {workflow: "demo-open-source"}}];
const document = {
  getElementById: id => { assert.ok(elements[id], "known DOM ID"); return elements[id]; },
  createElement: () => new Element(),
  querySelectorAll: selector => { assert.equal(selector, "[data-workflow]"); return rows; }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../assistant_dot/console_preview.js"), "utf8"), {document});
elements["preview-button"].handlers.click();
assert.equal(elements["preview-results"].children.length, 2);
assert.equal(elements["preview-results"].children[0].children[1].children.length, 3);
assert.equal(elements["preview-results"].children[0].children[1].children[0].textContent, "2026-11-03 08:00 UTC");
elements.reference.value = "invalid";
elements["preview-button"].handlers.click();
assert.equal(elements["preview-results"].children.length, 0);
assert.ok(elements["preview-error"].textContent.length > 0);
elements["task-filter"].handlers.change({target: {value: "demo-news"}});
assert.equal(rows[0].hidden, false);
assert.equal(rows[1].hidden, true);
elements["task-filter"].handlers.change({target: {value: "all"}});
assert.ok(rows.every(row => row.hidden === false));
console.log("PASS: offline DOM event wiring, preview output, error clearing and task filtering");
