// Runs Role 1 documents through the reader's converter without a browser.
// Usage: node --experimental-strip-types tools/check-p1.mjs [more-documents.json ...]
import { readFileSync } from 'node:fs'
import { fromP1 } from '../src/lib/p1.ts'
import { pageAnnouncements } from '../src/lib/sentences.ts'

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
ok('a failed last page is announced after the last passage', [...notes.after.values()].flat().some((t) => t.includes('could not be read')))
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

for (const f of process.argv.slice(2)) {
  try { const p = fromP1(load(f), extra); ok(`${f}: ${p.pages.length} pages, ${p.blocks.length} passages`, p.blocks.every((b) => b.lang === 'en' || b.lang === 'hi')) }
  catch (e) { ok(`${f}: ${e.message}`, false) }
}
process.exit(failed ? 1 : 0)
