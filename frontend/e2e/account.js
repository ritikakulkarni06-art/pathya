// Forgot password, the reset link, and sharing a chapter with another account (built-in stand-in API).
async (page) => {
  const base = 'http://localhost:4173'
  const log = []
  const ok = (name, cond) => log.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
  const axe = async (name) => {
    await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
    const res = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] }))
    ok(`${name} has no accessibility problems${res.violations.length ? ': ' + res.violations.map((v) => v.id).join(', ') : ''}`, res.violations.length === 0)
  }
  const signOut = async () => {
    await page.goto(base)
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
    await page.locator('aside').first().getByRole('button', { name: 'Sign out' }).click()
    await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
  }
  const create = async (email, password) => {
    await page.getByRole('button', { name: 'Create an account' }).click()
    await page.getByLabel('Email address').fill(email)
    await page.getByLabel('Password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
  }
  await page.context().setOffline(false)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base)
  await page.evaluate(async () => {
    localStorage.clear()
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
  })
  try {
    // Two accounts: Meera owns nothing special; Asha will share with her.
    await page.goto(base)
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
    await signOut()
    await create('meera@school.example', 'paper kite monsoon 17')
    await signOut()
    await create('asha@school.example', 'river stone lantern 42')

    // ---- sharing ----
    await page.goto(base + '/chapter/motion')
    const share = page.getByRole('region', { name: 'Share with classmates' })
    await share.getByText('Only you can open this chapter.').waitFor()
    ok('chapter details has a sharing section for the owner', true)
    await share.getByLabel('Classmate’s email address').fill('nobody@school.example')
    await share.getByRole('button', { name: 'Share', exact: true }).click()
    const alert = share.getByRole('alert')
    await alert.waitFor()
    ok('an address without an account is refused with a plain reason', (await alert.innerText()).includes('No Pathya account uses that address'))
    ok('the refusal takes focus so it is announced', await alert.evaluate((e) => e === document.activeElement))
    await share.getByLabel('Classmate’s email address').fill('Meera@School.example')
    await share.getByLabel('What they can do').selectOption('reviewer')
    await share.getByRole('button', { name: 'Share', exact: true }).click()
    await share.getByText('meera@school.example').waitFor()
    ok('a classmate is added by email and listed with what they can do', (await share.innerText()).includes('Can also review and correct'))
    await axe('chapter details with sharing')
    await share.getByRole('button', { name: 'Remove access for meera@school.example' }).click()
    await share.getByText('Only you can open this chapter.').waitFor()
    ok('access can be removed again', true)

    // ---- forgot password ----
    await signOut()
    await page.getByRole('button', { name: 'Forgot your password?' }).click()
    await page.getByRole('heading', { name: 'Reset your password', level: 1 }).waitFor()
    ok('sign in offers "Forgot your password?"', true)
    ok('the reset form asks only for the email address', (await page.getByLabel('Password', { exact: true }).count()) === 0)
    await axe('reset request screen')
    await page.getByLabel('Email address').fill('ghost@school.example')
    await page.getByRole('button', { name: 'Send reset link' }).click()
    const sent = page.getByRole('status').filter({ hasText: 'is on its way' })
    await sent.waitFor()
    ok('an unknown address gets the same answer (no account is revealed)', (await page.evaluate(() => localStorage.getItem('pathya.mock.outbox.v1'))) === null)
    await page.getByLabel('Email address').fill('asha@school.example')
    await page.getByRole('button', { name: 'Send reset link' }).click()
    await page.waitForFunction(() => localStorage.getItem('pathya.mock.outbox.v1'))
    const link = await page.evaluate(() => JSON.parse(localStorage.getItem('pathya.mock.outbox.v1')).link)
    ok('a reset link is sent for a known address', link.includes('/reset-password?token='))

    await page.goto(link)
    await page.getByRole('heading', { name: 'Choose a new password', level: 1 }).waitFor()
    ok('the link opens "Choose a new password"', (await page.getByLabel('Email address').count()) === 0)
    await axe('choose a new password screen')
    await page.getByLabel('New password').fill('short')
    await page.getByRole('button', { name: 'Save new password' }).click()
    ok('a short new password is refused before sending', (await page.getByRole('alert').innerText()).includes('at least 12 characters'))
    await page.getByLabel('New password').fill('blue harbour pepper 88')
    await page.getByRole('button', { name: 'Save new password' }).click()
    await page.getByRole('heading', { name: 'Sign in', level: 1 }).waitFor()
    ok('after saving, the sign-in screen says the password changed', (await page.getByRole('status').first().innerText()).includes('Your password was changed'))
    ok('the address bar no longer holds the token', !page.url().includes('token'))

    await page.getByLabel('Email address').fill('asha@school.example')
    await page.getByLabel('Password', { exact: true }).fill('river stone lantern 42')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.getByRole('alert').waitFor()
    ok('the old password no longer works', (await page.getByRole('alert').innerText()).includes('incorrect'))
    await page.getByLabel('Password', { exact: true }).fill('blue harbour pepper 88')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.getByRole('heading', { name: 'Library', level: 1 }).waitFor()
    ok('the new password signs in', true)

    await signOut()
    await page.goto(link)
    await page.getByLabel('New password').fill('another fresh phrase 99')
    await page.getByRole('button', { name: 'Save new password' }).click()
    await page.getByRole('alert').waitFor()
    ok('a reset link works only once', (await page.getByRole('alert').innerText()).includes('expired or was already used'))
  } catch (e) { log.push('FAIL  stopped: ' + String(e.message).split('\n').slice(0, 3).join(' | ')) }
  await page.goto(base).catch(() => {})
  await page.evaluate(async () => {
    localStorage.clear()
    for (const d of await indexedDB.databases()) indexedDB.deleteDatabase(d.name)
  }).catch(() => {})
  return log.join('\n')
}
