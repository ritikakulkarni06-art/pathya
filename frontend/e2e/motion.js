// Checks the motion layer: entrance finishes with everything visible, the book cover opens on hover,
// the nav pill follows the page, the sound wave runs while playing, and "Reduce motion" turns it off.
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  // Read a little first, so the library has a "Continue reading" banner to animate.
  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.getByLabel('Go to printed page').fill('38')
  await page.getByLabel('Go to printed page').press('Enter')
  await page.waitForTimeout(1200)
  await page.goto(base)
  // Watch the first card for 3 seconds and remember the lowest opacity it had.
  const mid = await page.evaluate(() => new Promise((resolve) => {
    let low = 1
    const t0 = performance.now()
    const tick = () => {
      const card = document.querySelector('[data-card]')
      if (card) low = Math.min(low, Number(getComputedStyle(card).opacity))
      if (performance.now() - t0 < 3000) requestAnimationFrame(tick)
      else resolve(low)
    }
    tick()
  }))
  const end = await page.evaluate(() => [...document.querySelectorAll('[data-hero],[data-card],[data-side]')].every((el) => getComputedStyle(el).opacity === '1' && getComputedStyle(el).visibility === 'visible'))
  ok(`cards fade in (lowest opacity seen ${mid.toFixed(2)})`, mid < 0.5)
  ok('everything is fully visible when the entrance ends', end)
  const settled = await page.evaluate(() => {
    const btn = getComputedStyle(document.querySelector('[data-hero] a'))
    const card = document.querySelector('[data-card]').getBoundingClientRect().top
    const side = document.querySelectorAll('[data-card]')[1].getBoundingClientRect().top
    return { button: btn.visibility === 'visible' && btn.opacity === '1', aligned: Math.abs(card - side) < 1 }
  })
  ok('the Resume button is visible after the entrance', settled.button)
  ok('cards settle level with each other', settled.aligned)

  await page.locator('[data-card]').first().hover()
  await page.waitForTimeout(700)
  const board = await page.evaluate(() => getComputedStyle(document.querySelector('.book-board')).transform)
  ok('book cover swings open on hover', board.startsWith('matrix3d'))
  await page.screenshot({ path: 'e2e/shots/library-hover-1440.png' })

  await page.getByRole('link', { name: 'Settings', exact: true }).click()
  await page.getByRole('heading', { name: 'Settings', level: 1 }).waitFor()
  await page.waitForTimeout(700)
  const pill = await page.evaluate(() => { const p = document.querySelector('nav span[aria-hidden]').getBoundingClientRect(); const a = document.querySelector('nav [aria-current=page]').getBoundingClientRect(); return Math.abs(p.top - a.top) < 2 && Math.abs(p.height - a.height) < 2 })
  ok('nav pill lands on the current page', pill)

  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.waitForTimeout(800)
  await page.locator('footer .btn-primary').click()
  await page.waitForTimeout(1200)
  ok('sound wave runs while playing', await page.evaluate(() => getComputedStyle(document.querySelector('.wave i')).animationName === 'wave'))
  await page.keyboard.press('Alt+Shift+KeyP')
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await page.waitForTimeout(400)
  ok('reading-progress line fills at the end', await page.evaluate(() => document.querySelector('header [aria-hidden].bg-primary').getBoundingClientRect().width > innerWidth * 0.95))

  // Reduce motion: no entrance, no cover swing.
  await page.evaluate(() => { const s = JSON.parse(localStorage.getItem('pathya.prefs.v1') || '{"state":{},"version":0}'); s.state.reduceMotion = true; localStorage.setItem('pathya.prefs.v1', JSON.stringify(s)) })
  await page.goto(base)
  await page.locator('[data-card]').first().waitFor()
  await page.waitForTimeout(150)
  ok('reduce motion: cards appear at once', (await page.evaluate(() => getComputedStyle(document.querySelector('[data-card]')).opacity)) === '1')
  await page.locator('[data-card]').first().hover()
  await page.waitForTimeout(300)
  ok('reduce motion: cover stays closed', (await page.evaluate(() => getComputedStyle(document.querySelector('.book-board')).transform)) === 'none')
  await page.evaluate(() => localStorage.removeItem('pathya.prefs.v1'))
  return log.join('\n')
}
