// Pure-logic tests for widget/pulse/PulseModel.js (QML's JS is ES5, so is this file's
// subject under test; the harness itself may use node APIs). Run: node widget/tests/pulse-model.test.js

const fs = require("fs")
const path = require("path")

const src = fs.readFileSync(path.join(__dirname, "..", "pulse", "PulseModel.js"), "utf8")
eval(src)

const fails = []
function check(name, actual, expected, tol = 0) {
  const ok =
    typeof expected === "number" && tol > 0
      ? Math.abs(actual - expected) <= tol
      : actual === expected
  if (!ok) fails.push(`${name}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`)
}

function iso(h, m) {
  const d = new Date()
  d.setHours(h, m, 0, 0)
  return d.toISOString().replace("Z", "+00:00")
}

// --- duplicate merge --------------------------------------------------------
{
  const a = { timestamp: iso(10, 0), data: { presses: 5, kbS: 60 } }
  const dup = { timestamp: iso(10, 0), data: { presses: 5, kbS: 60 } } // retry copy
  const partial = { timestamp: iso(10, 1), data: { kbS: 5 } }
  const orig = { timestamp: iso(10, 1), data: { kbS: 50, presses: 1 } }
  const merged = mergeDuplicateMinutes([a, dup, partial, orig])
  check("dedupe length", merged.length, 2)
  check("identical duplicate dropped, first kept", merged[0].data.kbS, 60)
  check("partial merge sums kbS", merged[1].data.kbS, 55)
}

// --- today: seconds, away gaps, both split, duplicates ------------------------
{
  const now = new Date()
  now.setHours(11, 7, 0, 0)
  const events = [
    { timestamp: iso(10, 0), data: { presses: 10, kbS: 60, mouseS: 0, bothS: 0 } },
    { timestamp: iso(10, 0), data: { presses: 10, kbS: 60, mouseS: 0, bothS: 0 } }, // retry copy
    { timestamp: iso(10, 1), data: { kbS: 30, mouseS: 30, bothS: 0 } },
    { timestamp: iso(11, 0), data: { kbS: 0, mouseS: 60, bothS: 0 } },
    { timestamp: iso(11, 5), data: { kbS: 20, mouseS: 20, bothS: 20 } },
  ]
  const r = analyzeWeek(events, now.getTime(), 1)
  const day = r.days[0]
  // window 10:00..11:07 = 67 min; gaps 10:01->11:00 (58 min) and 11:00->11:05
  // (3 min) leave 3 min idle each and drop the rest: away = 56 min
  check("spanMinutes", day.spanMinutes, 11)
  check("activeMinutes", day.activeMinutes, 4)
  check("kbMinutes", day.kbMinutes, 2) // (110 + 20/2)/60
  check("mouseMinutes", day.mouseMinutes, 2)
  check("idleMinutes", day.idleMinutes, 7)
  check("kbPct", day.kbPct, 18) // 120/660
  check("mousePct", day.mousePct, 18)
  check("idlePct", day.idlePct, 64)
  check("todayMinutes count", r.todayMinutes.length, 4)
  check("todayMinutes kinds", r.todayMinutes.map((x) => x.kind).join(","), "1,1,2,1")
}

// --- away: an overnight gap collapses to AFK idle -----------------------------
{
  const now = new Date()
  now.setHours(9, 2, 0, 0)
  const events = [
    { timestamp: iso(0, 30), data: { presses: 1, kbS: 30, mouseS: 0, bothS: 0 } },
    { timestamp: iso(9, 0), data: { kbS: 0, mouseS: 30, bothS: 0 } },
  ]
  const day = analyzeWeek(events, now.getTime(), 1).days[0]
  // window 00:30..09:02 = 512 min; the 8.5 h gap keeps 3 min idle, drops the rest
  check("away spanMinutes", day.spanMinutes, 6)
  check("away activeMinutes", day.activeMinutes, 2)
  check("away idleMinutes", day.idleMinutes, 5)
  check("away kbPct", day.kbPct, 8) // 30 s of 6 min
  check("away mousePct", day.mousePct, 8)
  check("away idlePct", day.idlePct, 84)
}

// --- legacy count-only events -------------------------------------------------
{
  const now = new Date()
  now.setHours(10, 5, 0, 0)
  const events = [
    { timestamp: iso(10, 0), data: { presses: 30, clicks: 2 } }, // legacy: keyboard
    { timestamp: iso(10, 2), data: { clicks: 40, scrollY: 9 } }, // legacy: mouse
  ]
  const day = analyzeWeek(events, now.getTime(), 1).days[0]
  check("legacy activeMinutes", day.activeMinutes, 2)
  check("legacy kbMinutes", day.kbMinutes, 1)
  check("legacy mouseMinutes", day.mouseMinutes, 1)
  check("legacy spanMinutes", day.spanMinutes, 5) // today: first minute .. now
  check("legacy kbPct", day.kbPct, 20)
  check("legacy mousePct", day.mousePct, 20)
  check("legacy idlePct", day.idlePct, 60)
}

// --- week totals --------------------------------------------------------------
{
  const now = new Date()
  now.setHours(11, 7, 0, 0)
  const events = [
    { timestamp: iso(10, 0), data: { kbS: 60, mouseS: 0, bothS: 0 } },
    { timestamp: iso(10, 1), data: { kbS: 0, mouseS: 30, bothS: 0 } },
  ]
  const r = analyzeWeek(events, now.getTime(), 3)
  const total = r.total
  // today's window 10:00..11:07 with the last 65 min away -> 5 min counted span
  check("total kbPct", total.kbPct, 20) // 60 s of 5 min
  check("total mousePct", total.mousePct, 10)
  check("total idlePct", total.idlePct, 70)
  check("total activeMinutes", total.activeMinutes, 2)
}

// --- empty days stay "no data" -------------------------------------------------
{
  const now = new Date()
  const r = analyzeWeek([], now.getTime(), 2)
  check("empty days", r.days.filter((d) => d.spanMinutes === 0 && d.activeMinutes === 0).length, 2)
  check("empty total", r.total.activeMinutes, 0)
}

if (fails.length) {
  console.error("FAIL\n" + fails.join("\n"))
  process.exit(1)
}
console.log("pulse-model tests: all passed")
