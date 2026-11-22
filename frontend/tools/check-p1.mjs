// Runs Role 1 documents through the reader's converter without a browser.
// Usage: npm run test:p1 -- [more-documents.json ...]
import { readFileSync } from 'node:fs'
import { fromP1 } from '../src/lib/p1.ts'
import { pageAnnouncements, sentencesOf, toSentenceStarts, unitsFor } from '../src/lib/sentences.ts'
import { clipsFor, withKeptClips } from '../src/lib/audio.ts'
import { unitClipKey } from '../src/lib/hash.ts'

const extra = { subject: 'check', rights_note: 'check' }
const load = (f) => JSON.parse(readFileSync(f, 'utf8'))
const clone = (x) => JSON.parse(JSON.stringify(x))
let failed = 0
const ok = (name, cond) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`); if (!cond) failed++ }

const base = load(new URL('../src/data/p1-sample.json', import.meta.url))
const pkg = fromP1(base, extra)
const tableOf = (p) => p.blocks.find((b) => b.table)

ok('sample converts: 3 pages, 8 passages', pkg.pages.length === 3 && pkg.blocks.length === 8)
ok('failed page keeps its status and warning', pkg.pages[2].status === 'failed' && pkg.pages[2].warnings.length === 1)
ok('page without a printed number is marked, not given a fake label', pkg.pages[2].label_missing === true && pkg.pages[2].printed_label === '(3)')
const notes = pageAnnouncements(pkg.pages, pkg.blocks)
ok('a failed last page is announced after the last passage, in the language around it', [...notes.after.values()].flat().some((n) => n.text.includes('पढ़ा नहीं जा सका') && n.lang === 'hi'))
ok('every passage has a voice language', pkg.blocks.every((b) => b.lang === 'en' || b.lang === 'hi'))

// Uncertain table (1.1.0): no cells, counts null, text in raw_text.
const u = clone(base)
const ut = u.blocks.find((b) => b.block_type === 'table')
u.blocks = u.blocks.filter((b) => b.block_type !== 'table_cell')
u.edges = u.edges.filter((e) => e.edge_type !== 'header_for' && e.edge_type !== 'contains')
Object.assign(ut, { table: { row_count: null, column_count: null, cell_ids: [] }, raw_text: 'Quantity SI unit Acceleration m/s²', current_text: 'Quantity SI unit Acceleration m/s²', quality_flags: ['table_structure_uncertain'] })
const up = fromP1(u, extra).blocks.find((b) => b.id === ut.id)
ok('uncertain table is read as plain text and sent to review', up.type === 'paragraph' && !up.table && up.status === 'needs_review' && up.text_current.includes('Acceleration'))

// Merged header: "Quantity" spans both columns above a second header row.
const m = clone(base)
const mt = m.blocks.find((b) => b.block_type === 'table')
const cells = mt.table.cell_ids.map((id) => m.blocks.find((b) => b.id === id))
mt.table.row_count = 3
cells[0].table_cell.column_span = 2
cells[0].current_text = cells[0].raw_text = 'Measured values'
Object.assign(cells[1].table_cell, { row_index: 1, column_index: 0, is_header: true }); cells[1].current_text = cells[1].raw_text = 'Quantity'
Object.assign(cells[2].table_cell, { row_index: 1, column_index: 1, is_header: true, header_cell_ids: [] }); cells[2].current_text = cells[2].raw_text = 'SI unit'
Object.assign(cells[3].table_cell, { row_index: 2, column_index: 1 })
const extraCell = clone(cells[3]); extraCell.id = '7d1e4c52-0000-4000-8000-0000000000aa'; extraCell.reading_order = 9
Object.assign(extraCell.table_cell, { row_index: 2, column_index: 0, header_cell_ids: [] }); extraCell.current_text = extraCell.raw_text = 'Acceleration'
m.blocks.push(extraCell); mt.table.cell_ids.push(extraCell.id)
m.edges = m.edges.filter((e) => e.edge_type !== 'header_for')
const mp = tableOf(fromP1(m, extra))
ok('merged header is repeated over each column it covers', mp.table.columns.join('|') === 'Measured values – Quantity|Measured values – SI unit')
ok('merged-header table keeps its data row', mp.table.rows.length === 1 && mp.table.rows[0].join('|') === 'Acceleration|m/s²')

// Critical symbol flag: any quality flag the reader does not know still sends the passage to review.
const c = clone(base)
c.blocks[1].quality_flags = ['low_confidence', 'critical_symbol_uncertain']
const cp = fromP1(c, extra).blocks[1]
ok('critical symbol flag sends the passage to review and is the reason shown first', cp.status === 'needs_review' && cp.confidence.flags[0] === 'critical_symbol_uncertain')

// Two row-label columns: both are part of each row's label, and a label merged down two rows is repeated.
{
  const r = clone(base)
  const rt = r.blocks.find((b) => b.block_type === 'table')
  r.blocks = r.blocks.filter((b) => b.block_type !== 'table_cell')
  const cell = (i, row, col, text, header, rowSpan = 1) => ({ ...clone(base.blocks.find((b) => b.block_type === 'table_cell')), id: `7d1e4c52-0000-4000-8000-0000000001${String(i).padStart(2, '0')}`, reading_order: 20 + i, raw_text: text, current_text: text,
    table_cell: { row_index: row, column_index: col, row_span: rowSpan, column_span: 1, is_header: header, header_cell_ids: [] } })
  const cs = [cell(1, 0, 0, 'Quantity', true), cell(2, 0, 1, 'Case', true), cell(3, 0, 2, 'Value', true),
    cell(4, 1, 0, 'Speed', true, 2), cell(5, 1, 1, 'walking', true), cell(6, 1, 2, '1.4 m/s', false),
    cell(7, 2, 1, 'cycling', true), cell(8, 2, 2, '4 m/s', false)]
  cs.forEach((x) => { x.parent_id = rt.id })
  r.blocks.push(...cs)
  Object.assign(rt.table, { row_count: 3, column_count: 3, cell_ids: cs.map((x) => x.id) })
  r.edges = r.edges.filter((e) => !['header_for', 'contains'].includes(e.edge_type))
  const rp = tableOf(fromP1(r, extra))
  ok('two row-label columns are read together, merged label repeated', !!rp && rp.table.columns.join('|') === 'Quantity – Case|Value' && rp.table.rows.map((x) => x.join('|')).join(' / ') === 'Speed – walking|1.4 m/s / Speed – cycling|4 m/s')
}

// Contract 1.2.0: heading_level, role, voice_language, and the original mul/und tag.
const v = clone(base)
v.schema_version = '1.2.0'
const vh = v.blocks.filter((b) => b.block_type === 'heading')
vh.forEach((b) => { b.heading_level = null })
if (vh[0]) vh[0].heading_level = 1
if (vh[1]) vh[1].heading_level = 4
const vp = v.blocks.filter((b) => b.block_type === 'paragraph')
vp[0].role = 'page_header'
vp[1].language = 'mul'; vp[1].integration = { voice_language: 'hi' }
const vv = fromP1(v, extra)
const levels = vv.blocks.filter((b) => b.type === 'heading').map((b) => b.level)
ok('1.2.0 heading_level 1 stays 1, deeper and null become 2', levels[0] === 1 && levels.slice(1).every((l) => l === 2))
ok('1.2.0 page_header role is not shown or read', !vv.blocks.some((b) => b.id === vp[0].id))
const mulB = vv.blocks.find((b) => b.id === vp[1].id)
ok('mul passage keeps its tag and uses the backend voice', mulB.source_lang === 'mul' && mulB.lang === 'hi')

// mul/und without a backend voice: same rule as Role 3 (Hindi only when Devanagari letters outnumber English).
{
  const w = clone(base)
  const ps = w.blocks.filter((b) => ['paragraph', 'heading', 'list_item'].includes(b.block_type) && b.role !== 'page_header' && b.role !== 'page_footer')
  const set = (b, tag, text) => { b.language = tag; b.raw_text = b.current_text = text; delete b.integration }
  set(ps[0], 'mul', 'ab कख')
  set(ps[1], 'und', '12 = 3 + 9')
  set(ps[2], 'mul', 'a कखग')
  const out = fromP1(w, extra).blocks
  const lang = (b) => out.find((x) => x.id === b.id)?.lang
  ok('mul/und voice: a tie is English, no letters is English, more Hindi letters is Hindi', lang(ps[0]) === 'en' && lang(ps[1]) === 'en' && lang(ps[2]) === 'hi')
}

// Backend sentence ranges: code points converted to JavaScript offsets, and the pieces rejoin to the text.
const hiText = 'गति क्या है? यह 𝑣 = 3.5 m/s है। अंत'
const cp2 = [...hiText]
const cut = (a, b) => ({ start: a, end: b })
const i1 = cp2.indexOf('?') + 1, i2 = cp2.indexOf('।') + 1
const starts = toSentenceStarts(hiText, [cut(0, i1), cut(i1 + 1, i2), cut(i2 + 1, cp2.length)])
const pieces = starts && sentencesOf({ text_current: hiText, lang: 'hi', sentence_starts: starts })
ok('code-point ranges with a character outside the basic plane map to the right sentences', !!pieces && pieces.length === 3 && pieces.join('') === hiText && pieces[2] === 'अंत')
ok('ranges that do not fit the text are ignored', toSentenceStarts('short', [cut(0, 50)]) === null)

// Role 3 prepared audio: the four-field clip key (passage, text SHA-256, sentence number, voice language).
{
  const enc = new TextEncoder()
  const sha = async (t) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(t)))].map((b) => b.toString(16).padStart(2, '0')).join('')
  const text = 'Speed is distance per time. वेग में दिशा भी होती है।'
  const cps = [...text], cut = cps.indexOf('.') + 1
  const units = [[0, cut], [cut + 1, cps.length]].map(([s, e], i) => ({ text_offset_start: s, text_offset_end: e, clip_asset_id: `clip${i}`, hash: 'h' + i, bytes: 100 }))
  const block = () => ({ id: 'b1', type: 'paragraph', lang: 'hi', source_lang: 'mul', text_current: text, status: 'trusted' })
  const file = async (over = {}) => ({ status: 'ready', block_id: 'b1', text_sha256: await sha(text), language: 'mul', units, ...over })
  const url = (id) => `/api/assets/${id}`

  const b = block()
  const clips = await clipsFor(b, await file(), url)
  ok('backend clips are keyed by passage, text hash, sentence number and voice language', clips.length === 2 && clips[1].key === `b1|${await sha(text)}|1|hi` && clips[1].url === '/api/assets/clip1')
  ok('a mul passage keeps its tag and gets the clip for its voice language', b.source_lang === 'mul' && clips.every((c) => c.key.endsWith('|hi')))
  const keys = await Promise.all(unitsFor(b, false).map((u) => unitClipKey(u, b.text_current)))
  ok('the narrator asks for exactly those keys', keys.join() === clips.map((c) => c.key).join())
  const reviewed = { ...block(), status: 'reviewed', revision: 7 }
  ok('a review-only change keeps the same clips', (await clipsFor(reviewed, await file(), url)).map((c) => c.key).join() === clips.map((c) => c.key).join())
  ok('edited text gets no old clips', (await clipsFor({ ...block(), text_current: text + ' नया' }, await file(), url)).length === 0)
  ok('silent test clips are never used', (await clipsFor(block(), await file({ synthetic: true }), url)).length === 0)
  ok('clips cut at other sentence boundaries are not used', (await clipsFor({ ...block(), sentence_starts: [0, 5] }, await file(), url)).length === 0)
  ok('clips in another voice language are not used', (await clipsFor({ ...block(), source_lang: undefined }, await file({ language: 'en' }), url)).length === 0)

  // Manifest still pending for a new revision: clips saved earlier are kept only while the text is unchanged.
  const pkgOf = (blk, audio, pending) => ({ document: { id: 'd' }, blocks: [blk], pages: [], audio, bytes: 0, audio_pending: pending })
  const saved = pkgOf(block(), clips, false)
  const kept = await withKeptClips(pkgOf({ ...block(), status: 'reviewed' }, [], true), saved)
  ok('while the manifest is pending, a review-only change keeps the saved clips', kept.audio.length === 2 && kept.bytes === 200)
  ok('while the manifest is pending, edited text keeps no old clips', (await withKeptClips(pkgOf({ ...block(), text_current: text + ' नया' }, [], true), saved)).audio.length === 0)
  ok('once the manifest is ready, only its own clips are used', (await withKeptClips(pkgOf(block(), [], false), saved)).audio.length === 0)
}

for (const f of process.argv.slice(2)) {
  try { const p = fromP1(load(f), extra); ok(`${f}: ${p.pages.length} pages, ${p.blocks.length} passages`, p.blocks.every((b) => b.lang === 'en' || b.lang === 'hi')) }
  catch (e) { ok(`${f}: ${e.message}`, false) }
}
process.exit(failed ? 1 : 0)
