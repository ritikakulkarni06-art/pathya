# Pathya reader (Role 2)

The student-facing reader for Pathya: find, read, listen, review, download and resume a textbook chapter in English or Hindi.

## Run it

```
npm install
npm run dev          # development, http://localhost:5173
npm run build && npm run preview   # production build with offline support, http://localhost:4173
```

Offline reading needs the production build (`preview`), because the service worker is only generated there.

## Tests

With `npm run preview` running in another terminal:

```
npm run test:e2e
```

`e2e/flow.js` walks the whole student flow in a real browser (24 checks, screenshots in `e2e/shots/`).
`e2e/axe.js` runs axe-core on every screen in all three colour themes.
`e2e/add.js` checks the upload form's messages and the job progress states.
`e2e/audio.js` checks that prepared narration clips play online and after an offline restart (needs `npm run audio` first).
`e2e/motion.js` checks the animations, and that "Reduce motion" turns them off.
`e2e/roles.js` checks the screens built for the other roles' features (24 checks, see below).
`e2e/p1.js` checks that Role 1's contract sample opens and reads correctly (15 checks).
`e2e/auth.js` checks sign in, create account and sign out (17 checks).
`e2e/tour.js` only takes a screenshot of every screen.

## English narration (Piper)

English sentences are narrated from clips made by Piper, a free voice model that runs on the laptop.
Hindi, and any sentence without a clip (for example one that was just corrected), uses a voice installed on the device.

One-time setup:

```
py -m venv .venv
.venv\Scripts\python -m pip install piper-tts
.venv\Scripts\python -m piper.download_voices en_US-lessac-medium --download-dir tools/voices
```

Make the clips, then rebuild:

```
npm run audio
npm run build
```

Clips land in `public/audio/<chapter>/` with a list in `public/audio/<chapter>.json`. Each clip is named by a
hash of its sentence, so changed text can never play old audio. To try another voice, download it the same way
and run `npm run audio -- <voice name>`. In the real system this job belongs to the backend.

## How it connects to the other roles

- `src/types.ts` is the content contract (blocks, pages, revisions). Agree changes with Role 1 and Role 3 first.
- `src/api/client.ts` is the only place that talks to the backend. Set `VITE_API_URL` to use Role 3's API.
  Without it the app uses a built-in mock with the same behaviour (revisions, conflicts, evidence, abstention).
- `src/data/chapters.ts` holds two sample chapters written for development. Replace them with real packages.

### Role 1 content contract (1.0.0 and 1.1.0)

`src/lib/p1.ts` converts a Role 1 document into what the reader shows. `src/data/p1-sample.json` is a copy of
`contract/samples/sample_document_en_hi.json` from the team repo and appears as the third sample chapter.
Where the contract does not say enough, the converter guesses. Each guess is marked `GAP` in the code:

- no heading level (uses the layout label, else the first heading is the title)
- page headers and footers arrive as paragraphs (skipped by layout label)
- `mul` and `und` languages (voice picked by counting Hindi and English letters)
- `review_status` is never set by the pipeline (a passage with any quality flag is treated as needing review)
- no document-level revision
- corrections cannot change the passage kind or reading order, although the reader's form offers both

Supported from 1.1.0: page status and warnings (a page that was not read says so on screen and in narration),
pages without a printed number, uncertain tables, and merged table headers (repeated over each column they cover).
`npm run test:p1` checks the converter without a browser; pass extra Role 1 JSON files as arguments.

Screens that exist because of the other roles' features. Each one calls the API below; the paths are this
reader's proposal and still need Role 3's agreement.

| Screen | For | API call the backend must provide |
|---|---|---|
| Review desk (`/review`): every flagged passage with its reason, confidence and place on the page | Role 1 quality flags and review states | `GET /documents`, `GET /documents/:id/manifest` |
| Correction form: words, plus language, passage kind and reading order | Role 1 content operations | `PATCH /blocks/:id` with `operations`: `replace_text`, `set_language`, `set_type`, `move` |
| Chapter details (`/chapter/:id`): quality summary, what is on the current revision, correction history | Role 1 evaluation, Role 3 revisions and rebuilds | `GET /documents/:id/revisions` |
| Remove chapter (on chapter details) | Role 3 deletion | `DELETE /documents/:id` |
| Your uploads, with cancel and try again (`/add`) | Role 3 jobs and retries | `GET /jobs`, `POST /jobs/:id/cancel`, `POST /jobs/:id/retry` |
| Questions left today (Ask panel) | Role 3 usage limits | `GET /usage`, `usage` in each answer, HTTP 429 when used up |

Sign-in (`src/routes/SignIn.tsx`, `src/api/auth.ts`, `src/state/auth.ts`) follows Role 3's session API: `POST /auth/register`,
`POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, with the `pathya_csrf` cookie echoed in `X-CSRF-Token` on writes.
It has only been run against the built-in stand-in, where the app starts signed in as a sample student.
Sharing a chapter with another person (`POST /documents/:id/grants`) has no screen yet.

## Where things are

| Path | What |
|---|---|
| `src/routes/` | Library, Reader, Review desk, Chapter details, Add chapter, Downloads, Settings |
| `src/components/` | Sidebar shell, correction form, page thumbnail, settings controls |
| `src/components/reader/` | Passage view, contents/bookmarks/search, review, ask, source page, narration player |
| `src/lib/sentences.ts` | Sentence splitting, what the narrator says for tables/equations/figures, pronunciation overrides |
| `src/lib/speech.ts` | Speech adapter (device voice now, prepared clips when the backend supplies them) |
| `src/lib/db.ts` | IndexedDB (text, bookmarks, positions, queued corrections) and Cache Storage (audio, page images) |
| `src/state/` | Preferences, narration, chapter loading and correction sync |

Narration shortcuts: Alt+Shift+P play/pause, Alt+Shift+Left/Right previous/next sentence.
