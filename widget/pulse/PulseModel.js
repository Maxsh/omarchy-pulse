// Pure helpers for the pulse widget: bucket discovery, today's fetch, and
// the keyboard/mouse/idle split. No state, no QML imports — everything is
// passed in, which keeps the data logic reviewable on its own.

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

// Resolve the input bucket, fetch today's per-minute events (server-side
// start filter keeps the payload small), and analyze. Calls back with
// { ok, bucketId, activity } or { ok: false, error }.
function fetchToday(awUrl, callback) {
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
      + "/events?limit=-1&start=" + encodeURIComponent(isoUtc(midnightMs(now)))
    _getJson(url, function(ok2, events) {
      if (!ok2) {
        callback({ ok: false, error: "unreachable" })
        return
      }
      var midnight = midnightMs(now)
      callback({ ok: true, bucketId: bucketId, activity: analyzeEvents(events, midnight, now.getTime()) })
    })
  })
}

// Classify every per-minute event as keyboard or mouse by dominant input,
// then express the split as percentages of the session so far: the span
// from the first input minute of the day to now. Minutes inside that span
// without any event are idle. Never records which keys — counts only.
//
// A minute is keyboard when key presses outweigh mouse work; scroll or a
// meaningful pointer movement counts as one unit of mouse work.
function analyzeEvents(events, sinceMs, nowMs) {
  var out = {
    firstTsMs: NaN, kbMinutes: 0, mouseMinutes: 0, activeMinutes: 0,
    spanMinutes: 0, idleMinutes: 0, kbPct: 0, mousePct: 0, idlePct: 0,
  }
  for (var i = 0; i < events.length; i++) {
    var event = events[i]
    var ts = Date.parse(String(event.timestamp))
    if (!isFinite(ts) || ts < sinceMs) continue
    if (!(out.firstTsMs <= ts)) out.firstTsMs = ts
    var data = event.data || {}
    var presses = Number(data.presses) || 0
    var clicks = Number(data.clicks) || 0
    var scroll = (Number(data.scrollX) || 0) + (Number(data.scrollY) || 0)
    var movement = (Number(data.deltaX) || 0) + (Number(data.deltaY) || 0)
    var kb = presses
    var mouse = clicks + (scroll > 0 ? 1 : 0) + (movement >= MOVEMENT_THRESHOLD_PX ? 1 : 0)
    if (kb <= 0 && mouse <= 0) continue
    out.activeMinutes += 1
    if (kb >= mouse) out.kbMinutes += 1
    else out.mouseMinutes += 1
  }
  if (out.activeMinutes === 0) return out
  var span = Math.ceil((nowMs - out.firstTsMs) / 60000)
  out.spanMinutes = Math.max(span, out.activeMinutes)
  out.idleMinutes = out.spanMinutes - out.activeMinutes
  out.kbPct = Math.round(out.kbMinutes * 100 / out.spanMinutes)
  out.mousePct = Math.round(out.mouseMinutes * 100 / out.spanMinutes)
  // Rounding the first two can drift off 100; idle absorbs the remainder.
  out.idlePct = Math.max(0, 100 - out.kbPct - out.mousePct)
  return out
}
