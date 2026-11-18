// Checks the screens built for the other two roles' features:
// review desk (Role 1 flags and structure fixes), chapter details (Role 3 revisions, rebuild state, deletion),
// upload cancel/retry (Role 3 jobs) and the daily question limit (Role 3 usage limits).
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base)
  await page.evaluate(async () => {
    localStorage.clear()
    // Drop any older cached build, so the test runs against the files just built.
    for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister()
    for (const k of await caches.keys()) await caches.delete(k)
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
  })

  // ---- review desk ----
  await page.goto(base + '/review')
  const cards = page.getByRole('list', { name: 'Passages waiting for a check' }).locator('> li')
  await cards.first().waitFor()
  ok('review desk lists flagged passages from all chapters (6)', (await cards.count()) === 6)
  ok('menu badge shows the same count', (await page.locator('aside nav a[href="/review"] .pill').innerText()).includes('6'))
  await page.getByRole('button', { name: /^Missing minus sign/ }).click()
  ok('filter by problem narrows the list', (await cards.count()) === 1)
  await page.getByRole('button', { name: 'Check and correct' }).click()
  const box = page.getByLabel('Corrected text')
  ok('correction form takes focus', await box.evaluate((el) => el === document.activeElement))
  await box.fill((await box.inputValue()).replace('is 2 m/s', 'is −2 m/s'))
  await page.getByText('Language, kind and reading order').click()
  await page.getByLabel('This passage is a').selectOption('list_item')
  await page.getByLabel('What was wrong?').fill('minus sign missing')
  await page.getByRole('button', { name: 'Publish correction' }).click()
  await page.getByText(/Revision 2 of .* published/).first().waitFor()
  await page.getByRole('button', { name: /^All 5/ }).waitFor()
  ok('published correction leaves the queue', (await cards.count()) === 5)
  const effort = await page.getByRole('region', { name: 'Review progress' }).innerText()
  const m = effort.match(/([0-9]+)[^0-9]+of ([0-9]+) checked/)
  ok("review progress counts it", !!m && Number(m[2]) - Number(m[1]) === 5)
  ok('it appears under Recently checked', (await page.getByRole('heading', { name: 'Recently checked' }).count()) === 1)

  // ---- open the passage from the desk ----
  await page.getByRole('region', { name: 'Recently checked' }).getByRole('link').first().click()
  await page.locator('.passage[data-flash="true"]').waitFor()
  const opened = await page.evaluate(() => { const el = document.querySelector('.passage[data-flash="true"]'); return { text: el.textContent, li: !!el.closest('li') || el.tagName === 'LI' || !!el.querySelector('li'), top: el.getBoundingClientRect().top } })
  ok('link opens the reader at the corrected passage', opened.text.includes('−2 m/s') && opened.top < 400)
  ok('the passage is now a list item', opened.li)

  // ---- question limit ----
  await page.getByRole('tab', { name: 'Ask' }).or(page.getByRole('button', { name: 'Ask', exact: true })).first().click()
  await page.getByText('20 of 20 questions left today').waitFor()
  await page.getByLabel('Ask about this chapter').fill('What is displacement?')
  await page.getByRole('button', { name: 'Ask', exact: true }).last().click()
  await page.getByText('19 of 20 questions left today').waitFor()
  ok('questions left today counts down', true)
  await page.evaluate(() => localStorage.setItem('pathya.mock.usage.v1', JSON.stringify({ day: new Date().toISOString().slice(0, 10), used: 20 })))
  await page.reload()
  await page.locator('.passage').first().waitFor()
  await page.getByRole('tab', { name: 'Ask' }).or(page.getByRole('button', { name: 'Ask', exact: true })).first().click()
  await page.getByText(/questions are used/).waitFor()
  await page.getByLabel('Ask about this chapter').fill('What is speed?')
  ok('asking is blocked when the limit is reached', await page.getByRole('button', { name: 'Ask', exact: true }).last().isDisabled())

  // ---- chapter details ----
  await page.getByRole('link', { name: /^Chapter details/ }).click()
  await page.getByRole('heading', { name: 'Motion in a straight line', level: 1 }).waitFor()
  const history = page.getByRole('region', { name: 'Correction history' })
  await history.getByText('Revision 2').waitFor()
  const h = await history.innerText()
  ok('history shows before, after, reason and the structure change', h.includes('is 2 m/s') && h.includes('−2 m/s') && h.includes('minus sign missing') && h.includes('Marked as a list item'))
  const sync = await page.getByRole('region', { name: /Kept in step/ }).innerText()
  ok('corrected sentences are reported as read by the device voice', /\d+ of \d+ sentences have a prepared clip/.test(sync))
  ok('quality card counts what is still waiting', (await page.getByRole('region', { name: 'How well the pages were read' }).innerText()).includes('3 waiting for a check'))
  await page.screenshot({ path: 'e2e/shots/tour-chapter-after.png', fullPage: true })

  // ---- remove a chapter ----
  await page.getByRole('button', { name: 'Remove chapter…' }).click()
  ok('removal asks first, focus is inside the dialog', await page.evaluate(() => !!document.activeElement.closest('[role=dialog]')))
  await page.getByRole('button', { name: 'Remove for good' }).click()
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  await page.locator('main li.book').first().waitFor()
  ok('removed chapter leaves the library', (await page.locator('main li.book').count()) === 2)
  await page.goto(base + '/read/motion')
  await page.getByText(/could not be|not found|does not exist|couldn/i).first().waitFor()
  ok('its reader link no longer opens it', (await page.locator('.passage').count()) === 0)

  // ---- uploads: cancel and try again ----
  await page.goto(base + '/add')
  await page.getByLabel('Chapter file').setInputFiles({ name: 'light-reflection.pdf', mimeType: 'application/pdf', buffer: Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.alloc(900000)]) })
  await page.getByText('I am allowed to use this chapter').click()
  await page.getByRole('button', { name: 'Upload and prepare' }).click()
  await page.getByRole('button', { name: 'Cancel upload', exact: true }).click()
  await page.getByText('Upload cancelled', { exact: true }).waitFor()
  ok('a running upload can be cancelled', true)
  await page.reload()
  const uploads = page.getByRole('region', { name: 'Your uploads' })
  await uploads.getByText('Cancelled').waitFor()
  ok('the upload is still listed after a reload', (await uploads.innerText()).includes('light reflection'))
  await uploads.getByRole('button', { name: /^Try .* again/ }).click()
  await uploads.getByText(/Waiting|Checking the file|Reading pages/).waitFor()
  ok('a cancelled upload can be tried again', true)

  // ---- restore samples ----
  await page.goto(base + '/settings')
  await page.getByRole('button', { name: 'Restore the sample chapters' }).click()
  await page.goto(base)
  await page.locator('main li.book').nth(1).waitFor()
  ok('sample chapters can be restored', (await page.locator('main li.book').count()) === 3)

  // ---- phone ----
  await page.setViewportSize({ width: 320, height: 640 })
  for (const path of ['/review', '/chapter/motion']) {
    await page.goto(base + path)
    await page.locator('h2').first().waitFor()
    await page.waitForTimeout(400)
    ok(`no sideways scroll at 320px on ${path}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  }
  ok('no console errors', errors.length === 0)
  if (errors.length) log.push(errors.slice(0, 3).join('\n'))
  return log.join('\n')
}
