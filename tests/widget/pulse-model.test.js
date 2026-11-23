// Pure-logic tests for widget/pulse/PulseModel.js (QML's JS is ES5, so is this file's
// subject under test; the harness itself may use node APIs). Run: node widget/tests/pulse-model.test.js

const fs = require("fs")
const path = require("path")

const src = fs.readFileSync(path.join(__dirname, "..", "..", "PulseModel.js"), "utf8")
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

// --- prettyApp: reverse-DNS shortening + generic tails + user overrides ------
{
  check("prettyApp agent", prettyApp("org.omarchy.agent"), "agent")
  check("prettyApp chrome pwa", prettyApp("chrome-chatgpt.com__-Default"), "chatgpt")
  check("prettyApp vendor", prettyApp("google-chrome"), "chrome")
  check("prettyApp plain", prettyApp("foot"), "foot")
  check("prettyApp empty", prettyApp(""), "")
  // kitty wrapper with a pinned class: the reverse-DNS tail is a generic
  // word ("Tui"); the product name is the middle segment.
  check("prettyApp generic tail", prettyApp("com.slk.Tui"), "slk")
  check("prettyApp generic tail app", prettyApp("io.github.foo.App"), "foo")
  check("prettyApp generic tail desktop", prettyApp("org.example.Desktop"), "example")
  check("prettyApp non-generic tail", prettyApp("org.example.firefox"), "firefox")
  // A sanitized user map wins over every rule.
  check("prettyApp user override", prettyApp("com.slk.Tui", { "com.slk.Tui": "Slack TUI" }), "Slack TUI")
  check("prettyApp override misses", prettyApp("foot", { "com.slk.Tui": "Slack TUI" }), "foot")
  check("prettyApp null labels", prettyApp("foot", null), "foot")
}

// --- sanitizeAppLabels: the shell.json map is untrusted -----------------------
{
  const good = sanitizeAppLabels({ "com.slk.Tui": "slk", "org.x.Y": "y" })
  check("labels valid map kept", good["com.slk.Tui"], "slk")
  check("labels null", sanitizeAppLabels(null), null)
  check("labels array", sanitizeAppLabels(["slk"]), null)
  check("labels string", sanitizeAppLabels("slk"), null)
  check("labels non-string values dropped", sanitizeAppLabels({ a: 5, b: { x: 1 }, c: "ok" })["c"], "ok")
  check("labels non-string map size", Object.keys(sanitizeAppLabels({ a: 5, b: { x: 1 }, c: "ok" })).length, 1)
  check("labels empty value dropped", sanitizeAppLabels({ a: "  " }), null)
  check("labels overlong value dropped", sanitizeAppLabels({ a: "x".repeat(25) }), null)
  check("labels value at cap kept", sanitizeAppLabels({ a: "x".repeat(24) })["a"], "x".repeat(24))
  check("labels trimmed", sanitizeAppLabels({ " k ": " v " })["k"], "v")
  let many = {}
  for (let i = 0; i < 60; i++) many["k" + i] = "v"
  check("labels count capped", Object.keys(sanitizeAppLabels(many)).length, 50)
}

// --- topApps keeps the raw class as merge key, override only for display ------
{
  const now = new Date()
  now.setHours(10, 5, 0, 0)
  const minutes = [
    { tsMs: new Date(iso(10, 0)).getTime(), kind: 1 },
    { tsMs: new Date(iso(10, 1)).getTime(), kind: 1 },
  ]
  const windows = [{ startMs: new Date(iso(9, 0)).getTime(), durationS: 7200, app: "com.slk.Tui" }]
  const r = topApps(minutes, windows, 5)
  check("topApps merge key stays raw", r.apps[0].app, "com.slk.Tui")
  check("topApps generic-tail label", r.apps[0].label, "slk")
  const r2 = topApps(minutes, windows, 5, { "com.slk.Tui": "slack" })
  check("topApps user label wins", r2.apps[0].label, "slack")
}

// --- parseTermEvents: the terminal-focus bucket is untrusted -------------------
{
  const spans = parseTermEvents([
    { timestamp: iso(10, 0), duration: 90, data: { app: "opencode", terminal: "foot", via: "herdr" } },
    { timestamp: iso(10, 5), duration: 10, data: { app: "nvim", terminal: "foot", via: "bogus" } },
    { timestamp: iso(10, 6), duration: 10, data: { app: "x".repeat(33), terminal: "foot", via: "pty" } },
    { timestamp: iso(10, 7), duration: 10, data: { app: "nvim", via: "pty" } },
    { timestamp: "not a date", duration: 10, data: { app: "nvim", terminal: "foot" } },
    { timestamp: iso(10, 8), duration: 10, data: { app: 5, terminal: "foot" } },
    null,
  ])
  check("term parse keeps valid", spans.length, 2)
  check("term parse app", spans[0].app, "opencode")
  check("term parse end", spans[0].endMs - spans[0].startMs, 90000)
  check("term parse via kept", spans[0].via, "herdr")
  check("term parse unknown via dropped", spans[1].via, "")
  check("term parse non-array", parseTermEvents({}).length, 0)
}

// --- topApps with terminal-focus spans: inner app replaces the emulator --------
{
  const at = (h, m) => new Date(iso(h, m)).getTime()
  const minutes = [0, 1, 2, 3].map((m) => ({ tsMs: at(10, m), kind: 1 }))
  const windows = [{ startMs: at(9, 0), durationS: 7200, app: "foot" }]
  const term = [
    { startMs: at(10, 0), endMs: at(10, 2), app: "opencode", terminal: "foot", via: "herdr" },
    { startMs: at(10, 2), endMs: at(10, 3), app: "nvim", terminal: "foot", via: "herdr" },
  ]
  const r = topApps(minutes, windows, 5, null, term)
  const byKey = {}
  r.apps.forEach((a) => (byKey[a.app] = a))
  check("term inner key", byKey["term:opencode"].activeMinutes, 2)
  check("term inner label", byKey["term:opencode"].label, "opencode")
  check("term inner terminal", byKey["term:opencode"].terminal, "foot")
  check("term inner via", byKey["term:opencode"].via, "herdr")
  check("term second app", byKey["term:nvim"].activeMinutes, 1)
  check("term unresolved stays emulator", byKey["foot"].activeMinutes, 1)
  check("term totals add up", r.totalActive, 4)
  check("term emulator record has no terminal", byKey["foot"].terminal, "")

  const plain = topApps(minutes, windows, 5, null, [])
  check("term none = plain join", plain.apps.length, 1)
  check("term none key", plain.apps[0].app, "foot")

  const other = [{ startMs: at(10, 0), endMs: at(10, 4), app: "nvim", terminal: "kitty", via: "pty" }]
  check("term other terminal ignored", topApps(minutes, windows, 5, null, other).apps[0].app, "foot")

  const caseTerm = [{ startMs: at(10, 0), endMs: at(10, 4), app: "nvim", terminal: "FOOT", via: "pty" }]
  check("term class case-insensitive", topApps(minutes, windows, 5, null, caseTerm).apps[0].app, "term:nvim")

  // a window whose class equals a CLI name must not merge with the inner app
  const clash = [{ startMs: at(9, 0), durationS: 7200, app: "nvim" }]
  const clashTerm = [{ startMs: at(10, 0), endMs: at(10, 4), app: "nvim", terminal: "foot", via: "pty" }]
  check("term key never collides with a window class", topApps(minutes, clash, 5, null, clashTerm).apps[0].app, "nvim")

  // labels map applies to the plain inner name
  const labelled = topApps(minutes, windows, 5, { opencode: "oc" }, term)
  check("term label override", labelled.apps.filter((a) => a.app === "term:opencode")[0].label, "oc")

  // the span covering most of the minute wins
  const split = [
    { startMs: at(10, 0), endMs: at(10, 0) + 15000, app: "nvim", terminal: "foot", via: "pty" },
    { startMs: at(10, 0) + 15000, endMs: at(10, 1), app: "lazygit", terminal: "foot", via: "pty" },
  ]
  check("term majority span wins", topApps([minutes[0]], windows, 5, null, split).apps[0].app, "term:lazygit")

  // apps folded into "Other" are named by the tooltip, largest first
  const manyMinutes = []
  for (let m = 0; m < 100; m++) manyMinutes.push({ tsMs: at(10, m), kind: 1 }) // rolls into 11:xx
  const footLong = { startMs: at(9, 0), durationS: 60 * 70, app: "foot" } // first 70 minutes
  const tinyWindows = [70, 72, 74, 76, 78].map((m) => ({
    startMs: at(10, m), durationS: 120, app: "tiny" + ((m - 70) / 2 + 1),
  }))
  const all = [footLong, ...tinyWindows, { startMs: at(10, 80), durationS: 60 * 30, app: "editor" }]
  const rCap = topApps(manyMinutes, all, 5)
  const footRow = rCap.apps.filter((a) => a.app === "foot")[0]
  check("kept rows carry no parts", footRow.parts, undefined)
  const capRow = rCap.apps.filter((a) => a.app === "other")[0]
  check("other row present", capRow.pct, 10)
  check("other parts capped", capRow.parts.length, 4)
  check("other parts pct rounded", capRow.parts[0].pct, 2)

  const twoTiny = [footLong, tinyWindows[0], tinyWindows[1],
    { startMs: at(10, 74), durationS: 60 * 30, app: "editor" }]
  const rParts = topApps(manyMinutes, twoTiny, 5)
  const partsRow = rParts.apps.filter((a) => a.app === "other")[0]
  check("other parts collected", partsRow.parts.map((p) => p.label).sort().join(","), "tiny1,tiny2")
}

// --- resolveAwUrl: the awUrl setting stays local-only ------------------------
{
  const D = "http://localhost:5600"
  check("awUrl empty", resolveAwUrl(""), D)
  check("awUrl null", resolveAwUrl(null), D)
  check("awUrl localhost kept", resolveAwUrl("http://localhost:5600"), "http://localhost:5600")
  check("awUrl localhost bare", resolveAwUrl("http://localhost"), "http://localhost")
  check("awUrl loopback kept", resolveAwUrl("http://127.0.0.1:9001"), "http://127.0.0.1:9001")
  check("awUrl https localhost kept", resolveAwUrl("https://localhost:1234"), "https://localhost:1234")
  check("awUrl userinfo kept", resolveAwUrl("http://user@localhost:5600"), "http://user@localhost:5600")
  check("awUrl ipv6 loopback kept", resolveAwUrl("http://[::1]:5600"), "http://[::1]:5600")
  check("awUrl ipv4-mapped kept", resolveAwUrl("http://[::ffff:127.0.0.1]:5600"), "http://[::ffff:127.0.0.1]:5600")
  check("awUrl remote host", resolveAwUrl("http://example.com:5600"), D)
  check("awUrl private lan", resolveAwUrl("http://10.0.0.5:5600"), D)
  check("awUrl prefix trick", resolveAwUrl("http://127.0.0.1.evil.com:5600"), D)
  check("awUrl other scheme", resolveAwUrl("ftp://localhost"), D)
  check("awUrl no scheme", resolveAwUrl("javascript:alert(1)"), D)
  check("awUrl garbage", resolveAwUrl("not a url"), D)
  check("awUrl bare ipv6", resolveAwUrl("http://::1:5600"), D)
  check("awUrl ipv6 other", resolveAwUrl("http://[::2]:5600"), D)
}

// --- watcherUpdateState: version sync between widget and installed watcher ----
{
  check("updateState ok", watcherUpdateState("0.1.2", "0.1.2"), "ok")
  check("updateState outdated", watcherUpdateState("0.1.1", "0.1.2"), "outdated")
  check("updateState watcher newer", watcherUpdateState("0.2.0", "0.1.2"), "outdated")
  check("updateState missing installed", watcherUpdateState("", "0.1.2"), "unknown")
  check("updateState missing own", watcherUpdateState("0.1.2", ""), "unknown")
  check("updateState both missing", watcherUpdateState(null, null), "unknown")
  check("updateState whitespace trimmed", watcherUpdateState(" 0.1.2 \n", "0.1.2"), "ok")
  check("updateState garbage installed", watcherUpdateState("garbage", "0.1.2"), "outdated")
}

if (fails.length) {
  console.error("FAIL\n" + fails.join("\n"))
  process.exit(1)
}
console.log("pulse-model tests: all passed")
