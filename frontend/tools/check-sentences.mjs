// Checks the reader's splitter against the pathya-sentences/3 fixtures shared by Role 1 and Role 3.
// Usage: npm run test:sentences
import { readFileSync } from 'node:fs'
import { sentenceRanges } from '../src/lib/sentences.ts'

const { segmenter, fixtures } = JSON.parse(readFileSync(new URL('./p3/pathya-sentences-3.fixtures.json', import.meta.url), 'utf8'))
let failed = 0
for (const f of fixtures) {
  const got = sentenceRanges(f.text)
  const same = JSON.stringify(got) === JSON.stringify(f.ranges.map((r) => ({ start: r.start, end: r.end })))
  if (!same) { failed++; console.log(`FAIL  ${f.id}: ${JSON.stringify(f.text)}\n      want ${JSON.stringify(f.ranges)}\n      got  ${JSON.stringify(got)}`) }
}
console.log(`${segmenter}: ${fixtures.length - failed} of ${fixtures.length} fixtures match`)
process.exit(failed ? 1 : 0)
