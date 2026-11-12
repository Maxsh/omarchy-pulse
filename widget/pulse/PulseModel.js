// Pure helpers for the pulse widget: bucket discovery, today's fetch, summing,
// and number formatting. No state, no QML imports — everything is passed in,
// which keeps the data logic reviewable and testable on its own.

var DEFAULT_AW_URL = "http://localhost:5600"
var BUCKET_TYPE = "os.hid.input"

var COUNT_KEYS = ["presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY"]

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
// start filter keeps the payload at ~a few KB), and sum them. Calls back
// with { ok, bucketId, today } or { ok: false, error }.
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
      callback({ ok: true, bucketId: bucketId, today: sumEvents(events, midnightMs(now)) })
    })
  })
}

// Sum per-minute events into one totals object. Events from before sinceMs
// are ignored (defense against a server ignoring the start filter).
function sumEvents(events, sinceMs) {
  var sums = { presses: 0, clicks: 0, deltaX: 0, deltaY: 0, scrollX: 0, scrollY: 0, minutes: 0 }
  if (!events) return sums
  for (var i = 0; i < events.length; i++) {
    var event = events[i]
    var ts = Date.parse(String(event.timestamp))
    if (isFinite(ts) && ts < sinceMs) continue
    var data = event.data || {}
    for (var k = 0; k < COUNT_KEYS.length; k++) {
      var key = COUNT_KEYS[k]
      var value = Number(data[key])
      if (isFinite(value) && value > 0) sums[key] += value
    }
    sums.minutes += 1
  }
  return sums
}

// 0 -> "0", 999 -> "999", 1234 -> "1.2k", 45200 -> "45k", 3200000 -> "3.2M".
// Bar labels are compact by nature; exact numbers live in the panel tooltip.
function compactNumber(value) {
  var n = Math.round(Number(value) || 0)
  if (n < 1000) return String(n)
  if (n < 10000) return (Math.round(n / 100) / 10) + "k"
  if (n < 1000000) return Math.round(n / 1000) + "k"
  return (Math.round(n / 100000) / 10) + "M"
}
