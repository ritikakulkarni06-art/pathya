// Checks the "Add a chapter" screen: validation messages and the job progress states.
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base + '/add')
  await page.waitForTimeout(1200)
  await page.reload()
  await page.getByRole('heading', { name: 'Add a chapter', level: 1 }).waitFor()

  await page.getByRole('button', { name: 'Upload and prepare' }).click()
  await page.getByRole('alert').filter({ hasText: 'Choose a PDF' }).waitFor({ timeout: 3000 }).catch(() => {})
  ok('empty form explains what is missing', await page.getByRole('alert').filter({ hasText: 'Choose a PDF' }).isVisible())
  ok('error message receives focus', await page.waitForFunction(() => document.activeElement?.id === 'add-error', null, { timeout: 3000 }).then(() => true, () => false))

  await page.getByLabel('Chapter file').setInputFiles({ name: 'notes.pdf', mimeType: 'application/pdf', buffer: Buffer.from('this is not really a pdf') })
  await page.getByRole('button', { name: 'Upload and prepare' }).click()
  ok('a fake PDF is rejected by its contents', await page.getByText('does not look like a PDF').waitFor({ timeout: 5000 }).then(() => true, () => false))

  await page.getByLabel('Chapter file').setInputFiles({ name: 'light_chapter-10.pdf', mimeType: 'application/pdf', buffer: Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.alloc(600000, 32)]) })
  ok('title is suggested from the file name', (await page.getByLabel('Chapter title').inputValue()) === 'notes')
  await page.getByLabel('Chapter title').fill('Light')
  await page.getByRole('button', { name: 'Upload and prepare' }).click()
  ok('permission must be confirmed', await page.getByText('Confirm that you are allowed').waitFor({ timeout: 5000 }).then(() => true, () => false))
  await page.getByLabel(/I am allowed to use this chapter/).check()
  await page.screenshot({ path: 'e2e/shots/add-form-1440.png' })
  await page.getByRole('button', { name: 'Upload and prepare' }).click()

  await page.getByText(/Reading page \d of 4/).waitFor({ timeout: 15000 })
  ok('page progress is announced', (await page.locator('progress').count()) === 1)
  await page.screenshot({ path: 'e2e/shots/add-progress-1440.png' })
  await page.getByText('This file could not be prepared.').waitFor({ timeout: 20000 })
  ok('a stopped job says why, in plain words', await page.getByText('no preparation server connected').isVisible())
  await page.setViewportSize({ width: 390, height: 844 })
  ok('no sideways scroll on a phone', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.screenshot({ path: 'e2e/shots/add-390.png' })
  return log.join('\n')
}
