// Lets Node run the app's TypeScript modules directly (as Vite does): adds the missing ".ts" to
// extensionless imports and treats imported ".json" files as JSON.
import { register } from 'node:module'

const hook = `
export async function resolve(spec, ctx, next) {
  if (spec.endsWith('.json')) {
    const r = await next(spec, { ...ctx, importAttributes: { type: 'json' } })
    return { ...r, importAttributes: { type: 'json' } }
  }
  try {
    return await next(spec, ctx)
  } catch (e) {
    if (e.code !== 'ERR_MODULE_NOT_FOUND' || !spec.startsWith('.')) throw e
    return next(spec + '.ts', ctx)
  }
}`
register('data:text/javascript,' + encodeURIComponent(hook))
