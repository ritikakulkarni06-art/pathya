// Checks that Role 1's contract sample (src/data/p1-sample.json, converted by src/lib/p1.ts)
// opens, reads in the right order and is presented by the rules in docs/p1_contract.md.
async (page) => {
  const base = 'http://localhost:4173'
  const DOC = '7d1e4c52-0000-4000-8000-000000000001'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base)
  await page.evaluate(async () => {
    localStorage.clear()
    for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister()
    for (const k of await caches.keys()) await caches.delete(k)
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
  })
  await page.goto(`${base}/read/${DOC}`)
  await page.locator('.passage').first().waitFor()
  const passages = page.locator('.passage')

  ok('8 passages: table cells and linked captions are not separate passages', (await passages.count()) === 8)
  const order = await passages.evaluateAll((els) => els.map((e) => e.id.slice(-2)))
  ok('reading order follows page, then reading_order', order.join() === 'a1,a2,a3,a4,b1,b2,b3,b5')
  if (order.join() !== 'a1,a2,a3,a4,b1,b2,b3,b5') log.push('  order was ' + order.join())

  ok('first heading is the chapter title level, later heading one below', (await page.locator('.passage h2').count()) === 1 && (await page.locator('.passage h3').count()) === 1)
  ok('approved MathML is shown with its approved spoken form', (await page.locator('.passage math').count()) === 1 && (await page.getByText('v equals u plus a t').count()) === 1)

  const table = page.locator('.passage table')
  ok('table is rebuilt from cell blocks with column headers', (await table.locator('thead th').allTextContents()).join('|') === 'Quantity|SI unit')
  ok('table body has the data row', (await table.locator('tbody tr').first().innerText()).replace(/\s+/g, ' ').trim() === 'Acceleration m/s²')
  ok('linked caption becomes the table caption', (await table.locator('caption').innerText()).includes('Table 4.1'))

  const langs = await passages.evaluateAll((els) => els.map((e) => e.lang))
  ok('every passage has a voice language (en or hi), also for "mul" and "und"', langs.every((l) => l === 'en' || l === 'hi'))
  ok('"mul" list item with mostly Hindi text is read by the Hindi voice', langs[langs.length - 1] === 'hi')

  const note = page.locator('[data-page-status=failed]')
  ok('a page that could not be read says so in the language around it, and is not shown as blank', (await note.count()) === 1 && (await note.innerText()).includes('पढ़ा नहीं जा सका') && (await note.getAttribute('lang')) === 'hi')
  ok('a page with no printed number is named by its place in the file', (await note.innerText()).includes('फ़ाइल का पृष्ठ 3'))
  ok('scanner notes for a page can be opened', (await page.getByText(/Notes from the scanner for this page/).count()) === 2)

  const fig = page.locator('.passage figure')
  ok('figure shows its printed caption once', (await page.getByText('चित्र 10.1 समतल दर्पण द्वारा प्रकाश का परावर्तन').count()) === 1)
  ok('approved human description is not labelled as a draft', (await fig.innerText()).includes('Description written by a teacher'))
  ok('figure with review_status needs_review is flagged', (await page.locator('.passage[data-review=true]').count()) === 1)
  ok('corrected passage offers the scanner text', (await page.getByText('Corrected in revision 2').count()) === 1)

  await page.goto(`${base}/review`)
  await page.getByRole('list', { name: 'Passages waiting for a check' }).locator('> li').first().waitFor()
  ok('review desk shows the flagged figure from this chapter', (await page.getByText('Science - Class 9 (bilingual sample excerpt)').count()) >= 1)

  await page.goto(`${base}/chapter/${DOC}`)
  await page.locator('h2').first().waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'e2e/shots/p1-chapter.png', fullPage: true })
  await page.goto(`${base}/read/${DOC}`)
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(600)
  await page.screenshot({ path: 'e2e/shots/p1-reader.png', fullPage: true })

  ok('no console errors', errors.length === 0)
  if (errors.length) log.push(errors.slice(0, 3).join('\n'))
  return log.join('\n')
}
