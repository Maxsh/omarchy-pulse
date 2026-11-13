// Pure helpers for the pulse widget: bucket discovery, range fetch, and the
// keyboard/mouse/idle split per day. No state, no QML imports — everything
// is passed in, which keeps the data logic reviewable on its own.
//
// The watcher reconstructs a device-ownership timeline and stores per-minute
// seconds (kbS/mouseS/bothS) next to the stock counts; see docs/PLAN.md D10
// and the HCI sources cited in watcher/pulse_watcher/timeline.py. Events from
// the older count-only watcher are classified with the legacy count heuristic.

var DEFAULT_AW_URL = "http://localhost:5600"
var BUCKET_TYPE = "os.hid.input"
var WINDOW_BUCKET_TYPE = "currentwindow"

// Apps below this share of attributed active time fold into "Other";
// "Other" itself only shows when it clears the same bar.
var MIN_APP_SHARE_PCT = 3

// Pointer travel that marks a minute as mouse-driven in the legacy heuristic
// (about a screen crossing on this scale).
var MOVEMENT_THRESHOLD_PX = 400

// Input gaps longer than this are "away" (lunch, meetings, sleep): they drop

// Input gaps longer than this are "away" (lunch, meetings, sleep): they drop
// out of the day's span instead of diluting the split. Matches ActivityWatch's
// AFK threshold.
var AFK_GAP_S = 180

// Simultaneous keyboard+mouse use (bothS) splits evenly for display.
var BOTH_SPLIT = 0.5

function normalizeBase(url) {
  var base = String(url || DEFAULT_AW_URL)
  while (base.charAt(base.length - 1) === "/") base = base.slice(0, -1)
  return base
}

// First bucket of the stock input type, so hostname changes don't matter.
function pickInputBucket(buckets) {
  for (var id in buckets) {
    var bucket = buckets[id]
    if (bucket && bucket.type === BUCKET_TYPE) return id
  }
  return ""
}

// Local midnight today, as unix ms.
function midnightMs(now) {
  var d = new Date(now.getTime())
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// Local midnight `daysBack` days before today (DST-safe: built from date
// parts, not by subtracting fixed milliseconds).
function midnightDaysAgo(now, daysBack) {
  var d = new Date(now.getTime())
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - daysBack)
  return d.getTime()
}

// toISOString() with a "+00:00" offset, matching the watcher's event format.
function isoUtc(ms) {
  return new Date(ms).toISOString().replace("Z", "+00:00")
}

function _getJson(url, callback) {
  var xhr = new XMLHttpRequest()
  xhr.open("GET", url)
  xhr.timeout = 5000
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== XMLHttpRequest.DONE) return
    if (xhr.status !== 200) {
      callback(false, null)
      return
    }
    try {
      callback(true, JSON.parse(xhr.responseText))
    } catch (e) {
      callback(false, null)
    }
  }
  xhr.send()
}

// Resolve the input bucket and fetch the last `daysBack` days (including
// today) of per-minute events; the server-side start filter keeps the
// payload bounded. Calls back with
//   { ok, bucketId, activity, days, total }
// where `activity` is today's record (same shape the bar widget polls with)
// and `days[daysBack - 1]` is today.
function fetch(awUrl, daysBack, callback) {
  var base = normalizeBase(awUrl)
  _getJson(base + "/api/0/buckets/", function(ok, buckets) {
    if (!ok) {
      callback({ ok: false, error: "unreachable" })
      return
    }
    var bucketId = pickInputBucket(buckets)
    if (!bucketId) {
      callback({ ok: false, error: "noInputBucket" })
      return
    }
    var now = new Date()
    var url = base + "/api/0/buckets/" + encodeURIComponent(bucketId)
      + "/events?limit=-1&start=" + encodeURIComponent(isoUtc(midnightDaysAgo(now, daysBack - 1)))
    _getJson(url, function(ok2, events) {
      if (!ok2) {
        callback({ ok: false, error: "unreachable" })
        return
      }
      var analyzed = analyzeWeek(events, now.getTime(), daysBack)
      callback({
        ok: true,
        bucketId: bucketId,
        activity: analyzed.days[analyzed.days.length - 1],
        days: analyzed.days,
        total: analyzed.total,
        todayMinutes: analyzed.todayMinutes,
      })
    })
  })
}

function hasSeconds(data) {
  return typeof data.kbS === "number" || typeof data.mouseS === "number" || typeof data.bothS === "number"
}

// A minute leans keyboard when its keyboard seconds outweigh its mouse
// seconds; simultaneous use (bothS) splits evenly. Count-only events from
// the legacy watcher fall back to comparing counts.
function classifyMinute(data) {
  if (hasSeconds(data)) {
    var kb = (Number(data.kbS) || 0) + (Number(data.bothS) || 0) * BOTH_SPLIT
    var mouse = (Number(data.mouseS) || 0) + (Number(data.bothS) || 0) * BOTH_SPLIT
    if (kb + mouse <= 0) return 0
    return kb >= mouse ? 1 : 2
  }
  var presses = Number(data.presses) || 0
  var clicks = Number(data.clicks) || 0
  var scroll = (Number(data.scrollX) || 0) + (Number(data.scrollY) || 0)
  var movement = (Number(data.deltaX) || 0) + (Number(data.deltaY) || 0)
  var kb = presses
  var mouse = clicks + (scroll > 0 ? 1 : 0) + (movement >= MOVEMENT_THRESHOLD_PX ? 1 : 0)
  if (kb <= 0 && mouse <= 0) return 0
  return kb >= mouse ? 1 : 2
}

// A server timeout after a successful write can store the same minute twice
// (identical data), and a badly stalled reader can emit a late second event
// for a flushed minute. Identical events collapse; differing ones merge by
// summing, with the seconds clamped back to a minute's worth.
function mergeDuplicateMinutes(events) {
  var byStamp = {}
  var out = []
  for (var i = 0; i < events.length; i++) {
    var event = events[i]
    var stamp = String(event.timestamp)
    var prev = byStamp[stamp]
    if (prev === undefined) {
      byStamp[stamp] = event
      out.push(event)
      continue
    }
    if (JSON.stringify(prev.data || {}) === JSON.stringify(event.data || {})) continue
    var merged = {}
    var a = prev.data || {}
    var b = event.data || {}
    for (var key in a) merged[key] = Number(a[key]) || 0
    for (var key2 in b) merged[key2] = (Number(merged[key2]) || 0) + (Number(b[key2]) || 0)
    var total = (Number(merged.kbS) || 0) + (Number(merged.mouseS) || 0) + (Number(merged.bothS) || 0)
    if (total > 60) {
      var scale = 60 / total
      merged.kbS = (Number(merged.kbS) || 0) * scale
      merged.mouseS = (Number(merged.mouseS) || 0) * scale
      merged.bothS = (Number(merged.bothS) || 0) * scale
    }
    prev.data = merged
  }
  return out
}

function emptyDay() {
  return {
    firstTsMs: NaN, lastTsMs: NaN,
    kbS: 0, mouseS: 0, bothS: 0, minutes: [],
    kbMinutes: 0, mouseMinutes: 0, activeMinutes: 0,
    spanMinutes: 0, idleMinutes: 0, kbPct: 0, mousePct: 0, idlePct: 0,
  }
}

// Split per-minute events into per-day keyboard/mouse/idle records for the
// last `daysBack` days (days[0] = oldest, days[last] = today).
//
// Day window: today runs from its first input minute to now; past days run
// from their first to last input minute — with one refinement over plain
// session spans: gaps longer than AFK_GAP_S count as "away" and drop out of
// the span, so lunch or sleep doesn't read as a wall of idle. Minutes without
// qualifying input inside the window are idle. A day with no events stays an
// all-zero "no data" record.
function analyzeWeek(events, nowMs, daysBack) {
  events = mergeDuplicateMinutes(events || [])
  var midnights = []
  for (var d = daysBack - 1; d >= 0; d--) midnights.push(midnightDaysAgo(new Date(nowMs), d))
  var days = []
  for (var b = 0; b < daysBack; b++) days.push(emptyDay())
  var todayMinutes = []  // [{tsMs, kind}] — today's classified minutes, for per-app joins

  for (var i = 0; i < events.length; i++) {
    var event = events[i]
    var ts = Date.parse(String(event.timestamp))
    if (!isFinite(ts)) continue
    var index = -1
    for (var m = 0; m < midnights.length; m++) {
      if (midnights[m] <= ts) index = m
      else break
    }
    if (index < 0) continue
    var day = days[index]
    if (!(day.firstTsMs <= ts)) day.firstTsMs = ts
    if (!(ts <= day.lastTsMs)) day.lastTsMs = ts
    day.minutes.push(ts)
    var data = event.data || {}
    var kind = classifyMinute(data)
    // Timeline events carry their own seconds; legacy count-only events
    // contribute their whole minute to the side their counts classify to.
    if (hasSeconds(data)) {
      day.kbS += Number(data.kbS) || 0
      day.mouseS += Number(data.mouseS) || 0
      day.bothS += Number(data.bothS) || 0
    } else if (kind === 1) {
      day.kbS += 60
    } else if (kind === 2) {
      day.mouseS += 60
    }
    if (kind === 0) continue
    day.activeMinutes += 1
    if (kind === 1) day.kbMinutes += 1
    else day.mouseMinutes += 1
    if (index === days.length - 1) todayMinutes.push({ tsMs: ts, kind: kind })
  }

  for (var k = 0; k < days.length; k++) finalizeDay(days[k], k === days.length - 1, nowMs)
  return { days: days, total: totalOf(days), todayMinutes: todayMinutes }
}

// Gaps between consecutive input minutes longer than AFK_GAP_S are "away":
// only the first AFK_GAP_S of each gap stays in the span as idle.
function awaySeconds(stamps, isToday, nowS, lastS) {
  var ordered = stamps.slice().sort(function(a, b) { return a - b })
  var away = 0
  for (var i = 0; i < ordered.length - 1; i++) {
    var gapS = Math.max(0, (ordered[i + 1] - ordered[i]) / 1000 - 60)
    if (gapS > AFK_GAP_S) away += gapS - AFK_GAP_S
  }
  if (isToday) {
    var trailingS = nowS - (lastS + 60)
    if (trailingS > AFK_GAP_S) away += trailingS - AFK_GAP_S
  }
  return away
}

function finalizeDay(day, isToday, nowMs) {
  if (day.minutes.length === 0) return
  var nowS = nowMs / 1000
  var firstS = day.firstTsMs / 1000
  var lastS = day.lastTsMs / 1000
  var spanS = isToday
    ? Math.ceil((nowS - firstS) / 60) * 60
    : lastS - firstS + 60
  spanS -= awaySeconds(day.minutes, isToday, nowS, lastS)
  var activeS = day.kbS + day.mouseS + day.bothS
  spanS = Math.max(spanS, activeS)
  var kbS = day.kbS + day.bothS * BOTH_SPLIT
  var mouseS = day.mouseS + day.bothS * BOTH_SPLIT
  day.spanMinutes = spanS / 60
  day.kbMinutes = kbS / 60
  day.mouseMinutes = mouseS / 60
  day.idleMinutes = Math.max(0, (spanS - activeS) / 60)
  day.kbPct = Math.round(kbS * 100 / spanS)
  day.mousePct = Math.round(mouseS * 100 / spanS)
  // Rounding the first two can drift off 100; idle absorbs the remainder.
  day.idlePct = Math.max(0, 100 - day.kbPct - day.mousePct)
}

// Week total: summed minutes across the per-day windows, as percentages.
function totalOf(days) {
  var total = {
    kbS: 0, mouseS: 0, bothS: 0,
    kbMinutes: 0, mouseMinutes: 0, idleMinutes: 0, activeMinutes: 0,
    kbPct: 0, mousePct: 0, idlePct: 0,
  }
  var spanS = 0
  for (var i = 0; i < days.length; i++) {
    total.kbS += days[i].kbS
    total.mouseS += days[i].mouseS
    total.bothS += days[i].bothS
    total.kbMinutes += days[i].kbMinutes
    total.mouseMinutes += days[i].mouseMinutes
    total.idleMinutes += days[i].idleMinutes
    total.activeMinutes += days[i].activeMinutes
    spanS += days[i].spanMinutes * 60
  }
  var sum = total.kbS + total.mouseS + total.bothS
  if (sum > 0 && spanS > 0) {
    var kbS = total.kbS + total.bothS * BOTH_SPLIT
    var mouseS = total.mouseS + total.bothS * BOTH_SPLIT
    total.kbPct = Math.round(kbS * 100 / spanS)
    total.mousePct = Math.round(mouseS * 100 / spanS)
    total.idlePct = Math.max(0, 100 - total.kbPct - total.mousePct)
  }
  return total
}

// Fetch the window-focus spans for the last `daysBack` days from the stock
// currentwindow bucket (written by pulse-window-watcher). Focus changes are
// rare, so this stays small even over weeks. Calls back with
// { ok, bucketId, windows } where windows = [{startMs, durationS, app}]
// sorted by start; empty app records are dropped.
function fetchWindowEvents(awUrl, daysBack, callback) {
  var base = normalizeBase(awUrl)
  _getJson(base + "/api/0/buckets/", function(ok, buckets) {
    if (!ok) {
      callback({ ok: false, error: "unreachable" })
      return
    }
    var bucketId = ""
    for (var id in buckets) {
      var bucket = buckets[id]
      if (bucket && bucket.type === WINDOW_BUCKET_TYPE) {
        bucketId = id
        break
      }
    }
    if (bucketId === "") {
      callback({ ok: false, error: "noWindowBucket" })
      return
    }
    var now = new Date()
    var url = base + "/api/0/buckets/" + encodeURIComponent(bucketId)
      + "/events?limit=-1&start=" + encodeURIComponent(isoUtc(midnightDaysAgo(now, daysBack - 1)))
    _getJson(url, function(ok2, events) {
      if (!ok2) {
        callback({ ok: false, error: "unreachable" })
        return
      }
      var spans = []
      for (var i = 0; i < events.length; i++) {
        var event = events[i]
        var ts = Date.parse(String(event.timestamp))
        var app = String((event.data || {}).app || "")
        if (!isFinite(ts) || app === "") continue
        spans.push({ startMs: ts, durationS: Number(event.duration) || 0, app: app })
      }
      spans.sort(function(a, b) { return a.startMs - b.startMs })
      callback({ ok: true, bucketId: bucketId, windows: spans })
    })
  })
}

// Display label for an app class: shortened for readability, identity-safe
// (the raw class stays the merge key and lives in the tooltip).
//   "org.omarchy.agent"            -> "agent"
//   "chrome-chatgpt.com__-Default" -> "chatgpt"   (Chrome/PWA classes)
//   "google-chrome"                -> "chrome"    (vendor prefixes)
//   "foot", "zen", "aw-qt"         -> unchanged
function prettyApp(appClass) {
  var name = String(appClass || "").trim()
  if (name === "") return ""
  if (name.indexOf("chrome-") === 0) {
    name = name.slice("chrome-".length)
    var cutoff = name.indexOf("__")
    if (cutoff !== -1) name = name.slice(0, cutoff)
    var tld = name.lastIndexOf(".")
    if (tld !== -1) name = name.slice(0, tld)  // chatgpt.com -> chatgpt
    return name
  }
  var vendors = ["google-", "microsoft-"]
  for (var v = 0; v < vendors.length; v++) {
    if (name.indexOf(vendors[v]) === 0) {
      name = name.slice(vendors[v].length)
      break
    }
  }
  var dot = name.lastIndexOf(".")
  if (dot !== -1 && dot + 1 < name.length) return name.slice(dot + 1)
  return name
}

// Attribute per-minute input records to the app focused when the minute
// started — a minute-granularity approximation: a minute with app-switching
// inside it goes entirely to one app. Returns { apps, totalActive, maxShare }
// with apps sorted by active minutes: apps under MIN_APP_SHARE_PCT fold into
// "Other" (shown only when it clears the threshold too), the list is capped
// at topN; each record carries pct (share of attributed active time), its
// own keyboard/mouse split as float shares (kbShare/mouseShare, for the
// diverging bars) and a shortened display label.
//
// `minutes` and `windows` may arrive in any order (the API returns events
// newest-first) — both are sorted here before the two-pointer walk.
function topApps(minutes, windows, topN) {
  var sortedMinutes = minutes.slice().sort(function(a, b) { return a.tsMs - b.tsMs })
  var sortedWindows = windows.slice().sort(function(a, b) { return a.startMs - b.startMs })
  var byApp = {}
  var winIndex = -1
  for (var i = 0; i < sortedMinutes.length; i++) {
    var minute = sortedMinutes[i]
    while (winIndex + 1 < sortedWindows.length && sortedWindows[winIndex + 1].startMs <= minute.tsMs) winIndex++
    var app = winIndex >= 0 && sortedWindows[winIndex].startMs <= minute.tsMs ? sortedWindows[winIndex].app : ""
    if (app === "") continue
    var record = byApp[app]
    if (!record) {
      record = byApp[app] = { app: app, label: prettyApp(app), kbMinutes: 0, mouseMinutes: 0, activeMinutes: 0 }
    }
    record.activeMinutes += 1
    if (minute.kind === 1) record.kbMinutes += 1
    else record.mouseMinutes += 1
  }

  var list = []
  for (var key in byApp) list.push(byApp[key])
  list.sort(function(a, b) { return b.activeMinutes - a.activeMinutes })

  var totalActive = 0
  for (var j = 0; j < list.length; j++) totalActive += list[j].activeMinutes

  // Partition: apps at or above the threshold become rows (capped at topN);
  // everything below the threshold — and everything beyond the cap — folds
  // into "Other", which itself only shows when it clears the threshold.
  var kept = []
  var other = { app: "other", label: "other", kbMinutes: 0, mouseMinutes: 0, activeMinutes: 0 }
  var maxShare = 0
  for (var k = 0; k < list.length; k++) {
    var rec = withPercentages(list[k], totalActive)
    if (rec.pct >= MIN_APP_SHARE_PCT && kept.length < topN) {
      kept.push(rec)
    } else {
      other.kbMinutes += rec.kbMinutes
      other.mouseMinutes += rec.mouseMinutes
      other.activeMinutes += rec.activeMinutes
    }
  }
  if (other.activeMinutes > 0) {
    var otherRec = withPercentages(other, totalActive)
    if (otherRec.pct >= MIN_APP_SHARE_PCT) kept.push(otherRec)
  }
  for (var m = 0; m < kept.length; m++) {
    maxShare = Math.max(maxShare, kept[m].kbTotalShare, kept[m].mouseTotalShare)
  }
  return { apps: kept, totalActive: totalActive, maxShare: maxShare }
}

function withPercentages(record, totalActive) {
  record.pct = totalActive > 0 ? Math.round(record.activeMinutes * 100 / totalActive) : 0
  // Internal split (tooltip: the app's own keyboard/mouse ratio)…
  record.kbShare = record.activeMinutes > 0 ? record.kbMinutes * 100 / record.activeMinutes : 0
  record.mouseShare = 100 - record.kbShare
  // …and total-relative shares (the diverging bars: length = the app's
  // keyboard / mouse minutes as a share of all attributed active minutes).
  record.kbTotalShare = totalActive > 0 ? record.kbMinutes * 100 / totalActive : 0
  record.mouseTotalShare = totalActive > 0 ? record.mouseMinutes * 100 / totalActive : 0
  return record
}
