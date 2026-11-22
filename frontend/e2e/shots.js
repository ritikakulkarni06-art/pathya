// Takes screenshots of the main screens for a visual check. Run after e2e/flow.js so there is reading history.
async (page) => {
  const base = 'http://localhost:4173'
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base + '/read/motion')
  await page.locator('.passage').first().waitFor()
  await page.getByLabel('Go to printed page').fill('38')
  await page.getByLabel('Go to printed page').press('Enter')
  await page.waitForTimeout(1200)
  await page.locator('footer .btn-primary').click()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'e2e/shots/reader-1440.png' })
  await page.keyboard.press('Alt+Shift+KeyP')
  await page.goto(base)
  await page.getByRole('heading', { name: 'Continue reading' }).waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'e2e/shots/library-1440.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: 'e2e/shots/library-390.png' })
  return 'ok'
}
