// End-to-end check of the student flow: find, present, review, ask, download, resume offline.
// Run:  npm run build && npm run preview   then
//       playwright-cli open http://localhost:4173 && playwright-cli run-code --filename=e2e/flow.js
async (page) => {
  const log = []
  const errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const shot = (name) => page.screenshot({ path: `e2e/shots/${name}.png` })
  const base = 'http://localhost:4173'

  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base)
  await page.evaluate(async () => {
    localStorage.clear()
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
    for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister()
    for (const k of await caches.keys()) await caches.delete(k)
  })
  await page.goto('about:blank') // lets the old service worker finish unregistering
  await page.goto(base)
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.waitForFunction(async () => (await caches.keys()).length > 0) // app shell is cached
  await page.reload() // now controlled by the new worker
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  await page.getByRole('link', { name: 'Motion in a straight line', exact: true }).waitFor()
  ok('library lists the three sample chapters', (await page.locator('main li.book').count()) === 3)
  await shot('library-1440')

  // Find
  await page.getByRole('link', { name: 'Motion in a straight line', exact: true }).click()
  await page.locator('.passage').first().waitFor()
  ok('reader renders passages', (await page.locator('.passage').count()) === 29)
  await page.getByLabel('Go to printed page').fill('38')
  await page.getByLabel('Go to printed page').press('Enter')
  await page.waitForTimeout(700)
  ok('go to page 38 moves focus to its first passage', (await page.evaluate(() => document.activeElement?.textContent)) === 'Acceleration')
  await shot('reader-1440')

  // Review and correct
  const card = page.locator('aside li.card', { hasText: '20 m/s' })
  await card.getByRole('button', { name: 'Correct' }).click()
  const area = card.getByLabel('Corrected text')
  await area.fill((await area.inputValue()).replace('is 2 m/s²', 'is −2 m/s²'))
  await shot('review-form-1440')
  await card.getByRole('button', { name: 'Publish correction' }).click()
  await page.getByText('Revision 2 published').waitFor()
  ok('correction publishes revision 2', await page.getByText('Pages 36–40 · Revision 2').isVisible())
  ok('corrected text shown in the chapter', await page.locator('.passage', { hasText: 'is −2 m/s²' }).isVisible())
  ok('edit trail keeps the scanner text', (await page.getByText('Corrected in revision 2').count()) === 1)

  // Ask, open evidence, return
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByLabel('Ask about this chapter').fill('What is displacement?')
  await page.getByRole('button', { name: 'Ask', exact: true }).last().click()
  await page.getByRole('button', { name: /Open the passage/ }).first().waitFor()
  await page.getByRole('button', { name: /Open the passage/ }).first().click()
  await page.getByRole('button', { name: 'Back to your answer' }).waitFor()
  ok('evidence passage is highlighted', (await page.locator('.passage[data-flash=true]').count()) === 1)
  await shot('evidence-1440')
  await page.getByRole('button', { name: 'Back to your answer' }).click()
  ok('return focuses the answer', await page.evaluate(() => document.activeElement?.id.startsWith('answer-')))
  await page.getByLabel('Ask about this chapter').fill('Who invented the telescope?')
  await page.getByRole('button', { name: 'Ask', exact: true }).last().click()
  await page.getByText('does not seem to cover').waitFor()
  ok('unsupported question abstains', true)

  // Bookmark and download
  await page.locator('.passage').nth(1).getByRole('button', { name: 'Options for this passage' }).click()
  await page.getByRole('menuitem', { name: 'Add bookmark' }).click()
  await page.getByText('Bookmark added').waitFor()
  await page.getByRole('button', { name: 'Download' }).click()
  await page.getByText('Chapter downloaded').waitFor()
  ok('chapter downloads', true)
  await page.getByLabel('Go to printed page').fill('39')
  await page.getByLabel('Go to printed page').press('Enter')
  await page.waitForTimeout(1500)

  // Offline restart
  await page.context().setOffline(true)
  await page.reload()
  await page.locator('.passage').first().waitFor()
  ok('offline restart opens the downloaded copy', await page.getByText('You are offline, reading your downloaded copy').isVisible())
  ok('offline copy has the corrected text', (await page.locator('.passage', { hasText: 'is −2 m/s²' }).count()) === 1)
  await page.waitForTimeout(800)
  ok('reading position restored near page 39', await page.evaluate(() => { const r = document.getElementById('page-39').getBoundingClientRect(); return r.top > -200 && r.top < innerHeight }))
  await page.getByRole('button', { name: 'search', exact: true }).click()
  await page.getByLabel('Search this chapter').fill('trolley')
  ok('offline search finds a passage', await page.getByText('1 passage found').isVisible())
  await page.getByRole('button', { name: /bookmarks/ }).click()
  ok('bookmark survives offline', (await page.locator('ul[aria-label=Bookmarks] li').count()) === 1)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  ok('assistant says it is unavailable offline', await page.getByText('The assistant needs internet').isVisible())
  await shot('offline-1440')

  // Offline correction is queued, then sent on reconnect
  await page.getByRole('button', { name: /^Review( [0-9]+)?$/ }).click()
  const c2 = page.locator('aside li.card', { hasText: 'l6 m' })
  await c2.getByRole('button', { name: 'Correct' }).click()
  await c2.getByLabel('Corrected text').fill('Example 3.2: A trolley starts from rest and accelerates at 0.5 m/s² for 8 s. Its final velocity is 4 m/s and it covers 16 m.')
  await c2.getByRole('button', { name: 'Publish correction' }).click()
  await page.getByText('1 correction waiting to send').waitFor()
  ok('offline correction is queued', true)
  await page.context().setOffline(false)
  await page.getByText('written offline was sent').waitFor()
  ok('queued correction sent on reconnect', await page.getByText('Pages 36–40 · Revision 3').isVisible())

  // Hindi chapter, other screens, themes
  await page.goto(base + '/read/bal-gati')
  await page.locator('.passage').first().waitFor()
  ok('Hindi passages carry lang=hi', (await page.locator('.passage[lang=hi]').count()) > 5)
  await shot('reader-hindi-1440')
  await page.goto(base + '/downloads')
  await page.getByText('Saved, 29 passages').waitFor()
  await shot('downloads-1440')
  await page.goto(base + '/settings')
  await page.getByRole('heading', { name: 'Reading display' }).waitFor()
  await shot('settings-1440')
  await page.getByText('High contrast').click()
  await page.getByLabel('Text size').fill('30')
  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(600)
  ok('preferences apply to the reader', (await page.evaluate(() => getComputedStyle(document.querySelector('.reading')).fontSize)) === '30px')
  await shot('reader-contrast-1440')
  await page.goto(base + '/settings')
  await page.getByRole('button', { name: 'Reset display and speech settings' }).click()

  // Phone
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(base)
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  await shot('library-390')
  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(600)
  ok('no sideways scroll on a phone', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await shot('reader-390')
  await page.getByRole('button', { name: /^Review( [0-9]+)?$/ }).click()
  await page.getByRole('dialog').waitFor()
  await shot('review-390')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Contents' }).click()
  await page.getByRole('dialog').getByRole('button', { name: /Exercises/ }).click()
  await page.waitForTimeout(700)
  ok('contents sheet closes and focus lands on the heading', (await page.evaluate(() => document.activeElement?.textContent)) === 'Exercises')
  // 400% zoom equivalent: 320 CSS px wide
  await page.setViewportSize({ width: 320, height: 640 })
  await page.waitForTimeout(300)
  ok('reflows at 320px (400% zoom)', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await shot('reader-320')

  ok('no console errors', errors.length === 0)
  return log.join('\n') + (errors.length ? '\nERRORS:\n' + errors.slice(0, 8).join('\n') : '')
}
