// i18n catalogs ship in lockstep: every language defines the same keys as
// en.json, as non-empty strings, and carries every placeholder (%1, %2…)
// its English string uses. Run: node widget/tests/i18n.test.js

const fs = require("fs")
const path = require("path")

const dir = path.join(__dirname, "..", "pulse", "i18n")
const base = JSON.parse(fs.readFileSync(path.join(dir, "en.json"), "utf8"))
const baseKeys = Object.keys(base)

const fails = []

function placeholders(s) {
  return (String(s).match(/%\d/g) || []).sort()
}

for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json")) {
  const catalog = JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"))
  const missing = baseKeys.filter((k) => !(k in catalog))
  const extra = Object.keys(catalog).filter((k) => !(k in base))
  if (missing.length) fails.push(`${file}: missing keys: ${missing.join(", ")}`)
  if (extra.length) fails.push(`${file}: unknown keys: ${extra.join(", ")}`)
  for (const key of baseKeys) {
    if (!(key in catalog)) continue
    const value = catalog[key]
    if (typeof value !== "string" || value.trim() === "")
      fails.push(`${file}: "${key}" is not a non-empty string`)
    const want = placeholders(base[key]).join(",")
    const got = placeholders(value).join(",")
    if (want !== got)
      fails.push(`${file}: "${key}" placeholders differ (en: ${want || "none"}, ${file}: ${got || "none"})`)
  }
}

if (fails.length) {
  console.error("FAIL\n" + fails.join("\n"))
  process.exit(1)
}
console.log(`i18n tests: ${1 + fs.readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json").length} catalog(s) in sync`)
