// Checks that prepared narration clips are used online and after an offline restart.
// Needs `npm run audio` to have been run before the build.
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const wavs = []
  page.on('request', (r) => r.url().endsWith('.wav') && wavs.push(r.url()))
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base + '/read/motion')
  await page.evaluate(async () => {
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
    for (const k of await caches.keys()) if (k.startsWith('pathya-assets')) await caches.delete(k)
  })
  await page.reload()
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(1200) // network copy with the audio list has arrived

  await page.locator('footer .btn-primary').click()
  await page.waitForFunction(() => /Sentence [3-9] of/.test(document.querySelector('footer').innerText), null, { timeout: 30000 })
  ok('clips are requested for narration', wavs.length >= 2)
  ok('the sentence being read is highlighted', (await page.locator('.sentence[data-current=true]').count()) === 1)
  await page.keyboard.press('Alt+Shift+KeyP')
  ok('pause shortcut works', await page.locator('footer .btn-primary', { hasText: 'Resume' }).isVisible())

  await page.getByRole('button', { name: 'Download' }).click()
  await page.getByText('Chapter downloaded').waitFor({ timeout: 60000 })
  const cached = await page.evaluate(async () => (await (await caches.open('pathya-assets-v1')).keys()).length)
  ok(`all clips saved for offline (${cached})`, cached === 57)

  await page.context().setOffline(true)
  await page.reload()
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(800)
  await page.locator('footer .btn-primary').click()
  await page.waitForFunction(() => /Sentence ([2-9]|[1-5][0-9]) of/.test(document.querySelector('footer').innerText) && document.querySelector('footer .btn-primary').innerText.includes('Pause'), null, { timeout: 30000 }).then(() => ok('narration plays from saved clips while offline', true), () => ok('narration plays from saved clips while offline', false))
  await page.keyboard.press('Alt+Shift+KeyP')
  await page.context().setOffline(false)
  return log.join('\n')
}
