// Screenshots of every screen, for a visual check. Usage: playwright-cli run-code --filename=e2e/tour.js
async (page) => {
  const base = 'http://localhost:4173'
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.getByLabel('Go to printed page').fill('38')
  await page.getByLabel('Go to printed page').press('Enter')
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'e2e/shots/tour-reader.png' })
  for (const [name, path] of [['home', '/'], ['review', '/review'], ['chapter', '/chapter/motion'], ['downloads', '/downloads'], ['settings', '/settings'], ['add', '/add']]) {
    await page.goto(base + path)
    await page.waitForTimeout(2600)
    await page.screenshot({ path: `e2e/shots/tour-${name}.png`, fullPage: true })
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(base)
  await page.waitForTimeout(2600)
  await page.screenshot({ path: 'e2e/shots/tour-home-390.png', fullPage: true })
  return 'ok'
}
