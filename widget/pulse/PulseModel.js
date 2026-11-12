// Pure helpers for the pulse widget: bucket discovery, range fetch, and the
// keyboard/mouse/idle split per day. No state, no QML imports — everything
// is passed in, which keeps the data logic reviewable on its own.

var DEFAULT_AW_URL = "http://localhost:5600"
var BUCKET_TYPE = "os.hid.input"

// Pointer travel that marks a minute as mouse-driven even without clicks
// (about a screen crossing on this scale).
var MOVEMENT_THRESHOLD_PX = 400

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
  }

  for (var k = 0; k < days.length; k++) finalizeDay(days[k], k === days.length - 1, nowMs)
  return { days: days, total: totalOf(days) }
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
