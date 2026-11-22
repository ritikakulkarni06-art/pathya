// Prepares narration clips for the English text of the sample chapters with Piper,
// a free voice model that runs on this laptop. One WAV per sentence, listed under the same key Role 3 uses
// (passage, text hash, sentence number, voice language), so a corrected sentence never plays old audio.
//
//   npm run audio                      (default voice: en_US-lessac-medium)
//   npm run audio -- en_GB-cori-medium (after: .venv/Scripts/python -m piper.download_voices <name> --download-dir tools/voices)
//
// In the real system this job belongs to the backend (Role 3); the reader only plays the clips.
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { SAMPLE_PACKAGES } from '../src/data/chapters.ts'
import { unitsFor } from '../src/lib/sentences.ts'
import { unitClipKey } from '../src/lib/hash.ts'

const voice = process.argv[2] ?? 'en_US-lessac-medium'
const model = `tools/voices/${voice}.onnx`
if (!existsSync(model)) throw new Error(`Voice model not found: ${model}`)
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'

// File name: a short hash of the spoken text, so identical sentences share one file.
const fileOf = (lang, text) => createHash('sha1').update(`${lang}|${text}`).digest('hex').slice(0, 16)

// What the voice should say for symbols it would otherwise spell out or skip.
const spoken = (t) =>
  t
    .replace(/−/g, ' minus ')
    .replace(/½/g, ' one half ')
    .replace(/m\/s²/g, 'metres per second squared')
    .replace(/km\/h/g, 'kilometres per hour')
    .replace(/m\/s/g, 'metres per second')
    .replace(/(\d)\s?kg\b/g, '$1 kilograms')
    .replace(/(\d)\s?m\b/g, '$1 metres')
    .replace(/(\d)\s?s\b/g, '$1 seconds')
    .replace(/—/g, ', ')
    .replace(/\s+/g, ' ')
    .trim()

for (const pkg of SAMPLE_PACKAGES) {
  const dir = `public/audio/${pkg.document.id}`
  rmSync(dir, { recursive: true, force: true })
  rmSync(`public/audio/${pkg.document.id}.json`, { force: true })
  const texts = new Map()
  const keys = []
  for (const block of pkg.blocks)
    for (const u of unitsFor(block, true))
      if (u.lang === 'en') {
        texts.set(fileOf(u.lang, u.text), u.text)
        keys.push([await unitClipKey(u, block.text_current), fileOf(u.lang, u.text)])
      }
  if (!texts.size) continue
  mkdirSync(dir, { recursive: true })
  const jobs = [...texts].map(([key, text]) => JSON.stringify({ text: spoken(text), out: `${dir}/${key}.wav` })).join('\n')
  const run = spawnSync(python, ['tools/piper_batch.py', model], { input: jobs, encoding: 'utf8', stdio: ['pipe', 'pipe', 'inherit'] })
  if (run.status !== 0) throw new Error('Piper failed')
  const audio = keys.map(([key, file]) => ({ key, url: `/audio/${pkg.document.id}/${file}.wav`, bytes: statSync(`${dir}/${file}.wav`).size }))
  writeFileSync(`public/audio/${pkg.document.id}.json`, JSON.stringify({ voice, audio }))
  console.log(`${pkg.document.id}: ${audio.length} clips, ${(audio.reduce((n, a) => n + a.bytes, 0) / 1e6).toFixed(1)} MB, voice ${voice}`)
}
