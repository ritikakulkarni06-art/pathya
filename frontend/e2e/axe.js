// Accessibility scan with axe-core on every screen, in all three colour themes.
async (page) => {
  const base = 'http://localhost:4173'
  const out = []
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  for (const theme of ['light', 'dark', 'contrast']) {
    for (const path of ['/', '/read/motion', '/read/bal-gati', '/downloads', '/settings', '/add', '/review', '/chapter/motion']) {
      await page.goto(base + path)
      await page.evaluate((t) => { const s = JSON.parse(localStorage.getItem('pathya.prefs.v1') || '{"state":{},"version":0}'); s.state.theme = t; localStorage.setItem('pathya.prefs.v1', JSON.stringify(s)) }, theme)
      await page.reload()
      await page.locator('h1').first().waitFor()
      await page.waitForTimeout(2600)
      await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
      const res = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] }))
      for (const v of res.violations) out.push(`${theme} ${path}  ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0].target.join(' ')} ${(v.nodes[0].any[0]?.message || '').slice(0, 110)}`)
    }
  }
  await page.evaluate(() => localStorage.removeItem('pathya.prefs.v1'))
  return out.length ? out.join('\n') : 'axe: 0 violations on 8 screens x 3 themes'
}
