// Pure helpers for the pulse widget: bucket discovery, range fetch, and the
// keyboard/mouse/idle split per day. No state, no QML imports — everything
// is passed in, which keeps the data logic reviewable on its own.

var DEFAULT_AW_URL = "http://localhost:5600"
var BUCKET_TYPE = "os.hid.input"
var WINDOW_BUCKET_TYPE = "currentwindow"

// Pointer travel that marks a minute as mouse-driven even without clicks
// (about a screen crossing on this scale).
var MOVEMENT_THRESHOLD_PX = 400

// Apps below this share of attributed active time fold into "Other";
// "Other" itself only shows when it clears the same bar.
var MIN_APP_SHARE_PCT = 3

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

// One minute is keyboard when key presses outweigh mouse work; scroll or a
// meaningful pointer travel counts as one unit of mouse work. Returns
// 0 = idle, 1 = keyboard, 2 = mouse. Never sees which keys — counts only.
function classifyMinute(data) {
  var presses = Number(data.presses) || 0
  var clicks = Number(data.clicks) || 0
  var scroll = (Number(data.scrollX) || 0) + (Number(data.scrollY) || 0)
  var movement = (Number(data.deltaX) || 0) + (Number(data.deltaY) || 0)
  var kb = presses
  var mouse = clicks + (scroll > 0 ? 1 : 0) + (movement >= MOVEMENT_THRESHOLD_PX ? 1 : 0)
  if (kb <= 0 && mouse <= 0) return 0
  return kb >= mouse ? 1 : 2
}

function emptyDay() {
  return {
    firstTsMs: NaN, lastTsMs: NaN, kbMinutes: 0, mouseMinutes: 0,
    activeMinutes: 0, spanMinutes: 0, idleMinutes: 0, kbPct: 0, mousePct: 0, idlePct: 0,
  }
}

// Split per-minute events into per-day keyboard/mouse/idle records for the
// last `daysBack` days (days[0] = oldest, days[last] = today).
//
// Day window: today runs from its first input minute to now; past days run
// from their first to last input minute — off-hours sleep never dilutes the
// split. Minutes without events inside a day's window are idle. A day with
// no events at all stays an all-zero "no data" record.
function analyzeWeek(events, nowMs, daysBack) {
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
    var kind = classifyMinute(event.data || {})
    if (kind === 0) continue
    day.activeMinutes += 1
    if (kind === 1) day.kbMinutes += 1
    else day.mouseMinutes += 1
    if (index === days.length - 1) todayMinutes.push({ tsMs: ts, kind: kind })
  }

  for (var k = 0; k < days.length; k++) finalizeDay(days[k], k === days.length - 1, nowMs)
  return { days: days, total: totalOf(days), todayMinutes: todayMinutes }
}

function finalizeDay(day, isToday, nowMs) {
  if (day.activeMinutes === 0) return
  var span = isToday
    ? Math.ceil((nowMs - day.firstTsMs) / 60000)
    : Math.round((day.lastTsMs - day.firstTsMs) / 60000) + 1
  day.spanMinutes = Math.max(span, day.activeMinutes)
  day.idleMinutes = day.spanMinutes - day.activeMinutes
  day.kbPct = Math.round(day.kbMinutes * 100 / day.spanMinutes)
  day.mousePct = Math.round(day.mouseMinutes * 100 / day.spanMinutes)
  // Rounding the first two can drift off 100; idle absorbs the remainder.
  day.idlePct = Math.max(0, 100 - day.kbPct - day.mousePct)
}

// Week total: summed minutes across the per-day windows, as percentages.
function totalOf(days) {
  var total = { kbMinutes: 0, mouseMinutes: 0, idleMinutes: 0, activeMinutes: 0, kbPct: 0, mousePct: 0, idlePct: 0 }
  for (var i = 0; i < days.length; i++) {
    total.kbMinutes += days[i].kbMinutes
    total.mouseMinutes += days[i].mouseMinutes
    total.idleMinutes += days[i].idleMinutes
    total.activeMinutes += days[i].activeMinutes
  }
  var sum = total.kbMinutes + total.mouseMinutes + total.idleMinutes
  if (sum > 0) {
    total.kbPct = Math.round(total.kbMinutes * 100 / sum)
    total.mousePct = Math.round(total.mouseMinutes * 100 / sum)
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
