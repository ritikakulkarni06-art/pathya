// Downloaded chapters: kept per account, checked against the server on start, purged when access is lost or on sign-out.
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const SERVER = 'pathya.mock.server.v1'
  // Read the downloaded chapters straight from the device store: [{ db, id, revision }]
  const stored = () => page.evaluate(async () => {
    const out = []
    for (const d of await indexedDB.databases()) {
      if (!d.name.startsWith('pathya')) continue
      const rows = await new Promise((resolve) => {
        const open = indexedDB.open(d.name)
        open.onsuccess = () => {
          const db = open.result
          if (!db.objectStoreNames.contains('packages')) { db.close(); return resolve([]) }
          const all = db.transaction('packages').objectStore('packages').getAll()
          all.onsuccess = () => { db.close(); resolve(all.result) }
        }
        open.onerror = () => resolve([])
      })
      for (const r of rows) out.push({ db: d.name, id: r.document.id, revision: r.revision })
    }
    return out
  })
  const download = async () => {
    await page.goto(base + '/read/motion')
    await page.locator('.passage').first().waitFor()
    await page.getByRole('button', { name: 'Download' }).click()
    await page.getByText('Chapter downloaded').waitFor()
  }
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base)
  await page.evaluate(async () => {
    localStorage.clear()
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
    for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister()
    for (const k of await caches.keys()) await caches.delete(k)
  })
  try {
    await download()
    let rows = await stored()
    ok('the sample student keeps downloads in the original store', rows.length === 1 && rows[0].db === 'pathya' && rows[0].revision === 1)

    // The server moves to a newer revision while the app is closed.
    await page.evaluate((k) => localStorage.setItem(k, JSON.stringify({ motion: { revision: 5, blocks: {} } })), SERVER)
    await page.goto(base)
    await page.getByText('One downloaded chapter was updated to the latest revision.').waitFor()
    rows = await stored()
    ok('a changed chapter is refreshed on start', rows.length === 1 && rows[0].revision === 5)

    // The chapter is deleted on the server, or access is taken away.
    await page.evaluate((k) => localStorage.setItem(k, JSON.stringify({ motion: { revision: 5, blocks: {}, deleted: true } })), SERVER)
    await page.goto(base)
    await page.getByText('no longer available to you').waitFor()
    ok('a chapter that is gone on the server is deleted from the device', (await stored()).length === 0)

    // Signing out on purpose clears the account's copies.
    await page.evaluate((k) => localStorage.removeItem(k), SERVER)
    await download()
    await page.goto(base)
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
    await page.locator('aside').first().getByRole('button', { name: 'Sign out' }).click()
    await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
    await page.waitForTimeout(500)
    ok('signing out deletes the downloads', (await stored()).length === 0)

    // A second person on the same device gets a separate store.
    await page.getByRole('button', { name: 'Create an account' }).click()
    await page.getByLabel('Email address').fill('asha@school.example')
    await page.getByLabel('Password', { exact: true }).fill('river stone lantern 42')
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
    await download()
    rows = await stored()
    ok('another account downloads into its own store', rows.length === 1 && rows[0].db.startsWith('pathya.') && rows[0].db !== 'pathya')

    // The session ends without signing out, and the sample student uses the device next.
    await page.evaluate(() => { localStorage.removeItem('pathya.mock.session.v1'); localStorage.removeItem('pathya.user.v1') })
    await page.goto(base + '/downloads')
    await page.getByRole('heading', { level: 1 }).first().waitFor()
    await page.waitForTimeout(800)
    const side = await page.locator('aside').first().innerText()
    const main = await page.locator('main').innerText()
    ok('the next person does not see the download of the other account', side.includes('student@pathya.example') && main.includes('Nothing is downloaded yet'))
    ok('the copy of the other account is still kept for them', (await stored()).length === 1)
  } catch (e) { log.push('FAIL  stopped: ' + String(e.message).split('\n').slice(0, 3).join(' | ')) }
  await page.context().setOffline(false)
  await page.goto(base).catch(() => {})
  await page.evaluate(async () => {
    localStorage.clear()
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
  }).catch(() => {})
  return log.join('\n')
}
