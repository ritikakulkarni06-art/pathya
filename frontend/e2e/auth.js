// Sign in, create account and sign out (Role 3's session API; here against the built-in stand-in).
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
    for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister()
    for (const k of await caches.keys()) await caches.delete(k)
  })
  try {
  await page.goto(base)
  const side = page.locator('aside').first()
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  ok('sample build starts signed in as the sample student', (await side.innerText()).includes('student@pathya.example'))

  await side.getByRole('button', { name: 'Sign out' }).click()
  const h1 = page.getByRole('heading', { level: 1 })
  await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
  ok('signing out shows the sign-in screen', (await page.locator('main li.book').count()) === 0)
  await page.goto(base + '/read/motion')
  await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
  ok('a chapter link does not open while signed out', (await page.locator('.passage').count()) === 0)

  const alert = page.getByRole('alert')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await alert.waitFor()
  ok('empty form says what is missing', (await alert.innerText()).includes('email address'))
  ok('the message receives focus', await alert.evaluate((el) => el === document.activeElement))

  await page.getByLabel('Email address').fill('asha@school.example')
  await page.getByLabel('Password', { exact: true }).fill('not-my-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByText('The email or password is incorrect.').waitFor()
  ok('unknown account gets the same message as a wrong password', true)

  await page.getByRole('button', { name: 'Create an account' }).click()
  await page.getByRole('heading', { name: 'Create your account', level: 1 }).waitFor()
  ok('switching to create account moves focus to the heading', await h1.evaluate((el) => el === document.activeElement))
  await page.getByLabel('Password', { exact: true }).fill('short')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await page.getByText(/at least 12 characters\. Yours has 5/).waitFor()
  ok('a short password says how long it must be', true)

  const show = page.getByRole('button', { name: 'Show password' })
  await show.click()
  ok('show password reveals the text and reports its state', (await page.getByLabel('Password', { exact: true }).getAttribute('type')) === 'text' && (await show.getAttribute('aria-pressed')) === 'true')

  await page.setViewportSize({ width: 320, height: 640 })
  await page.waitForTimeout(200)
  ok('no sideways scroll at 320px', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.setViewportSize({ width: 1440, height: 900 })

  const axeOut = []
  for (const theme of ['light', 'dark', 'contrast']) {
    await page.evaluate((t) => { document.documentElement.dataset.theme = t }, theme)
    await page.waitForTimeout(300)
    if (theme === 'light') await page.screenshot({ path: 'e2e/shots/signin.png' })
    await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
    const res = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] }))
    for (const v of res.violations) axeOut.push(`${theme} ${v.id} (${v.impact}): ${v.nodes[0].target.join(' ')} ${(v.nodes[0].any[0]?.message || '').slice(0, 110)}`)
  }
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light' })
  ok('axe: no violations on the sign-in screen in 3 themes', axeOut.length === 0)
  log.push(...axeOut)

  await page.getByLabel('Password', { exact: true }).fill('river stone lantern 42')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await page.locator('.passage').first().waitFor()
  ok('creating an account signs in and opens the chapter that was asked for', page.url().endsWith('/read/motion'))
  await page.goto(base)
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  ok('the menu shows who is signed in', (await side.innerText()).includes('asha@school.example'))

  await page.reload()
  await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  ok('still signed in after a reload', (await side.innerText()).includes('asha@school.example'))

  await page.goto(base + '/settings')
  await page.getByRole('heading', { name: 'Account' }).waitFor()
  await page.locator('main').getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
  await page.getByRole('button', { name: 'Create an account' }).click()
  await page.getByLabel('Email address').fill('Asha@school.example')
  await page.getByLabel('Password', { exact: true }).fill('another long password')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await page.getByText('This account cannot be registered. Try signing in.').waitFor()
  ok('an email that is already registered cannot be registered again', true)

  await page.getByRole('button', { name: 'Sign in instead' }).click()
  await page.getByLabel('Password', { exact: true }).fill('river stone lantern 42')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('heading', { name: 'Settings', level: 1 }).waitFor()
  ok('signing in returns to the page that was open', page.url().endsWith('/settings'))

  } catch (e) { log.push('FAIL  stopped: ' + String(e.message).split('\n').slice(0, 3).join(' | ')) }
  await page.evaluate(() => localStorage.clear())
  ok('no console errors', errors.length === 0)
  if (errors.length) log.push(errors.slice(0, 3).join('\n'))
  return log.join('\n')
}
