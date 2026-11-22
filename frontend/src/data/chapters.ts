// SAMPLE CONTENT. Two short chapters written by the team for development, standing in for
// Role 1's extraction output. Replace with real packages from the backend (see src/api/client.ts).
import type { Block, BlockType, ChapterPackage, Lang, Page } from '../types'
import { fromP1 } from '../lib/p1'
import p1Sample from './p1-sample.json'

type Extra = Partial<Omit<Block, 'id' | 'page_id' | 'type' | 'text_raw' | 'text_current' | 'lang'>>

function build(
  docId: string,
  lang: Lang,
  firstPrinted: number,
  spec: [page: number, type: BlockType, text: string, extra?: Extra][],
): { pages: Page[]; blocks: Block[] } {
  const pageCount = Math.max(...spec.map((s) => s[0])) + 1
  const pages: Page[] = Array.from({ length: pageCount }, (_, i) => ({
    id: `${docId}-p${i}`,
    pdf_index_0: i,
    printed_label: String(firstPrinted + i),
  }))
  const cursor: number[] = Array(pageCount).fill(0.07)
  const blocks = spec.map(([page, type, text, extra], i): Block => {
    const h = type === 'heading' ? 0.05 : type === 'table' || type === 'figure' ? 0.2 : type === 'equation' ? 0.06 : Math.min(0.2, 0.045 + text.length / 2600)
    const y0 = cursor[page]
    cursor[page] = y0 + h + 0.018
    return {
      id: `${docId}-b${String(i + 1).padStart(2, '0')}`,
      page_id: pages[page].id,
      type,
      order_key: i,
      bbox: [0.1, y0, 0.9, y0 + h],
      text_raw: text,
      text_current: text,
      lang,
      revision: 1,
      status: 'trusted',
      confidence: { engine: 'tesseract-5', score: 0.96, flags: [] },
      provenance: { parser: 'docling+tesseract', version: '0.1-sample' },
      ...extra,
    }
  })
  return { pages, blocks }
}

const flag = (code: string, score: number): Extra => ({
  status: 'needs_review',
  confidence: { engine: 'tesseract-5', score, flags: [code] },
})

const motion = build('motion', 'en', 36, [
  [0, 'heading', 'Motion in a straight line', { level: 1 }],
  [0, 'paragraph', 'A body is in motion when its position changes with time. To describe motion we first choose a reference point, called the origin. Every position is then measured from that point.'],
  [0, 'heading', 'Distance and displacement', { level: 2 }],
  [0, 'paragraph', 'Distance is the total length of the path a body covers. Displacement is the shortest straight line from the starting point to the final point, together with its direction. A runner who completes one full lap of a 400 m track covers a distance of 400 m, but her displacement is zero.'],
  [0, 'paragraph', 'Remember: distance can never be negative, but displacement can be positive, negative or zero.', { ...flag('column_order_uncertain', 0.9), bbox: [0.62, 0.62, 0.9, 0.74] }],
  [1, 'heading', 'Speed and velocity', { level: 2 }],
  [1, 'paragraph', 'Speed tells us how fast a body moves. Average speed is the total distance divided by the total time taken. Velocity is speed in a stated direction, so it is found from displacement rather than distance.'],
  [1, 'equation', 'average speed = total distance / total time', {
    mathml: '<math display="block"><msub><mi>v</mi><mtext>av</mtext></msub><mo>=</mo><mfrac><mi>s</mi><mi>t</mi></mfrac></math>',
    spoken: 'Average speed equals total distance s, divided by total time t.',
    status: 'reviewed',
  }],
  [1, 'paragraph', 'The SI unit of both speed and velocity is the metre per second, written m/s. A speed of 36 km/h is the same as 10 m/s.'],
  [1, 'table', 'Table 3.1 Distance covered by a cyclist', {
    table: {
      caption: 'Table 3.1 Distance covered by a cyclist',
      columns: ['Time (s)', 'Distance (m)', 'Speed in interval (m/s)'],
      rows: [['0', '0', '—'], ['10', '40', '4.0'], ['20', '100', '6.0'], ['30', '160', '6.0'], ['40', '190', '3.0']],
      numeric: [true, true, true],
    },
  }],
  [1, 'paragraph', 'Between 10 s and 30 s the cyclist covers equal distances in equal intervals, so the motion is uniform. In the last interval the cyclist slows down.'],
  [2, 'heading', 'Acceleration', { level: 2 }],
  [2, 'paragraph', 'Acceleration is the rate at which velocity changes. If the velocity of a body changes from an initial value u to a final value v in time t, the acceleration is the change in velocity divided by the time.'],
  [2, 'equation', 'a = (v − u) / t', {
    mathml: '<math display="block"><mi>a</mi><mo>=</mo><mfrac><mrow><mi>v</mi><mo>−</mo><mi>u</mi></mrow><mi>t</mi></mfrac></math>',
    spoken: 'a equals a fraction. Numerator: v minus u. Denominator: t.',
    status: 'reviewed',
  }],
  [2, 'paragraph', 'A car moving at 20 m/s brakes and comes down to 10 m/s in 5 s. Its acceleration is 2 m/s². The negative sign shows that the car is slowing down.', flag('possible_missing_minus', 0.71)],
  [2, 'paragraph', 'An acceleration that reduces speed is sometimes called retardation or deceleration.'],
  [2, 'figure', 'Figure 3.2 Velocity–time graph of a braking car', {
    status: 'reviewed',
    figure: {
      caption: 'Figure 3.2 Velocity–time graph of a braking car',
      alt: 'Line graph falling from 20 m/s to 10 m/s over 5 s.',
      description: 'The horizontal axis shows time from 0 to 5 seconds. The vertical axis shows velocity from 0 to 20 metres per second. A straight line starts at 20 metres per second at time zero and falls evenly to 10 metres per second at 5 seconds. The downward slope shows a constant negative acceleration.',
      description_origin: 'teacher',
    },
  }],
  [3, 'heading', 'Equations of uniformly accelerated motion', { level: 2 }],
  [3, 'paragraph', 'When acceleration is constant, three equations connect u, v, a, t and the displacement s.'],
  [3, 'equation', 'v = u + at', {
    mathml: '<math display="block"><mi>v</mi><mo>=</mo><mi>u</mi><mo>+</mo><mi>a</mi><mi>t</mi></math>',
    spoken: 'v equals u plus a times t.',
    status: 'reviewed',
  }],
  [3, 'equation', 's = ut + ½at²', {
    mathml: '<math display="block"><mi>s</mi><mo>=</mo><mi>u</mi><mi>t</mi><mo>+</mo><mfrac><mn>1</mn><mn>2</mn></mfrac><mi>a</mi><msup><mi>t</mi><mn>2</mn></msup></math>',
    spoken: 's equals u times t, plus one half a times t squared.',
    status: 'reviewed',
  }],
  [3, 'equation', 'v² = u² + 2as', {
    mathml: '<math display="block"><msup><mi>v</mi><mn>2</mn></msup><mo>=</mo><msup><mi>u</mi><mn>2</mn></msup><mo>+</mo><mn>2</mn><mi>a</mi><mi>s</mi></math>',
    spoken: 'v squared equals u squared plus 2 times a times s.',
    status: 'reviewed',
  }],
  [3, 'paragraph', 'Example 3.2: A trolley starts from rest and accelerates at 0.5 m/s² for 8 s. Its final velocity is 4 m/s and it covers l6 m.', flag('low_ocr_confidence', 0.64)],
  [4, 'heading', 'Exercises', { level: 2 }],
  [4, 'list_item', '1. A bus travels 150 m in 12 s. Find its average speed.'],
  [4, 'list_item', '2. State one difference between distance and displacement.'],
  [4, 'list_item', '3. A scooter slows from 15 m/s to 5 m/s in 4 s. Calculate its acceleration.'],
  [4, 'list_item', '4. Using Table 3.1, in which interval is the cyclist fastest?'],
  [4, 'figure', 'Figure 3.3 Position of a ball on a ramp at equal time intervals', {
    ...flag('unreviewed_figure', 0.5),
    confidence: { engine: 'draft-describer', score: null, flags: ['unreviewed_figure'] },
    figure: {
      caption: 'Figure 3.3 Position of a ball on a ramp at equal time intervals',
      alt: 'A ball shown at five positions along a ramp.',
      description: 'A ramp slopes down from left to right. Five outlines of a ball are drawn along it, spaced further apart towards the bottom.',
      description_origin: 'generated_draft',
    },
  }],
])

const bal = build('bal-gati', 'hi', 52, [
  [0, 'heading', 'बल तथा गति के नियम', { level: 1 }],
  [0, 'paragraph', 'किसी वस्तु को धकेलने या खींचने की क्रिया को बल कहते हैं। बल वस्तु की विराम अवस्था या गति की अवस्था को बदल सकता है। बल का SI मात्रक न्यूटन (N) है।'],
  [0, 'heading', 'संतुलित और असंतुलित बल', { level: 2 }],
  [0, 'paragraph', 'जब किसी वस्तु पर लगने वाले सभी बलों का परिणामी शून्य होता है, तो उन्हें संतुलित बल कहते हैं। संतुलित बल वस्तु की गति की अवस्था नहीं बदलते। असंतुलित बल वस्तु में त्वरण (acceleration) उत्पन्न करते हैं।'],
  [0, 'heading', 'गति का पहला नियम', { level: 2 }],
  [0, 'paragraph', 'प्रत्येक वस्तु अपनी विराम अवस्था या सरल रेखा में एकसमान गति की अवस्था में बनी रहती है, जब तक उस पर कोई असंतुलित बल न लगाया जाए। वस्तु के इस गुण को जड़त्व (inertia) कहते हैं।'],
  [0, 'paragraph', 'बस के अचानक चलने पर यात्री पीछे की ओर झुक जाते हैं, क्योंकि उनका शरीर विराm अवस्था में बने रहना चाहता है।', flag('script_mixing', 0.68)],
  [1, 'heading', 'गति का दूसरा नियम', { level: 2 }],
  [1, 'paragraph', 'किसी वस्तु के संवेग (momentum) में परिवर्तन की दर उस पर लगाए गए असंतुलित बल के समानुपाती होती है। संवेग वस्तु के द्रव्यमान और वेग का गुणनफल है।'],
  [1, 'equation', 'F = ma', {
    mathml: '<math display="block"><mi>F</mi><mo>=</mo><mi>m</mi><mi>a</mi></math>',
    spoken: 'बल बराबर द्रव्यमान गुणा त्वरण।',
    status: 'reviewed',
  }],
  [1, 'table', 'सारणी 4.1 बल, द्रव्यमान और त्वरण', {
    table: {
      caption: 'सारणी 4.1 बल, द्रव्यमान और त्वरण',
      columns: ['द्रव्यमान (kg)', 'त्वरण (m/s²)', 'बल (N)'],
      rows: [['2', '3', '6'], ['5', '2', '10'], ['10', '1.5', '15']],
      numeric: [true, true, true],
    },
  }],
  [2, 'heading', 'गति का तीसरा नियम', { level: 2 }],
  [2, 'paragraph', 'प्रत्येक क्रिया की समान और विपरीत प्रतिक्रिया होती है। क्रिया और प्रतिक्रिया बल सदैव दो अलग-अलग वस्तुओं पर लगते हैं।'],
  [2, 'heading', 'अभ्यास', { level: 2 }],
  [2, 'list_item', '1. जड़त्व किसे कहते हैं?'],
  [2, 'list_item', '2. 4 kg द्रव्यमान की वस्तु पर 12 N का बल लगाया जाता है। त्वरण ज्ञात कीजिए।'],
])

function pack(id: string, title: string, subject: string, languages: Lang[], data: { pages: Page[]; blocks: Block[] }): ChapterPackage {
  const first = data.pages[0].printed_label
  const last = data.pages[data.pages.length - 1].printed_label
  return {
    document: {
      id,
      title,
      subject,
      languages,
      page_count: data.pages.length,
      printed_range: `${first}–${last}`,
      current_revision: 1,
      review_count: 0, // computed by the API from block status
      rights_note: 'Sample chapter written by the Pathya team for development.',
      updated_at: '2026-11-14T10:20:00+05:30',
    },
    revision: 1,
    pages: data.pages,
    blocks: data.blocks,
    audio: [],
    bytes: 0, // computed by the API
  }
}

export const SAMPLE_PACKAGES: ChapterPackage[] = [
  pack('motion', 'Motion in a straight line', 'Physics · Class 9', ['en'], motion),
  pack('bal-gati', 'बल तथा गति के नियम', 'भौतिकी · कक्षा 9', ['hi', 'en'], bal),
  // Role 1's own contract sample, converted, so format changes on their side show up here first.
  fromP1(p1Sample, { subject: 'Role 1 contract sample', rights_note: 'Sample document from the document AI contract (Role 1).' }),
]
