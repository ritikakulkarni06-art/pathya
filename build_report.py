from pathlib import Path
import re, json, html, math
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Flowable
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).parent
OUT=ROOT/'output'/'pdf'; OUT.mkdir(parents=True,exist_ok=True)
TMP=ROOT/'tmp'/'pdfs'; TMP.mkdir(parents=True,exist_ok=True)
for name,file in [('Body','arial.ttf'),('Bold','arialbd.ttf'),('Italic','ariali.ttf'),('Mono','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
NAVY=colors.HexColor('#16354B'); TEAL=colors.HexColor('#087F83'); INK=colors.HexColor('#182B38'); MUTED=colors.HexColor('#536574'); PALE=colors.HexColor('#EDF5F5'); LINE=colors.HexColor('#CCDADC')
styles={
'title':ParagraphStyle('title',fontName='Bold',fontSize=25,leading=29,textColor=NAVY,spaceAfter=13),
'subtitle':ParagraphStyle('subtitle',fontName='Bold',fontSize=14.5,leading=19,textColor=NAVY,spaceAfter=10),
'h':ParagraphStyle('h',fontName='Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=9,spaceAfter=6),
'p':ParagraphStyle('p',fontName='Body',fontSize=10.15,leading=14.2,textColor=INK,spaceAfter=8),
'small':ParagraphStyle('small',fontName='Body',fontSize=8.8,leading=11.6,textColor=MUTED,spaceAfter=7),
'cell':ParagraphStyle('cell',fontName='Body',fontSize=8.65,leading=11.25,textColor=INK),
'th':ParagraphStyle('th',fontName='Bold',fontSize=8.65,leading=11.25,textColor=colors.white),
'ref':ParagraphStyle('ref',fontName='Body',fontSize=9.1,leading=12.5,textColor=INK,spaceAfter=9),
'code':ParagraphStyle('code',fontName='Mono',fontSize=8.6,leading=11.5,textColor=NAVY,spaceAfter=8),
}
refs=[]
def R(title,url,date='n.d. (living documentation)',kind='Official documentation'):
    refs.append(dict(n=len(refs)+1,title=title,url=url,date=date,kind=kind)); return len(refs)
R('W3C. Web Content Accessibility Guidelines (WCAG) 2.2','https://www.w3.org/TR/WCAG22/','12 December 2024','W3C Recommendation')
R('W3C. EPUB Accessibility 1.1','https://www.w3.org/TR/epub-a11y-11/','17 October 2024','W3C Recommendation')
R('W3C. MathML Core','https://www.w3.org/TR/mathml-core/','24 June 2025','Candidate Recommendation Snapshot')
R('DAISY Consortium. DAISY Format','https://daisy.org/activities/standards/daisy/','n.d.; DAISY 3 released 2005')
R('W3C WAI. Stories of Web Users','https://www.w3.org/WAI/people-use-web/user-stories/')
R('Microsoft. Languages and products supported by Immersive Reader','https://support.microsoft.com/en-us/education/learning-accelerators/languages-and-products-supported-by-immersive-reader')
R('Microsoft. Use Immersive Reader and reading mode in Microsoft Edge','https://support.microsoft.com/en-gb/education/learning-accelerators/use-immersive-reader-in-microsoft-edge-1')
R('Microsoft. What is Azure AI Immersive Reader?','https://learn.microsoft.com/en-us/azure/ai-services/immersive-reader/overview')
R('Microsoft. Seeing AI: app description and version history','https://apps.apple.com/us/app/seeing-ai/id999062298','Living listing; document Q&A release notes 2024','Vendor app-store listing')
R('Google. Use Lookout to explore your surroundings','https://support.google.com/accessibility/android/answer/9031274?hl=en')
R('Bookshare. Sign up around the world','https://www.bookshare.org/sign-up-outside-the-us')
R('Bookshare. Who qualifies for Bookshare?','https://www.bookshare.org/help-and-learning-articles/who-qualifies-for-bookshare')
R('Dolphin. EasyReader App','https://yourdolphin.com/EasyReader')
R('Dolphin. About EasyReader Premium and EasyReader Education','https://yourdolphin.com/product-help/easyreader-app/361.htm?lid=1')
R('Dolphin. EasyReader supported file formats','https://yourdolphin.com/support/article?id=49&lid=1')
R('Dolphin. EasyReader Android listing','https://play.google.com/store/apps/details?hl=en-US&id=com.yourdolphin.easyreader','Updated 28 August 2026 in reviewed listing','Vendor app-store listing')
R('Kurzweil Education. Kurzweil 3000','https://www.kurzweiledu.com/products/k3000.html')
R('Kurzweil Education. Frequently asked questions','https://www.kurzweiledu.com/help/frequently-asked-questions.html')
R('Everway / Texthelp Academy. Read&Write for Education how-to articles','https://academy.everway.com/read-and-write-education/howtos/')
R('Speechify. Free and Premium plans','https://speechify.com/pricing/')
R('Speechify. iPhone and iPad application','https://speechify.com/ios/')
R('NaturalReader. Features of Personal Version','https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version')
R('NaturalReader. Working with Text and Audio (Personal Version)','https://help.naturalreaders.com/en/articles/11543218-working-with-text-and-audio-personal-version','11 September 2025')
R('NaturalReader. Plans and pricing (Personal Version)','https://help.naturalreaders.com/en/articles/8854700-plans-pricing-personal-version')
R('EDRLab. Thorium Reader','https://www.edrlab.org/software/thorium-reader/')
R('EDRLab. Thorium Desktop technical specification','https://www.thoriumreader.com/en/legals/desktop/technical-spec/')
R('Google. Gemini Notebook (formerly NotebookLM)','https://workspace.google.com/products/gemini-notebook/')
R('Google. NotebookLM goes global: source passages and citations','https://blog.google/innovation-and-ai/products/notebooklm-goes-global-support-for-websites-slides-fact-check/','6 June 2024','Vendor announcement')
R('Wood, S. G., Moxley, J. H., Tighe, E. L., & Wagner, R. K. Does Use of Text-to-Speech and Related Read-Aloud Tools Improve Reading Comprehension for Students with Reading Disabilities? A Meta-Analysis','https://pmc.ncbi.nlm.nih.gov/articles/PMC5494021/','Online 23 January 2017; journal issue January-February 2018','Peer-reviewed; J. Learning Disabilities 51(1), 73-84')
R('Kuster, S. M., van Weerdenburg, M., Gompel, M., & Bosman, A. M. T. Dyslexie font does not benefit reading in children with or without dyslexia','https://link.springer.com/article/10.1007/s11881-017-0154-6','Online 4 December 2017; volume 68, 2018','Peer-reviewed; Annals of Dyslexia, 25-42')
R('Azzarello, C., Paek, S., Hodge, C., Jameson, M., & Lewis, J. Does font improve reading in dyslexic children?: meta-analysis of dyslexia-friendly fonts and dyslexic children\'s reading performance','https://link.springer.com/article/10.1007/s11881-026-00389-8','31 July 2026','Peer-reviewed; abstract reviewed, full text subscription restricted')
R('Auer, C., et al. Docling Technical Report','https://arxiv.org/abs/2408.09869','19 August 2024; v5, 9 December 2024','Technical report; not treated as independent validation')
R('Ouyang, L., et al. OmniDocBench: Benchmarking Diverse PDF Document Parsing with Comprehensive Annotations','https://openaccess.thecvf.com/content/CVPR2025/html/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.html','CVPR 2025','Peer-reviewed; proceedings metadata and repository reviewed; HTML fetch restricted')
R('OpenDataLab. OmniDocBench repository and evaluation code','https://github.com/opendatalab/OmniDocBench','Living repository','Public code / benchmark documentation')
R('Gao, T., Yen, H., Yu, J., & Chen, D. Enabling Large Language Models to Generate Text with Citations','https://aclanthology.org/2023.emnlp-main.398/','December 2023','Peer-reviewed; EMNLP, 6465-6488')
R('Huh, M., et al. Long-Form Answers to Visual Questions from Blind and Low Vision People','https://arxiv.org/abs/2408.06303','12 August 2024; v2, 25 July 2025','Research paper; arXiv record reports COLM 2024')
R('Hyeon, S., Jung, K., Kim, N.-J., Ryu, H. G., & Do, J. MathReader: Text-to-Speech for Mathematical Documents','https://arxiv.org/abs/2501.07088','13 January 2025; v2, 19 January 2025','Research paper; arXiv record reports ICASSP 2025 acceptance')
R('DAISY. Image Descriptions, Accessible Publishing Knowledge Base','https://kb.daisy.org/publishing/docs/html/images-desc.html')
R('Docling project. Source, features and license','https://github.com/docling-project/docling','Living repository','Public code; MIT code license')
R('Tesseract. Source and language data documentation','https://github.com/tesseract-ocr/tesseract','Living repository','Public code; Apache-2.0')
R('Tesseract. Languages/scripts supported in different versions','https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html')
R('PaddlePaddle. PaddleOCR source and license','https://github.com/PaddlePaddle/PaddleOCR','Living repository','Public code; Apache-2.0 code license')
R('DAISY. MathCAT source and license','https://github.com/daisy/MathCAT','Living repository','Public code; MIT')
R('NV Access. NVDA User Guide','https://api.nvaccess.org/documentation/userGuide.html','Reviewed live guide identifies version 2026.3.1')
R('eSpeak NG. Source, features and license','https://github.com/espeak-ng/espeak-ng','Living repository','Public code; GPL-3.0-or-later core')
R('Mozilla. PDF.js source and license','https://github.com/mozilla/pdf.js','Living repository','Public code; Apache-2.0')
R('jsvine. pdfplumber source and license','https://github.com/jsvine/pdfplumber','Living repository','Public code; MIT')
R('intfloat. multilingual-e5-small model card','https://huggingface.co/intfloat/multilingual-e5-small','Living model card; linked technical report 2024','Model documentation; MIT')
R('Google Cloud. Enterprise Document OCR','https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr')
R('Google Cloud. Gemini layout parser','https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk')
R('Microsoft. Azure Speech languages and voices','https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support')
R('Microsoft. SSML document structure and events','https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/speech-synthesis-markup-structure')
R('FastAPI. Documentation and license','https://fastapi.tiangolo.com/')
R('Deque. axe-core accessibility testing engine','https://www.deque.com/axe/axe-core/')
R('OpenStax. Physics preface and license','https://openstax.org/books/physics/pages/preface','Book published 2020; page is living')
R('OpenStax. Licensing information for textbooks','https://help.openstax.org/s/article/Licensing-information-of-OpenStax-textbooks','Living help page; edition-specific check required')
R('Pratham Books. StoryWeaver open content and licenses','https://storyweaver.org.in/en/open-content')
R('Pratham Books. StoryWeaver attribution guidelines','https://storyweaver.org.in/en/attributions')
R('NCERT. Textbooks and copyright notice','https://ncert.nic.in/textbook.php')
R('Google. Gemini 3.5 Flash-Lite model specification','https://aistudio.google.com/docs/models/gemini-3.5-flash-lite','Latest model update July 2026','Official model documentation; stable endpoint listed')
R('Bookshare. What formats are available for Bookshare books?','https://www.bookshare.org/help-and-learning-articles/what-format-are-bookshare-books-available-in')
R('Everway. Read&Write education pricing and platform entitlements','https://www.everway.com/products/read-and-write-education/pricing/')
R('Microsoft. Seeing AI launches on Android','https://blogs.microsoft.com/accessibility/seeing-ai-app-launches-on-android-including-new-and-updated-features-and-new-languages/','4 December 2023','Vendor announcement')

pages=[]; current=None
def page(part,title):
    global current
    current={'part':part,'title':title,'items':[]};pages.append(current)
def p(s):current['items'].append(('p',s))
def h(s):current['items'].append(('h',s))
def small(s):current['items'].append(('small',s))
def box(s):current['items'].append(('box',s))
def table(headers,rows,widths):current['items'].append(('table',(headers,rows,widths)))
def code(s):current['items'].append(('code',s))
def diagram(kind):current['items'].append(('diagram',kind))

P1='PART 1 - PROBLEM, EXISTING SOLUTIONS, AND VERIFIED GAPS'
P2='PART 2 - PROPOSED SOLUTION, DIFFERENTIATION, AND FEASIBILITY'
P3='PART 3 - TECH STACK, ARCHITECTURE, AND BUILD PLAN'

page(P1,'Pathya: a repairable AI textbook reader')
small('IMPLEMENTATION-READY PROJECT REPORT | Research cut-off and access date: 16 November 2026')
h('Executive summary')
p('Build <b>Pathya</b> (working name; availability not checked): an accessible web reader that turns a limited set of English and Hindi textbook chapters into navigable, page-linked content. Its core contribution is a trustworthy study workflow: uncertain extraction can be inspected and corrected, and those corrections update narration, search and evidence used by the optional assistant.')
p('A basic OCR + text-to-speech (TTS) reader is a useful baseline but a weak project differentiator. Immersive Reader, Kurzweil 3000, EasyReader, Speechify and NaturalReader already cover substantial reading support; Seeing AI already offers document questions. Source-linked answers also exist in Google\'s NotebookLM / Gemini Notebook documentation. The opportunity is a focused integration with measurable reliability, not a claim that these components are new. [6-9,13-24,27-28]')
box('<b>Recommended flagships:</b> (1) one structured, page-linked reading model; (2) confidence-aware review with revision-safe corrections; (3) evidence-linked study assistance that abstains when the chapter or its extraction cannot support an answer. Offline chapter reading and user-controlled accessibility settings are essential requirements.')
h('Planning assumptions, not established facts')
table(['Resource','Planning assumption'],[
['Team and time','3 students, 14 weeks; approximately 12 focused hours per person per week (504 person-hours). Weeks 15-16 are contingency.'],
['Equipment','An existing 4-core laptop with 16 GB RAM and 20 GB free space; an Android phone with 4 GB RAM; no dedicated GPU purchase.'],
['Content and users','School / early college science prose, simple tables and a few teacher-verified equations. English and Hindi first; adults for initial user sessions.'],
['Budget','INR 7,000 base cash envelope; up to INR 14,000 with participant and cloud contingencies. Borrowed hardware and student labor excluded.']],[0.23,0.77])
h('How to read this report')
p('Part 1 (pp. 1-8) establishes needs, compares 12 solution categories/systems and evaluates evidence. Part 2 (pp. 9-12) defines the product, ranking and evaluation. Part 3 (pp. 13-25) specifies implementation, delivery gates and a numbered bibliography. All numbered citations link to the bibliography; bibliography titles link to original sources.')
small('Evidence labels: V = capability documented by its provider or standard, not independently tested here. R = research result, bounded by its study. I = inference from reviewed evidence. P = proposed implementation. T = proposed target. No software prototype or user study was carried out for this report.')

page(P1,'A. Different needs, different study journeys')
p('The following are design scenarios, not observations from recruited participants. WAI user stories illustrate why disability labels alone cannot determine an interface. People may have overlapping needs, different screen-reader skills and different preferred languages. Ask about tasks and preferences; do not require a diagnosis to select reader settings. [5]')
table(['Student / task','Barrier in an ordinary workflow','Required response and limit'],[
['Blind student: locate an exercise and compare two definitions','An image PDF has no usable text. A flat OCR transcript loses headings, columns, footnotes and the printed page cited by a teacher.','Heading / page / exercise navigation, stable source links, keyboard controls and screen-reader semantics. Audio alone cannot convey a whole page efficiently.'],
['Low-vision student: examine a graph and continue reading','Zooming a fixed page causes repeated panning. Small labels, glare and weak contrast make crops difficult to inspect.','Reflow prose separately from a zoomable source; allow contrast, size and spacing changes, with a clear return point. Preserve magnification and focus.'],
['Student with dyslexia: read, revisit a term and explain a concept','Decoding effort and losing one\'s place can slow study. Audio may help some tasks; long narration can also overload attention.','Optional sentence highlighting, short playback units, adjustable pace, bookmarks and concise source-linked explanation. Preferences are not treatment.']],[0.23,0.35,0.42])
h('Where textbook structure creates failure')
p('Poor photographs introduce blur, shadows, skew and clipped lines. Scanned PDFs lack semantic order; even a selectable PDF may have a faulty text layer. Two-column prose, captions and sidebars can interleave. Tables lose header-to-cell relationships when flattened. Equations can lose a minus sign, fraction boundary or exponent while the surrounding paragraph remains fluent. Diagram meaning includes relationships, not just object names. These are engineering risks to test, rather than measured prevalence claims. Document-parsing benchmarks explicitly separate text, tables, formulae and reading order. [33-34]')
p('Multilingual chapters add script changes, English technical terms, abbreviations and numerals. Hindi OCR availability does not guarantee accurate conjuncts, correct language segmentation or intelligible narration. A translated explanation is not the original textbook. Keep source text, pronunciation hints and generated material in separate fields. [6,41,51]')
h('Access is necessary; comprehension is a separate outcome')
p('A student may successfully hear a paragraph yet fail to compare quantities or explain the principle. Test both access tasks (find, read, return, correct) and learning tasks (explain, infer, retrieve supporting evidence). A proposed journey is: import at college Wi-Fi, review flagged content with a teacher, download a chapter, study on the bus, and resume later. If the page is unreadable, request a better capture or authorized accessible edition instead of presenting guessed text as truth.')

page(P1,'B. Comparison matrix 1: users and ingestion')
small('Reviewed scope: 12 rows across four linked matrices (pp. 3-6). NV means not verified in reviewed sources, never proof of absence. Vendor documentation establishes advertised capability, not independent accuracy. Versions, platforms and subscriptions must be recorded during baseline testing.')
table(['System / evidence','Intended users and platforms','Inputs','OCR / reading order'],[
['Immersive Reader [6-8]','Learning differences / language learners; Microsoft host apps; Azure SDK integration.','Host-provided text; Edge web reading and PDF Read Aloud are distinct contexts.','Azure reader receives content; it is not a complete textbook OCR pipeline. Order depends on host/input.'],
['Seeing AI [9,63]','Blind / low vision; iOS and Android.','Camera documents, photos; multi-page scanning in release history.','Alignment guidance; recognizes document text and formatting (vendor claim). Complex textbook order NV.'],
['Google Lookout [10]','Blind / low vision; Android 6+.','Camera; Documents mode for full pages; image modes.','Audio capture hints; text recognition. Multi-column order accuracy NV.'],
['Bookshare [11-12,61]','People with qualifying print disabilities; compatible reading apps.','Library titles in formats such as DAISY, EPUB, BRF, Word and audio; title-dependent.','Structure depends on supplied edition and reader; extraction quality NV here.'],
['DAISY readers [4]','Print-disabled readers; software and dedicated devices.','DAISY talking books: combinations of audio, text and images.','Format encodes navigation/synchronization; cannot repair an arbitrary scan by itself.'],
['Dolphin EasyReader [13-16]','Print disabilities; Android, iOS and Windows reviewed.','DAISY, EPUB, DOCX, HTML, text; PDF documentation differs by source/version.','PDF listed in current app listing; older help restricts PDF to RNIB Bookshare. General OCR and order behavior NV.'],
['Kurzweil 3000 [17-18]','Learning / literacy support; installed clients and web.','Scanned material, digital documents, web reading.','ABBYY OCR documented; vendor accuracy superlative is not adopted here.'],
['Read&Write [19,62]','Windows, Mac, Chrome, Edge, iOS, Android; features vary.','Web / Google Docs; PDF and inaccessible image text via screenshot reader.','Screenshot Reader documented. Full textbook layout fidelity NV.'],
['Speechify [20-21]','General / education listening; web, mobile and desktop offerings.','PDFs, documents, web and Scan & Listen.','OCR scanning advertised. Complex textbook order accuracy NV.'],
['NaturalReader [22-24]','Personal / education reading; web and mobile.','Documents, scans and images; paid OCR.','OCR and PDF filtering advertised; filter is not verified structural repair.'],
['Thorium Reader [25-26]','Accessible desktop reading; Windows, macOS, Linux.','EPUB, PDF, DAISY, audiobooks and other publishing formats.','Reads existing publications; arbitrary-scan OCR NV.'],
['NotebookLM / Gemini Notebook [27-28]','Source-based research / study; Google web service.','Uploaded PDFs, text, Docs, Slides and other sources.','Document ingestion documented; faithful textbook order and correction controls NV.']],[0.21,0.25,0.25,0.29])
small('Naming note: Google\'s reviewed Workspace page uses “Gemini Notebook (formerly NotebookLM)”; other official pages retain NotebookLM. Recheck the deployed name and account entitlements when running comparisons. [27-28]')

page(P1,'B. Comparison matrix 2: reading and accessibility')
small('“Designed for” or “supports assistive technology” is a documented intent/capability, not a passed accessibility audit. NV below identifies the exact unverified area. This review did not install or test these products.')
table(['System','TTS / synchronized highlighting','Dyslexia-related controls','Screen reader / keyboard'],[
['Immersive Reader [6-8]','Read Aloud; availability varies by language and host.','Line focus, spacing, themes, syllables and picture dictionary; language-dependent.','Full host-by-host screen-reader / keyboard conformance NV.'],
['Seeing AI [9]','Spoken document reading; highlight synchronization details NV.','Dedicated dyslexia customization NV.','Blind-user design and audio capture cues documented; keyboard coverage NV.'],
['Lookout [10]','Spoken text; rate / pitch and voice settings. Word highlighting NV.','Dedicated typography / focus controls NV.','Blind-user design; document hints and haptics. Full keyboard coverage NV.'],
['Bookshare [11-12]','Accessible reading available through reader ecosystem; highlighting reader-dependent.','Reader-dependent; do not attribute every reader feature to the library.','Compatible reader and accessible edition determine experience; exact combination NV.'],
['DAISY readers [4]','Text/audio synchronization supported by format; implementation varies.','Multi-sensory reading possible; display preferences depend on reader.','Navigable format; reader-specific commands / conformance NV.'],
['EasyReader [13,16]','Text/audio sync and word/sentence highlighting advertised.','Fonts, color, letter/line spacing and visible lines; pronunciation controls.','Linear screen-reader and braille mode advertised. Keyboard audit NV.'],
['Kurzweil 3000 [17]','Words and sentences highlighted during TTS.','Rate, colors, zoom and OpenDyslexic; desktop magnification.','Independent screen-reader interoperability and complete keyboard audit NV.'],
['Read&Write [19]','Read Aloud and Audio Maker documented; exact sync behavior by edition NV.','Masking, text formatting, dictionaries and reading support.','Full toolbar / PDF reader keyboard and screen-reader audit NV.'],
['Speechify [20-21]','TTS and playback options; highlighting advertised in product materials.','Exact typography / focus controls on each current platform NV.','Complete screen-reader / keyboard conformance NV.'],
['NaturalReader [22]','TTS and highlighting; feature limits depend on plan.','Font/spacing options for typed text; dyslexia font optional.','Full screen-reader / keyboard conformance NV.'],
['Thorium [25-26]','TTS; publication-dependent audio support. Exact word sync NV in reviewed spec.','Accessibility-oriented display customization; exact settings depend on version.','Assistive-technology access documented; task-level audit still needed.'],
['Notebook / NotebookLM [27-28]','Generated audio / study features overlap conceptually; exact word sync NV.','Dedicated dyslexia reading controls NV.','Full keyboard and screen-reader task coverage NV.']],[0.19,0.28,0.29,0.24])
h('Fair interpretation')
p('Customization is already common. A new font, a dark theme or a speed slider should be treated as baseline product quality. Missing documentation creates a research question for hands-on testing. It does not justify calling an established product inaccessible. For any adopted baseline, record the exact browser, operating system, voice, app version and subscription, then test the same chapter and tasks.')

page(P1,'B. Comparison matrix 3: STEM and AI study support')
small('Math = mathematical content. A supported file format is not evidence of correct conversion from a photographed equation. An AI summary is not evidence that every statement is grounded.')
table(['System','Math, tables and diagrams','AI explanations / grounded Q&A','Documented boundary / uncertainty'],[
['Immersive Reader [6,8]','Equation Read Aloud appears in host/language matrix. Table and diagram exploration NV.','Translation / picture dictionary documented. Textbook-grounded generative Q&A within reader NV.','Features differ across host and language; do not generalize one host to all.'],
['Seeing AI [9]','Rich image descriptions documented. Structural equation / table navigation NV.','Document questions already documented. Citation fidelity NV.','App description is vendor evidence, not a textbook STEM benchmark.'],
['Lookout [10]','Image information available; structured STEM traversal NV.','Textbook evidence-linked study answers NV.','Explore mode explicitly beta and less accurate than other modes.'],
['Bookshare [11-12]','Accessible edition and downstream reader determine STEM access; exact title NV.','Library-level source-grounded generative Q&A NV.','Qualifying disability / membership; availability of a required edition not established.'],
['DAISY [4]','MathML extension exists; figures and text can coexist. Table traversal reader-dependent.','Format supplies no generative answer engine.','Structure must first be authored correctly. Navigation is established prior art.'],
['EasyReader [13-16]','MathML listed; premium image descriptions advertised. Scanned equation repair NV.','Premium AI study tools documented; exact passage citation / correction propagation NV.','Do not confuse AI help search with textbook Q&A. PDF support documentation conflicts.'],
['Kurzweil 3000 [17]','OCR plus notes / study tools; verified math-tree / diagram traversal NV.','Dictionaries / study guides documented; generative chapter Q&A NV.','Vendor “highest accuracy” OCR claim not independently evaluated here.'],
['Read&Write [19]','Screenshot reading; semantic STEM reconstruction NV.','Simplify AI documented; textbook-grounded Q&A / citations NV.','Features and platform coverage differ; simplification can change meaning.'],
['Speechify [20-21]','Structured STEM exploration NV.','Voice AI assistant can discuss books / sites (vendor). Citation correctness NV.','AI chat is existing capability; local offline generation not established.'],
['NaturalReader [22-24]','Smart Filter can skip tables/charts; semantic narration of their structure NV.','Subscriber Ask AI documented. Fine-grained evidence correctness NV.','Skipping a chart is not making its information accessible.'],
['Thorium [25-26]','Accessible publication reading; exact STEM interaction on test build NV.','Textbook-grounded generative Q&A NV.','Quality depends on authored EPUB / DAISY content.'],
['Notebook / NotebookLM [27-28]','Multisource study tools; accessible math-tree navigation NV.','Source-based answers with passage citations documented.','Citation interface establishes overlap, not independent truth or learning benefit.']],[0.18,0.28,0.29,0.25])
h('Additional technical prior art')
p('Docling\'s structured parsing, MathCAT\'s speech/navigation and MathReader\'s OCR-to-math speech are substantial prior art and reusable foundations. They are not the complete proposed workflow. [37,39,43-44]')

page(P1,'B. Comparison matrix 4: language, offline and access')
small('No price is inferred from an old blog or a US plan. Except where explicitly stated, exact India checkout price / tax / entitlement is NV. “Offline audio” and “all processing offline” are different capabilities.')
table(['System','Language support relevant to India','Offline boundary','Verified access / pricing boundary'],[
['Immersive Reader [6-8]','Language/host feature matrix includes Indian languages; parity is not universal.','Host, voice and feature dependent; full offline pipeline NV.','Bundled host availability vs metered Azure integration differ. Current India cost NV.'],
['Seeing AI [9]','Multilingual listing; target Hindi technical narration quality NV.','Feature-by-feature offline operation NV in reviewed listing.','Free app listing; data / connectivity still matter.'],
['Lookout [10]','English, Hindi, Bengali, Gujarati, Kannada, Marathi, Tamil, Telugu among listed languages.','Food-label download explicitly supports offline recognition; not evidence all modes do.','Android app; exact service limits / India feature availability NV.'],
['Bookshare [11-12]','Title and reader dependent; required bilingual textbook catalog coverage NV.','Downloaded reading depends on chosen compatible app and format.','Reviewed international signup explicitly lists free individual membership in India; proof of eligibility required.'],
['DAISY readers [4]','Content and voice dependent; DAISY is a format, not a language model.','Local talking books can be packaged; player-specific limits NV.','Standard is public; players and library access have separate terms.'],
['EasyReader [13-16]','Voices and library content determine narration; Hindi quality NV.','Downloaded reading supported in reader workflow; exact premium / voice behavior NV here.','Free app with premium subscriptions and limited imports; exact current India price NV.'],
['Kurzweil 3000 [17-18]','13 TTS languages advertised; passage translation into 70+ languages. Hindi TTS NV.','FAQ: website cannot work offline; installed Web License client can.','Commercial licensing; institutional access possible; India quote NV.'],
['Read&Write [19,62]','Translator and language/settings profiles documented; Hindi voice NV.','Online voices distinct; full offline feature matrix NV.','USD 184/year individual listed; higher education quote. India checkout/tax NV.'],
['Speechify [20-21]','Multiple voices/languages advertised; code-switched pronunciation quality NV.','Premium downloadable audio advertised; offline OCR/chat NV.','Free and Premium tiers verified; exact India checkout and usage caps require recheck.'],
['NaturalReader [22-24]','Voice-dependent multilingual support; exact Hindi model/quality NV.','Paid MP3 export for offline listening. Offline AI / OCR NV.','OCR and Ask AI paid. Personal-plan audio restricted to personal use.'],
['Thorium [25-26]','Localized interface; content / OS voices govern narration.','Desktop reader works offline; catalogs need network.','Free/open source; protected content has separate access rules.'],
['Notebook / NotebookLM [27-28]','Exact Hindi functionality and parity across accounts NV.','Full source-grounded assistant offline NV.','Google account / edition entitlements; current India limits / price NV.']],[0.18,0.28,0.27,0.27])
p('Comparison conclusion (I): a defensible student project must show a better bounded workflow on its evaluation chapters, rather than a longer checklist. None of these documentation-only comparisons establishes that Pathya would outperform a product, or that a particular commercial feature is absent. A synchronized correction-to-audio-to-retrieval workflow for the proposed low-cost bilingual scope was <b>not found in the reviewed sources</b>; this is not evidence that no implementation exists.')

page(P1,'C. What research and standards support')
table(['Evidence and status','Supported conclusion','Boundary and project consequence'],[
['Read-aloud meta-analysis [29] (R)','Wood et al. report a positive average comprehension effect (d = 0.35; 95% CI 0.14-0.56).','Study designs and learners vary. This does not predict a gain for this app, Hindi content or each student; measure comprehension separately.'],
['Specialized fonts [30-31] (R)','Kuster et al. found no speed/accuracy advantage for Dyslexie. A 2026 meta-analysis abstract reports no consistent reliable benefit.','The 2026 full text was not available. Offer preferences; do not claim fonts, color overlays or AI cure / treat dyslexia.'],
['Document parsing [32-34,39]','Docling provides reusable structured parsing; OmniDocBench evaluates diverse documents and components.','Developer reports / benchmark scores are not a local textbook result. Pin versions and measure language, layout and degradation strata.'],
['Accessible STEM [3,37,43-44]','MathML carries structure; MathCAT enables speech/navigation. MathReader reports improved math speech WER on its test.','Math OCR errors can remain mathematically fatal. No reported WER here is transferred to Pathya or Hindi.'],
['Grounded answers [35] (R)','ALCE evaluates answer and citation quality separately; generated citations can remain incomplete.','A real citation can still fail to support a claim. Check evidence entailment; add unanswerable questions and abstention.'],
['Multimodal access [36,38]','VizWiz-LF finds plausible generated answers can contain incorrect visual details. DAISY recommends context-appropriate image descriptions.','Not a textbook diagram efficacy study. Do not publish unreviewed inferred relations as source facts.']],[0.24,0.36,0.40])
h('Standards translated into implementation requirements')
p('<b>WCAG 2.2:</b> target AA for the web app; implement semantic structure, meaningful reading order, keyboard operation, visible/unobscured focus, contrast, reflow, language markup and accessible authentication. Avoid drag-only correction. Test target sizing and redundant data entry as applicable. Automated scans alone cannot establish conformance. [1]')
p('<b>EPUB Accessibility 1.1:</b> use its distinction between content accessibility and discoverability metadata when designing exports; do not label an export conformant without checking the complete requirements. <b>DAISY:</b> navigable, synchronized reading is established practice. <b>MathML Core:</b> reviewed snapshot is a Candidate Recommendation, not a final Recommendation; rendering does not certify speech correctness. [2-4]')
p('<b>Image guidance:</b> provide a concise alternative plus a linked longer description when needed. State diagram type, key labels and relationships in the textbook\'s context. A description should not add invisible facts. In Pathya, descriptions are teacher-authored or explicitly labeled generated drafts until reviewed. [38]')

page(P1,'D. Seven opportunities, with bounded claims')
table(['Opportunity / category','Evidence and gap interpretation','Student-team decision'],[
['1. One source-linked content model (engineering)','DAISY synchronization and Docling\'s representation already exist [4,39]. Linking corrections, audio and Q&A at paragraph revisions is an integration opportunity.','MVP foundation. Stable IDs and page geometry are more useful than a custom graph database.'],
['2. Uncertainty-aware repair (underserved workflow)','Vendor OCR and reading are common [9-10,17,22]; standardized textbook error triage and derivative invalidation were not found in reviewed product docs.','Flag low-quality extraction; supply accessible review queue. Need a held-out flagging experiment.'],
['3. Evidence return path (engineering)','Passage citations already exist [28]; ALCE shows citation quality needs evaluation [35].','Jump from answer to source paragraph, then return to answer. Suppress stale evidence after edits.'],
['4. Offline study continuity (underserved workflow)','Several products support downloaded audio or local reading [18,21,23,26]; offline processing and AI are different.','Cache verified chapter content/audio and position. New imports and cloud explanations may wait.'],
['5. Choice without diagnosis (common + engineering)','Reading customization is well established [6,13,17,22]. WAI stories show differing interaction needs [5].','Provide independent controls and presets, then preserve individual changes. Do not market presets as treatment.'],
['6. English-Hindi technical pronunciation (hypothesis)','OCR models and hosted voices list Hindi [41,51]. End-to-end code-switching quality is not established by a language list.','Small, editable term glossary; bilingual listener test. No automatic textbook translation in MVP.'],
['7. Structure-aware STEM access (future research)','MathML, MathCAT and math speech research are substantial prior art [3,37,43]. Diagram hallucination risk is documented [36].','MVP renders reviewed MathML and simple header tables. Automatic equation parsing / diagram relation exploration is stretch.']],[0.26,0.43,0.31])
h('Search scope and evidence discipline')
p('The review searched official Microsoft, Google, Bookshare, Dolphin, Kurzweil, Everway/Texthelp, Speechify, NaturalReader and EDRLab documentation; W3C and DAISY standards/guidance; ACL, CVPR, journal publisher, PubMed/PMC and arXiv records; and named public repositories. Searches included OCR, reading order, offline, language support, document Q&A, citation evaluation, dyslexia fonts and accessible mathematics. Access date is 16 November 2026. This is a targeted desktop review, not a systematic review or a hands-on product audit.')
p('The comparison supports choosing a narrow reliability problem. It cannot support “world first,” exhaustive catalog coverage, comparative accessibility rankings or clinical effects. Pages with inconsistent documentation (notably EasyReader PDF input) are recorded as uncertainty. Exact commercial India prices are intentionally left unverified where the reviewed material did not establish a reliable checkout amount.')
h('What can be demonstrated credibly')
p('Show the same extraction error before and after a correction, prove that stale audio and answers are no longer served, and repeat a study task without internet. This makes the technical contribution inspectable. The hypothesis is that these mechanisms reduce silent errors and recovery effort; only the planned evaluation can establish whether students find the combination useful.')

page(P2,'A. The product: study a chapter, trust its provenance')
p('<b>Value proposition (P):</b> Pathya helps students navigate an authorized chapter, hear or inspect its content in their preferred way, notice extraction problems and return from explanations to the exact supporting passage. It should remain useful when its assistant is unavailable. The name is a working label, not a trademark claim.')
h('Users and core use cases')
p('<b>Primary:</b> students who use screen readers or magnification, and students who choose TTS / visual reading supports, studying English or Hindi science prose. Keep blindness, low vision and dyslexia as separate evaluation strata. <b>Secondary:</b> teachers or authorized helpers who review extraction and pronunciation. The initial pilot uses consenting adult students; work with minors requires a separate institutional process.')
p('Core tasks are: import; navigate by heading/page/paragraph; read, bookmark and correct; download; and request evidence-linked explanation. Independent controls cover size/spacing, colors, focus, voice, rate and uncertainty interruptions. Preserve preferences without requiring diagnosis. A helper sees authorized blocks, not the student\'s entire reading history.')
h('A realistic complete journey')
p('A blind student receives a 12-page authorized physics chapter. At college Wi-Fi, they upload it and hear progress messages. Pathya detects two columns and flags a suspicious minus sign. The student can skip to the review queue, listen to the uncertain text, inspect its provenance or ask an authorized helper to review the crop. The helper corrects it using a labeled text form, not drag-and-drop.')
p('After publication of revision 2, the student downloads the chapter, audio and text. On a phone offline, “Go to printed page 38” opens the right section. Table navigation announces the column header with each value. A bookmark saves the paragraph rather than a pixel offset. The assistant is visibly unavailable offline; search and reading continue. After reconnection, an explanation of acceleration cites a specific paragraph, with a link to open and read the evidence.')
p('A low-vision student uses the same content in reflow with adjustable size and an independently zoomable original page. A student with dyslexia chooses short narration segments and sentence focus, turns highlighting off if distracting, and checks an explanation against the original. No preset silently rewrites textbook sentences.')
h('Deliberate scope boundaries')
box('<b>Outside MVP:</b> arbitrary handwriting; handwriting-to-math; general diagram reasoning; chemistry structures; universal table reconstruction; all Indian languages; full DAISY/EPUB import/export certification; diagnosis or treatment; autonomous tutoring; exam proctoring; Braille production; and large-model training. Camera input is a file/capture control with basic quality feedback, not a guaranteed independent capture guide.')
p('A failed parse must still leave a usable status page, a source-download option if authorized and an explicit way to request review. It must not imply that an inaccessible source image has become accessible merely because an upload succeeded.')

page(P2,'B-C. Feature ranking and scope selection')
p('The scoring below is a <b>planning judgment</b>, not empirical evidence. Scores run 1-5; larger is better. U = user value (30%); F = feasibility in 14 weeks (25%); D = defensible differentiation despite overlap (15%); R = lower technical risk (15%); C = lower recurring cost (15%). Total = 0.30U + 0.25F + 0.15D + 0.15R + 0.15C. Value and feasibility dominate.')
table(['Candidate','U','F','D','R','C','Total / decision'],[
['Independent reader controls',5,5,1,5,5,'4.40 - mandatory baseline'],
['Shared page-linked representation',5,4,3,4,5,'4.30 - flagship 1'],
['Offline prepared-chapter reading',5,4,2,4,5,'4.15 - mandatory baseline'],
['Confidence + corrections',5,3,4,3,5,'4.05 - flagship 2'],
['Simple structured-table narration',4,4,2,4,5,'3.85 - bounded MVP'],
['English-Hindi term glossary',4,4,2,3,4,'3.55 - bounded MVP'],
['Source-linked / abstaining answers',4,4,2,3,3,'3.40 - flagship 3'],
['Equation structure navigation',5,2,2,2,4,'3.20 - reviewed MathML only'],
['Automatic diagram exploration',5,1,3,1,2,'2.65 - stretch / research'],
['Automatic multilingual translation',3,2,1,2,2,'2.15 - future research']],[0.43,0.06,0.06,0.06,0.06,0.06,0.27])
p('Ranking is not the only decision rule. Accessibility controls outrank “differentiators” but are expected functionality. Table narration scores well but depends on verified headers. Evidence-linked answers score lower; retain them as the third flagship because they directly test the study-to-source return path. If time fails, ship passage retrieval first and cut generative responses, preserving the other two flagships.')
h('MVP, stretch and future work')
p('<b>MVP:</b> a chapter-scoped accessible reader; PDF/photo ingestion on the laptop; page/heading/paragraph IDs; basic quality signals; correction history and invalidation; English-Hindi segmentation with manual overrides; sentence-level audio; simple tables; reviewed equations/figure descriptions; offline chapter package; and optional online evidence-linked explanation. “Reviewed” is a workflow status, not a guarantee of correctness.')
p('<b>Stretch, only after acceptance gates:</b> word-level timing; an additional tested Indian language; automatic equation candidates reviewed before use; simple labeled diagram relationships; structured HTML export; and more robust camera guidance. <b>Future research:</b> calibrated semantic uncertainty, automatic accessible STEM conversion, learning gains over a semester and robust translation of technical educational content.')
h('Hardest assumption: can unreliable extraction be caught affordably?')
p('In weeks 1-2, annotate 24 development pages (12 English, 12 Hindi), including columns, shadows and symbols. Compare Tesseract-only extraction with Docling plus Tesseract. Plot important-error recall against reviewer effort; count minutes spent reviewing each page. If errors remain silent or repair takes over 3 minutes/page on ordinary pages, narrow ingestion to cleaner PDFs and teacher-prepared chapters. Do not add a chatbot to hide a failed extraction pipeline.')

page(P2,'C. Flagship contracts and accessibility behavior')
table(['Flagship','Concrete behavior to implement','Acceptance gate (T)'],[
['1. One structured source','Every read unit, search result and answer citation resolves to document, physical PDF page, printed label, block ID and revision. The source crop is an optional visual supplement.','A 50-link fixture set opens the intended block; keyboard / screen-reader users receive the block text and can return without losing context.'],
['2. Uncertainty and repair','Show “needs review” with reasons, not a fake probability. Store raw OCR, correction, reviewer, revision and provenance. Editing text/order invalidates affected outputs.','Seeded minus-sign, missing-line and wrong-order faults enter review. After correction, old audio, index chunks and answers are never served as current.'],
['3. Evidence-first assistance','Return original supporting passages before or alongside generated explanation. Each factual claim links to allowed block revisions. Answering can be refused.','Reject nonexistent, cross-book and stale citations. Test answerable, missing-evidence, misleading-premise and damaged-extraction queries separately.']],[0.22,0.46,0.32])
h('Confidence-aware is not “the model is certain”')
p('OCR confidence is an engine-specific score, often absent for native text or generative parsing. Keep it separate from layout heuristics, language checks and human review. An initially transparent rule could flag a block if OCR confidence is low, scripts are implausible for the selected language, text overlaps a figure, symbols disagree across two passes or its order violates detected columns. These flags need development-set tuning; they are not calibrated correctness probabilities.')
p('Do not interrupt every sentence. Provide a review summary, an accessible review queue and a user setting to pause on unresolved critical symbols. Use a short status announcement plus the reason: “Equation 2: denominator needs review.” A student may continue, but the assistant should not use unresolved critical content as reliable evidence. Users can override a language label without re-uploading the whole book.')
h('Controls remain independent')
p('Offer start presets such as “screen-reader navigation,” “magnified reading” and “read and listen,” then independent controls for font/size/spacing, colors, line focus, voice, rate, unit length and uncertainty interruptions. Include a reset and preview. For screen-reader use, do not force application TTS; native screen-reader speech and the app narrator should not speak simultaneously.')
p('Use native headings, buttons, links, lists and tables. Preserve tab order when the source pane opens; put focus at the cited block and offer “Return to explanation.” Provide correction fields for text, language, reading-order position, table headers and pronunciation. A visual crop alone cannot verify an OCR correction for a blind student; allow a helper to supply a reviewed description and retain the unverified status where necessary.')
h('What makes the live evaluation impressive')
p('An examiner should see a source-linked answer invalidated after its supporting sentence changes, then regenerated against the new revision; a table read with its headers; and an offline restart that restores the last paragraph. These are observable integration results. Label pre-corrected content and seeded faults openly. Demo success cannot establish general accuracy, user benefit or novelty.')

page(P2,'D. Evaluation: extraction and grounded answers')
p('Use a frozen evaluation manifest and the same source bytes across systems. Split by source chapter, not by adjacent page: 24 development pages and 48 held-out pages, with degradation variants kept in the same split as their clean originals. Report clean native PDF, clean scan and phone-photo results separately, also by English/Hindi. Proposed thresholds below are feasibility gates, not achieved results.')
table(['Measure / annotation','Method','Proposed target (T)'],[
['OCR CER and WER','CER = (substitutions + deletions + insertions) / reference characters; WER uses words. Fix Unicode normalization and tokenization; retain meaningful symbols. Report micro-average and per-page median/tail.','Clean prose: CER <=3% English, <=5% Hindi; degraded pages reported separately, no implied pass.'],
['Reading order / coverage','Two reviewers mark blocks and ordered relations. Pairwise order accuracy = correct comparable block pairs / annotated pairs. Also measure omitted blocks and header/footer intrusion.','>=95% pairwise order on clean pages; >=98% prose block coverage.'],
['Flagging and review burden','Label meaning-changing errors (negation, units, missing lines, symbol errors). Report recall, precision, flagged blocks/page and correction minutes/page.','>=90% critical-error recall with <=25% of prose blocks flagged on development gate; validate again held-out.'],
['Equations (separate set)','20 reviewed expressions: exact normalized structure match, symbol errors, and spoken structure judged by a knowledgeable reviewer. Track coverage and unsupported cases.','No unreviewed auto-extracted equation served as trusted; >=90% correct speech on supported reviewed set.'],
['Tables (separate set)','12 simple tables: cell text accuracy, header association accuracy, row/column completeness and answer-to-cell navigation tasks.','>=95% header association on supported simple tables; merged headers explicitly unsupported unless reviewed.'],
['Figures (separate set)','12 figures: two reviewers score label correctness, relations, omissions and invented facts against the page. Student utility scored separately.','Zero invented factual relations in descriptions published as reviewed; report draft errors separately.'],
['Grounded Q&A: 60 questions','30 supported; 10 absent; 10 misleading premises; 10 from ambiguous/damaged content. Score claim-level correctness and support, citation resolution/entailment and false confident answers.','>=95% citation resolution; >=90% supported factual claims; <=5% unsupported factual claims.'],
['Abstention / retrieval','Report correct abstentions on 30 unsafe/unsupported questions and unnecessary abstentions on supported ones. Recall@5 uses manually linked evidence blocks.','>=90% appropriate abstention; <=20% unnecessary abstention; evidence Recall@5 >=90%.']],[0.23,0.48,0.29])
small('Targets may conflict: raising abstention can increase refusal of answerable questions. Publish coverage versus risk and raw denominators, not just one “accuracy.” Raters should see source crops and reference text, be blind to condition where possible and adjudicate disagreements. An LLM judge may assist triage but is not the sole ground-truth authority. [34-36]')

page(P2,'D. Evaluation: people, ablations and device costs')
h('Baselines and ablations')
p('<b>B0:</b> Tesseract + flat text + sentence TTS, with the same voice and device. <b>B1:</b> full structured reader. <b>B2:</b> B1 without uncertainty cues/review support. <b>B3:</b> evidence retrieval with source links versus generated evidence-linked explanation. Use the same extraction when testing interface ablations, and the same interface when testing parsers. Compare a suitable installed EasyReader/Thorium edition on prepared accessible content and Seeing AI/Lookout on capture tasks where access permits. Record content preparation time; do not compare an already accessible edition against an unprocessed scan without disclosure.')
h('A feasible formative study, not a clinical trial')
p('Aim for 6-9 consenting adult intended users: approximately 2-3 blind, 2-3 low vision and 2-3 with dyslexia, recruited with an accessibility office if feasible. Sample size is a planning assumption. Reimburse time/transport, provide accessible information sheets, allow withdrawal and avoid requiring disclosure beyond what is necessary. Obtain institutional review requirements before recruitment. Use no simulated disability as a substitute for intended-user feedback.')
p('Run 45-60 minute sessions with training and breaks. Counterbalance two equivalent chapter task sets to reduce learning effects. Tasks: locate an exercise; return from a citation; read a table value; notice a seeded uncertain symbol; resume offline; explain a concept and select its supporting passage. Record completion, help required, navigation errors, recoveries, time and comprehension rubric scores. Ask about trust, fatigue and preferences. Report individual and group-stratified observations; small cells do not establish population effects.')
table(['Acceptance area','Proposed target / test configuration (T)'],[
['Accessible task success','At least 80% independent completion of core find/read/return tasks across sessions; report each group and all assistance. No unresolved keyboard trap or inaccessible critical control.'],
['Manual / automated coverage','NVDA + Firefox/Chrome on Windows; TalkBack + Chrome on Android. Keyboard-only end-to-end flows; 200% text and 400% zoom/reflow; focus, contrast, language switching and status messages. axe-core adds regression checks [44,54].'],
['Latency','On assumed laptop: first usable clean page <=15 s after upload; 10-page chapter <=3 min; cached navigation <300 ms. Online answer p95 <=15 s on measured network. Report cold/warm and failures.'],
['Storage / bandwidth','20-page package <=50 MB with chosen image resolution and audio; show exact bytes, model downloads excluded and reported separately. Throttle to 1 Mbps / 300 ms RTT; interrupt download and resume.'],
['Offline behavior','After explicit download, restart app with network disabled; read, navigate, search and bookmark chapter. Clear status for unavailable AI, missing audio and storage eviction. No silent online fallback.'],
['Cost and reliability','Log pages, TTS characters, input/output tokens, retries and per-job costs; hard API budget cap. Crash worker mid-job, retry, edit while offline, then test conflict and stale-cache behavior.']],[0.25,0.75])
p('If intended-user recruitment fails, complete expert/manual checks and disclose the limitation. Do not invent a user study or describe technical test success as accessibility validation or improved learning. A future larger study could test retained understanding after a delay; it is beyond this project\'s evidence claims.')

page(P3,'A. Concrete stack: accessible reader and extraction')
p('Affordable default (P): one TypeScript web app and a Python service/worker on a college laptop. Preprocess chapters there; phones consume prepared chapter packages. A local area network can support a demo, but production phone access and service-worker caching require a trusted HTTPS origin. Localhost on a phone refers to that phone, not the laptop.')
table(['Layer / recommended choice','Why it fits / alternatives','License, hardware and cost boundary'],[
['Frontend: React + TypeScript + Vite; semantic HTML; CSS controls','A single responsive reader; use native controls first. Alternative: vanilla TypeScript reduces framework overhead. PDF.js renders the optional source pane; reflowed HTML is the main reading surface.','React/Vite/TypeScript commonly permissive; confirm exact lockfile licenses. PDF.js Apache-2.0 verified [46]. Device target: Android 4 GB RAM; measure, do not promise minimum compatibility.'],
['Backend: Python 3.11/3.12 + FastAPI + Pydantic','Typed request/response schemas; Python document libraries. Alternative: Node API, but avoid splitting business logic across two backends.','FastAPI MIT verified [53]. One 4-core / 16 GB laptop is the planning target; no per-call API cost locally. Pin a compatible environment after the week-1 spike.'],
['PDF/image ingestion: pdfplumber; PDFium renderer; Pillow / OpenCV','Check native text first; extract coordinates with pdfplumber. Rasterize only necessary pages. Alternative: PyMuPDF is convenient but requires an explicit license decision.','pdfplumber MIT verified [47]. Verify pypdfium2/PDFium notices and OpenCV/Pillow licenses in pinned build. CPU-only; bounded page count/resolution.'],
['OCR: Tesseract eng + hin','Low-cost CPU baseline; preserve word boxes/confidence where available. Explicitly configure language; benchmark mixed-script pages.','Tesseract Apache-2.0; language files listed for English/Hindi [40-41]. Model license/version still recorded. No recurring service charge.'],
['Layout / tables: Docling with selected local OCR adapter','Reuse its layout and document representation; map into a small application schema. Alternative: PaddleOCR/PP-Structure after measurement, rather than running both pipelines in production.','Docling code MIT; PaddleOCR code Apache-2.0 [39,42]. Models have separate notices. Local weights must be predownloaded; CPU memory/latency measured early.'],
['Structured model: JSON Schema + SQLite relational tables','Store typed blocks and edges; no separate graph database required. JSON exports allow debugging and offline transport. Alternative: PostgreSQL if shared deployment grows.','Application-owned schema; record dependency licenses. SQLite database and file store on laptop; no managed database fee.']],[0.28,0.40,0.32])
h('Local versus hosted extraction')
p('Optional higher-quality configuration: send only selected, consented low-quality pages to Google Document AI Enterprise OCR or its layout parser, then map the response into the same block schema. Both are documented services, not guaranteed improvements for this corpus. Benchmark quality, response geometry, processing region and revision/version first; preserve the local candidate for audit. [49-50]')
p('Do not send every page to several vendors or train a large model from scratch. The budget and schedule favor assembling and evaluating pretrained components. If no GPU is available, batch preparation is acceptable; phone-side document parsing is outside MVP. A hosted API brings recurring page fees, connectivity and data-processing terms; local tools bring setup, model-download and CPU costs.')

page(P3,'A. Concrete stack: speech, retrieval and operations')
table(['Layer / default','Alternatives and trade-offs','Constraints to verify'],[
['Speech: eSpeak NG sentence files on preparation server; optional installed device voice','CPU, deterministic file generation and local operation. Less natural than neural voices. Optional Azure Speech produces higher-quality candidate audio plus timing events; listener test decides.','eSpeak core GPL-3.0-or-later [45]; package notices/source obligations reviewed before redistribution. Device voice availability and offline behavior vary. Azure per-character terms and voice-specific SSML limits apply [51-52].'],
['Synchronization: sentence-to-audio manifest','Exact sentence start/end from separate clips; highlight current sentence. Word boundaries only when returned by selected engine and mapped reliably.','Do not estimate word timing by equal durations. Cache by text, language, voice and engine version. No alignment-model training required.'],
['Retrieval: SQLite text search + optional multilingual-e5-small embeddings','Keyword lookup plus 384-dimensional local vectors; brute-force cosine is adequate for a small chapter corpus. Alternative: Postgres/pgvector when scale justifies it.','E5 model card MIT, query:/passage: prefixes and input limits [48]. Test Hindi recall; word tokenization may limit lexical search. CPU inference; no embedding API fee.'],
['Answer generation: Gemini API gemini-3.5-flash-lite; optional [60]','Base mode returns extractive evidence cards. Hosted model receives authorized blocks and returns structured claims. Alternative: licensed small local instruct model on better hardware; not a phone default.','Official stable endpoint supports structured output; this is not a grounding guarantee. Recheck availability, tariff, retention and terms at build time. Hard token/cost limits.'],
['Storage/jobs/cache: SQLite + private files + single durable worker','Jobs table with leases/retries; content-hash derived artifacts. Alternative: Redis/RQ or Celery only when concurrency needs justify another service. IndexedDB/Cache Storage for downloaded chapter.','SQLite/file-system backup and locking tested. Browser quotas/eviction vary. Do not introduce an S3/Redis/graph stack just for a small demo.'],
['Authentication / privacy: local single-user mode; hosted sessions if needed','Local demonstration can avoid student accounts. Shared pilot uses secure session cookies, per-document ownership and authorized reviewer roles.','No raw passwords in app code. Verify auth library licenses and deployment region; collect no diagnosis or speech recordings by default.'],
['Testing / monitoring: pytest, Playwright, axe-core; structured logs','Golden documents, correction dependency tests and keyboard/screen-reader checks. Track stage durations, queue failures, bytes and API usage.','axe-core MPL-2.0 [54]; other pinned licenses recorded. No source text or sensitive query bodies in routine logs. Error metrics do not replace user feedback.']],[0.28,0.40,0.32])
h('Hardware and recurring-cost commitments')
p('Assume a 16 GB preparation laptop and a 4 GB Android client, not a GPU workstation. Cap processing to one page/job at a time and 20-page demo chapters initially. Measure peak RAM, idle/active CPU, model size and package bytes in week 2. These are proposed deployment limits, not measured library minimums. A neural OCR/VLM alternative may exceed them; retain the simpler local route if it does.')
p('There is no unavoidable hosted AI fee in the base reader: preparation and eSpeak speech can be local. Optional hosted OCR, speech, LLM, storage and HTTPS hosting each add charges. Price the exact chosen configuration at build time; service marketing free tiers are not a reliability or budget guarantee. Maintain a dependency/model inventory with license, version, checksum, attribution and redistribution decision.')

page(P3,'B. Architecture: a small pipeline with clear boundaries')
diagram('architecture')
small('Figure 1. Proposed system. The graph is a logical content model stored as ordinary database records. Optional cloud enrichment is isolated; prepared chapter reading does not depend on it.')
h('Responsibilities and important interfaces')
p('<b>Client:</b> upload/capture, accessible status, settings, navigation, review forms and offline package manager. <b>API:</b> authorization, content limits, job state, version negotiation and signed/private artifact access. <b>Worker:</b> native-text inspection, image preprocessing, OCR/layout adapters, structured conversion, quality rules, speech and indexing. <b>Publisher:</b> validates a revision manifest and atomically makes it current. It never exposes a half-updated mixture.')
p('1. Client uploads PDF/image with language hints. 2. API validates bytes and creates a job. 3. Worker extracts one page at a time and preserves geometry. 4. Typed blocks and links become a candidate revision. 5. Checks create review items; authorized corrections create a new revision. 6. Speech and search artifacts are built for eligible content. 7. Reader requests a versioned chapter manifest. 8. Q&A retrieves only eligible current blocks. 9. Client downloads a complete package and stores local reading state. 10. Deletion revokes access and removes derivatives through a tracked job.')
h('Why this is feasible')
p('There are two application processes plus a browser, a relational database and private files. Models are reused, not trained. Parser adapters can be replaced without rewriting the reader; the stable block schema protects the interface. Optional online assistance can fail without blocking access to already prepared content. The complexity budget is spent on correction consistency and accessibility, not on microservices.')

page(P3,'B. Data contracts and provenance')
p('Use opaque document and block IDs, not text hashes as public identity. IDs remain stable for ordinary edits; splitting/merging creates explicit successor links. Physical PDF index and teacher-visible printed page label are different. Coordinates refer to a normalized top-left page space; retain the affine transform to the original pixels, crop and rotation so highlights remain correct.')
code('''Document { id, owner_id, title, source_sha256, rights_note,
  languages[], current_revision, retention_until, state }
Page { id, document_id, pdf_index_0, printed_label,
  width, height, rotation, source_asset, transform }
Block { id, page_id, type, parent_id, order_key,
  bbox:[x0,y0,x1,y1], text_raw, text_current, lang,
  revision, status, confidence:{engine,score,flags[]},
  provenance:{parser,model,version,reviewer,changed_at} }
Edge { from_id, relation, to_id }
Correction { id, block_id, base_revision, operations[],
  author_id, reason, created_at, accepted_revision }
Artifact { id, kind, dependency_revisions[], hash,
  language, voice, engine_version, status, private_uri }''')
p('Block types: heading, paragraph, list item, table, table cell, equation, figure and caption. Relations: contains, precedes, caption-of, refers-to, header-for and supersedes. A table stores row/column indices, spans, header associations and cell IDs. An equation stores reviewed MathML, original crop and a fallback spoken description. A figure stores source caption, short alternative and extended description with separate origin/review status.')
table(['Endpoint / interface','Request and outcome'],[
['POST /documents','Multipart bytes + title/language/rights note. Returns document_id and job_id (202). Reject excess size/pages before expensive processing.'],
['GET /jobs/{id}','State: queued, validating, extracting, review_required, building, ready, failed or cancelled; per-page progress and accessible reason.'],
['GET /documents/{id}/manifest','Current immutable revision, block/page summaries, chapter packages and artifact hashes. Client may request a known revision.'],
['PATCH /blocks/{id}','base_revision + allowed operations. Compare-and-swap; conflicting edit returns 409 with accessible reconciliation fields.'],
['POST /questions','document_id, revision, question, optional block scope. Returns evidence IDs, claims, citations, origin label or abstention reason.'],
['DELETE /documents/{id}','Immediately revokes active access, cancels jobs and schedules physical deletion of source/derivatives; returns deletion job receipt.']],[0.34,0.66])
h('Generated material has a different identity')
p('Store original text, accepted corrections, teacher commentary and AI explanations separately. Answer records include model/prompt version, evidence block revisions, generated timestamp and a visible “AI explanation” label. Never index a generated explanation as if it were source evidence. A correction is a transcription repair; a teacher\'s conceptual rewrite belongs in a labeled note, preserving the original wording for audit.')

page(P3,'B. Extraction, checks and correction propagation')
h('Ingest defensively, preserve evidence')
p('Validate MIME by bytes, allow only PDF/JPEG/PNG initially, reject password-protected or malformed documents with an accessible message, and cap page count, pixels, CPU time and decompression size. Process in a non-privileged worker with a timeout and no document-triggered external URL fetch. Keep source bytes immutable; store processed crops as derivatives. Strip unnecessary camera metadata from working images. These are proposed controls, not a completed security assessment.')
p('Inspect native text coverage and coordinate plausibility before OCR. A mixed PDF may require OCR only on some pages. For photos, test rotation, deskew, crop and conservative contrast correction; do not erase faint minus signs through aggressive thresholding. Docling gives block/layout candidates; Tesseract eng+hin supplies a transparent baseline. Record all parser/model versions and map coordinates back to the source. [39-41,47]')
h('Checks are layered, not a single confidence number')
p('Check empty/duplicate regions, paragraph coverage, column progression, header repetition, impossible character sequences, suspicious script mixing and orphaned captions. Flag formula/table regions separately. Reserve numeric thresholds for development tuning. Text from native PDFs may have no OCR confidence; label it “not scored,” not “100%.” Randomly review a sample of apparently good blocks to detect silent errors. Keep a visible source and edit trail for every accepted correction.')
diagram('correction')
small('Figure 2. Correction transaction and rebuild. A published revision is immutable; a newer one replaces it only after required artifacts pass validation.')
h('Transaction and concurrency behavior')
p('An accepted edit increments the block and document revision in one transaction, records the operation, and marks dependent speech, chunks, embeddings and answers stale. New read/answer requests resolve the new version; stale derivatives cannot be served under its manifest. Rebuild only affected units. Until audio is ready, show text or synthesize the new sentence; do not play old audio as current. An affected answer remains in history with a stale warning, excluded from current answers.')
p('Reading order edits also invalidate sequence manifests and table/figure adjacency. Re-extraction never silently overwrites teacher corrections: propose a new candidate, match by geometry/text, and request reconciliation when IDs cannot be preserved. Two offline reviewers editing the same base revision cause a conflict rather than last-writer-wins. Keep old references resolvable as historical versions while permission and retention allow.')

page(P3,'B. Narration, offline use and privacy')
h('Make synchronization honest and affordable')
p('Split paragraphs into language-tagged sentences, with manual overrides for abbreviations and mixed English-Hindi terms. Generate one clip per sentence and store text offsets, clip duration, block revision and voice. This gives reliable sentence-level highlighting without pretending to have word alignment. For optional Azure synthesis, use returned word/bookmark events only for tested voices; support varies across voice families. [51-52]')
p('A pronunciation glossary maps a term + language + scope to spoken alias or supported phoneme instructions. Scope overrides to document/user so “lead” in chemistry need not alter another book. Keep displayed textbook spelling unchanged. Include units, acronyms and common science terms in a small listener-reviewed English/Hindi list. If TTS fails or a device voice is absent, retain accessible text and cached audio, and announce the missing voice.')
h('Offline package, not an implied offline AI system')
p('A chapter manifest names its revision, trusted block text, navigation, table structure, reviewed math/descriptions, optional source thumbnails, audio hashes and byte sizes. The user explicitly downloads it. Store structured text/settings/bookmarks in IndexedDB and immutable audio/assets in Cache Storage. Verify hashes and switch the active manifest atomically only after required files are present. Keep the old package until replacement succeeds.')
p('Support local navigation, simple text search, sentence playback and bookmarks after restart without network. New OCR and online explanations wait. If audio was not downloaded, offer installed speech only after an offline device check; do not promise that all Web Speech voices work offline. Provide storage usage, download progress, delete-download control and clear recovery when browser eviction removes files. Service workers require HTTPS except local development contexts; configure and test deployment before the pilot.')
table(['Failure / event','Graceful behavior (P)'],[
['Interrupted download / full storage','Retain previous complete package; show missing bytes/files and retry. Do not mark the chapter offline-ready prematurely.'],
['Server revision changes while client offline','Read cached revision with date. Queue bookmarks and correction proposals with base revision; synchronize on reconnection and show conflicts.'],
['Cloud outage / exhausted API budget','Continue reading/search; show evidence passages or a clear assistant-unavailable status. No repeated hidden retries.'],
['Source contains inaccessible STEM','Announce the unreviewed figure/equation/table and offer caption/review request. A source crop is supplementary, not an accessible substitute.']],[0.34,0.66])
h('Secure storage, deletion and retention')
p('Default to private documents, owner/reviewer checks on every API and artifact, HTTPS in hosted mode and secret keys only server-side. Store no diagnosis, microphone recording or unnecessary identifiers. For a pilot, propose source/derivative retention until project end plus 30 days, with immediate user-requested revocation and deletion job completion within 7 days; disclose backup expiry separately (e.g. 30 days). These are policy proposals, not legal compliance claims.')
p('Deletion covers originals and all derivatives. Online clients receive a purge request; disconnected devices require local deletion. Disclose shared-device risks and exact data sent to cloud providers. Review institutional, provider, copyright and applicable data requirements before deployment; this report makes no legal compliance claim.')

page(P3,'B. Grounded assistance and bounded STEM handling')
h('Retrieval and answer contract')
p('Index paragraph-sized chunks of about 150-350 tokens, retaining heading context, page/block IDs and revisions; never split a table cell from its headers. For small chapters start with lexical search and add local E5 vectors after measuring recall. E5 expects <b>query:</b> and <b>passage:</b> prefixes exactly as in the model card; its 384-dimensional embeddings suit a small in-memory index. Truncate/chunk within the selected model\'s input limit. [48]')
p('Filter by owner, document and current eligible revision before ranking. Retrieve a small set (initially top 5) and include neighboring blocks if needed. Unreviewed critical symbols and generated explanations are excluded from trusted evidence. Send only selected excerpts to an optional hosted LLM. The instruction is to explain from supplied evidence, preserve units/negation, identify missing support and return claim-level allowed evidence IDs. Source text is untrusted data; instructions embedded in a book must not change application behavior.')
code('''Answer { origin:"ai_explanation", document_revision:7,
  claims:[{text:"...", evidence:[{block_id:"b17", rev:3}]}],
  abstain:false, uncertainty_notes:[], model_id:"pinned-id" }
Abstention { abstain:true, reason:"source_needs_review",
  evidence_candidates:["b17"], next_action:"open_review" }''')
p('Validate response schema, allowed IDs, revision and quoted spans deterministically. A valid ID is insufficient: evidence may still not entail the claim. Evaluate with human source comparison; optionally add an entailment checker as a second signal. Low retrieval support, contradictory sources, stale content or unresolved critical extraction should trigger an explicit abstention. A prompt alone cannot guarantee groundedness. [35]')
h('Equations, tables and diagrams: explicit support limits')
p('<b>Equations:</b> MVP accepts teacher-verified MathML for a small supported set (fractions, powers and simple algebra). Expose native MathML and test actual NVDA/browser behavior, including numerator/denominator navigation. Use MathCAT through compatible assistive technology, not a custom speech grammar. A crop-to-LaTeX model is stretch; malformed or unverified expressions remain flagged. MathML can encode an incorrectly transcribed formula perfectly. [3,43-44]')
p('<b>Tables:</b> support rectangular tables with a single header row and optional row headers. Render HTML table semantics, announce “row label; column label; value,” and let users move by cell or request a row summary. Treat merged headers, cross-page tables and ambiguous alignment as review cases. A generated verbal summary is additional commentary, not a replacement for exact cells.')
p('<b>Diagrams:</b> retain caption, short alternative and linked extended description. Prefer teacher-reviewed descriptions for the demo. A stretch relation list may expose “battery connects to resistor” with corresponding label IDs, but only after verification. Do not infer trends from unreadable axes or identify missing labels confidently. Test description correctness and student utility separately; fluent visual language can still hallucinate. [36,38]')

page(P3,'C. Fourteen-week roadmap and cut rules')
small('Planning allocation: 504 person-hours across 3 students. Suggested primary ownership: A reader/accessibility, B extraction/content, C API/retrieval/evaluation. Cross-review every interface. Reserve roughly 20% for integration, accessibility repairs and documentation; weeks 15-16 are optional contingency, not hidden MVP scope.')
table(['Week','Deliverable / dependency','Acceptance gate (P/T)'],[
['1','Rights manifest, 24-page development sample; user-task sketches; parser environment spike.','Native text, Tesseract and Docling run on actual laptop; measure RAM/time. Confirm Hindi OCR and font rendering.'],
['2','Hardest-risk experiment: annotate key errors/order; compare pipelines and review burden.','Decide clean-PDF vs photo scope; publish errors and flagging curves. Narrow scope if ordinary-page repair exceeds 3 min/page.'],
['3','Versioned JSON schema, page coordinates and API contracts; accessible reader skeleton.','10 fixture pages retain printed/PDF page mapping; keyboard navigation and labeled controls work.'],
['4','Durable jobs, ingestion caps, text/layout adapter. Depends on schema.','Interrupted job retries idempotently; no duplicate documents/artifacts or hanging progress.'],
['5','Correction forms, role checks, revision transactions and dependency invalidation.','Seeded edits make audio/index/answer stale; unauthorized and conflicting edits rejected.'],
['6','Sentence narration, glossary, English-Hindi segmentation.','Ten mixed-language passages checked by listeners; missing-voice fallback is explicit.'],
['7','Reflow, heading/page navigation, preferences, simple table semantics.','NVDA keyboard tasks and Android TalkBack smoke test; no critical focus trap.'],
['8','Offline manifests, cache/download controls and resume.','Airplane-mode restart reads downloaded text/audio; interrupted update keeps valid old package.'],
['9','Chapter retrieval, evidence cards and citation return navigation.','Development evidence Recall@5 measured; cross-document leakage/stale references rejected.'],
['10','Optional generated explanations with abstention; reviewed MathML/figures.','Question set includes missing evidence and injected book instructions; enforce ID/revision checks.'],
['11','Freeze features; complete extraction/Q&A held-out tests and failure drills.','Report all denominators, supported coverage, per-language errors and measured resource costs.'],
['12','Consent-based formative sessions or disclosed expert fallback.','Document independent task success, assistance, preferences and group-specific barriers.'],
['13','Fix highest-impact barriers; repeat only affected checks.','No unresolved blocker in upload/read/find/return/offline/delete flows; report remaining limitations.'],
['14','Release package, reproducible demo, model/license manifest and final report.','Fresh-machine setup verified; demo works without cloud; achieved results clearly separate from targets.'],
['15-16','Contingency: repair/integration; selected stretch only after gates.','No new flagship; repeat affected evaluation and freeze final version.']],[0.08,0.48,0.44])
h('What to cut, and what to protect')
p('Cut in order: automatic diagram relations; automatic equation OCR; word-level alignment; extra languages; generative answer prose. Keep passage retrieval and source links. If extraction is weak, deliver teacher-reviewed chapter preparation and disclose preparation effort. Protect accessible navigation, correction consistency, offline restart and honest status labeling. If only 12 weeks are available, combine weeks 9-10 as extractive evidence support and move feature freeze to week 9; use weeks 10-12 for testing, repairs and release.')

page(P3,'C. Evaluation corpus and costed delivery')
h('A small corpus with a rights ledger')
p('Prepare 72 unique pages: 24 development and 48 held-out, from disjoint chapters. Aim for 24 English science pages from the specifically licensed OpenStax <i>Physics</i> edition, 24 Hindi / mixed-language science pages authored by the team or supplied by a teacher with written adaptation/testing permission, and 24 varied supplementary pages split between team-made layouts and clearly licensed StoryWeaver books. StoryWeaver material is a multilingual narrative/illustration stress case, not a science-textbook substitute. Final selection is a week-1 deliverable, not a corpus already acquired. [55-58]')
p('Across this set, select 20 equations, 12 simple tables and 12 figures for separate annotation. Include single/two-column prose, sidebars, footnotes, mixed script and technical units. For 12 source pages create clean scans plus skew/blur/shadow phone variants; keep variants in the same split and report them separately, not as independent originals. Two people check text/order/STEM references; adjudicate disagreements before testing.')
p('Record source URL, title, edition/date, chapter/page, creator, download date, checksum, exact license, third-party asset exclusions, attribution and permission evidence. The reviewed <i>Physics</i> preface says CC BY 4.0, while OpenStax\'s general current help describes CC BY-NC-SA. Check the exact downloaded edition/file and every selected asset; do not generalize either notice. StoryWeaver books/images use CC BY 4.0 with attribution, while readalongs/videos have different restrictions. Use book assets only. NCERT access does not imply republication permission: its notice prohibits rehosting. Exclude NCERT from the redistributed demo without permission. [55-59]')
h('Budget envelope: planning allocations, not vendor quotations')
table(['Item / assumption','Base INR','Upper INR'],[
['Participant time / local travel: 6 sessions x 500; up to 9 x 700',3000,6300],
['Optional APIs: OCR/TTS/LLM combined hard spending cap',1500,3000],
['Temporary HTTPS hosting / storage allocation',500,1000],
['Printing / phone data / simple capture stand',500,1000],
['Contingency',1500,2700],
['Total cash envelope (existing hardware and labor excluded)',7000,14000]],[0.66,0.17,0.17])
p('The base month-to-month reader can run locally without paid model calls. The allocations above do not promise that any named service costs that amount. Track API cost as pages x OCR rate + TTS characters/1M x speech rate + input tokens/1M x input rate + output tokens/1M x output rate + storage/egress; add retries, taxes and currency conversion when relevant. Use current provider tariffs before enabling a paid route, with user-visible limits and a server-side stop.')
p('Storage sanity check (assumption): 20 pages x 500 words / 150 spoken words per minute is about 66.7 minutes. At 32 kbit/s, compressed audio is about 16 MB (decimal); add thumbnails, text and manifests. This explains the proposed 50 MB package target, not a measured result. Store actual durations and bytes because language, rate and encoding change the total.')

page(P3,'D. Build first, demonstrate honestly, publish limits')
h('Exactly what to build first')
p('Implement one 10-12 page English/Hindi demonstration chapter using the final block schema, accessible heading/page navigation and sentence reading. Then add one text/order correction that atomically invalidates audio and retrieval and rebuilds them. Run that path offline after download. Only once this works should the team add evidence-linked generation. This sequence makes the first usable product independent of LLM availability.')
h('A convincing eight-minute end-to-end demonstration')
table(['Time','Action and visible evidence'],[
['0:00-1:00','Upload a legally usable chapter; show page count, physical/printed page mapping, extraction progress and declared language scope.'],
['1:00-2:00','Navigate by heading and printed page with keyboard/NVDA; reflow at large text; toggle narration independently of screen-reader speech.'],
['2:00-3:15','Open a clearly disclosed seeded OCR/symbol issue. Correct through a labeled form. Show revision increment and stale derivative states.'],
['3:15-4:15','Listen to rebuilt sentence; read a simple table cell with its row/column headers; inspect one explicitly pre-reviewed equation.'],
['4:15-5:30','Ask a supported question, open its exact evidence paragraph and return. Ask an unsupported question and receive a meaningful abstention.'],
['5:30-6:45','Disable network, restart and resume the downloaded chapter; search and bookmark. Show assistant unavailable without blocking reading.'],
['6:45-8:00','Reconnect and show revision synchronization, then deletion receipt. Present held-out measurements, preparation time and remaining failures.']],[0.19,0.81])
h('An honest novelty statement for the project review')
box('“Pathya is a student-built integration of structured textbook extraction, accessible reading and evidence-linked study support. Our proposed contribution is a revision-aware workflow that exposes extraction uncertainty and propagates corrections to narration, navigation and answer evidence, evaluated on a bounded English-Hindi corpus and affordable devices. We do not claim that OCR, TTS, document chat, source citations or accessible math navigation are new.”')
h('Largest limitations and unresolved questions')
p('Uncertainty heuristics can miss fluent but wrong OCR; human review remains necessary. Hindi technical pronunciation and mixed-script search require native-speaker testing. Reviewed MathML/descriptions restrict scale, and helper dependence may reduce independence. Browser storage can be evicted, online services can change, and a small user sample cannot prove educational or clinical efficacy. The project needs a named maintenance owner after the semester to remain dependable.')
p('Continue only if early experiments establish a useful extraction-and-repair workflow. Success means supported content stays navigable, corrections stay consistent and students can check evidence with manageable effort. Publish failures and unsupported content coverage alongside aggregate scores. No accuracy, learning gain, novelty or cost saving has been measured by this report.')
small('Report quality note: the PDF is designed for readable visual review and includes linked citations and page numbers. It is not certified PDF/UA or claimed to be a fully tagged accessible PDF. The companion HTML carries the same report text, semantic headings and tables for reflow/screen-reader use. Both describe a proposal, not an implemented system.')

# Remove the standalone contract recap: these requirements are specified in the
# data, extraction, answer and evaluation sections rather than repeated here.
pages=[pg for pg in pages if pg['title']!='C. Flagship contracts and accessibility behavior']
quality_item=pages[-1]['items'].pop()
pages[0]['items'].append(quality_item)

for i,group in enumerate([refs[:20],refs[20:40],refs[40:]]):
    page(P3,f'D. Numbered bibliography ({i+1} of 3)')
    small('Every source below was accessed on 16 November 2026. Dates are publication/update dates where verified; n.d. means no stable publication date established. Living pages and repositories can change. Titles link to original sources. Product documentation is vendor evidence. Research conclusions are bounded by the reviewed study.')
    for r in group:
        current['items'].append(('ref',r))

def markup(s):
    # Escape only stray ampersands; authored ReportLab-compatible tags are intentional.
    s=re.sub(r'&(?!amp;|lt;|gt;|quot;|#\d+;)', '&amp;', str(s))
    def cite(m):
        content=m.group(1); nums=[]
        for bit in content.split(','):
            if '-' in bit:
                a,b=map(int,bit.split('-'));nums.extend(range(a,b+1))
            else:nums.append(int(bit))
        return '['+', '.join(f'<link href="#ref{n}" color="#087F83">{n}</link>' for n in nums)+']'
    return re.sub(r'\[(\d+(?:[-,]\d+)*)\]',cite,s)

class Diagram(Flowable):
    def __init__(self,kind):Flowable.__init__(self);self.kind=kind;self.width=505;self.height=245 if kind=='architecture' else 122
    def draw(self):
        c=self.canv
        def node(x,y,w,hh,title,sub=''):
            c.setFillColor(PALE);c.setStrokeColor(LINE);c.roundRect(x,y,w,hh,5,fill=1,stroke=1)
            c.setFillColor(NAVY);c.setFont('Bold',10);c.drawCentredString(x+w/2,y+hh-17,title)
            if sub:
                c.setFont('Body',8.6)
                for j,line in enumerate(sub.split('|')):c.drawCentredString(x+w/2,y+hh-31-j*11,line)
        def arrow(x1,y1,x2,y2):
            c.setStrokeColor(TEAL);c.setFillColor(TEAL);c.setLineWidth(1.2);c.line(x1,y1,x2,y2)
            ang=math.atan2(y2-y1,x2-x1);a=5
            pth=c.beginPath();pth.moveTo(x2,y2);pth.lineTo(x2-a*math.cos(ang-.5),y2-a*math.sin(ang-.5));pth.lineTo(x2-a*math.cos(ang+.5),y2-a*math.sin(ang+.5));pth.close();c.drawPath(pth,fill=1,stroke=0)
        if self.kind=='architecture':
            node(0,180,145,58,'Accessible client','Upload / reader / review|Offline chapter cache')
            node(180,180,145,58,'FastAPI boundary','Authorization / validation|Jobs / manifests / revisions')
            node(360,180,145,58,'Durable worker','Extract / check / rebuild|Local models and speech')
            arrow(145,208,180,208);arrow(325,208,360,208)
            node(180,84,145,66,'Content + provenance','SQLite blocks / edges|Immutable source assets|Versioned derived artifacts')
            arrow(252,180,252,150);arrow(432,180,432,117);arrow(432,117,325,117)
            node(0,0,145,61,'Study API','Eligible evidence retrieval|Claims / citations / abstain')
            node(360,0,145,61,'Optional cloud','OCR / neural TTS / LLM|Consented data only')
            arrow(180,112,72,112);arrow(72,112,72,61);arrow(145,30,360,30)
            arrow(0,30,0,180)
        else:
            node(0,56,145,60,'Accepted correction','Compare base revision|Append change event')
            node(180,56,145,60,'Mark dependencies stale','Audio / search / answers|Old versions stay historical')
            node(360,56,145,60,'Rebuild and validate','Publish new manifest|Sync version + hashes')
            arrow(145,86,180,86);arrow(325,86,360,86)
            c.setFillColor(MUTED);c.setFont('Body',9);c.drawCentredString(252,20,'New requests cannot label old derivatives as current.')

def make_table(data):
    heads,rows,widths=data; vals=[[Paragraph(markup(x),styles['th']) for x in heads]]
    vals += [[Paragraph(markup(x),styles['cell']) for x in row] for row in rows]
    t=Table(vals,colWidths=[505*x for x in widths],hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LINEBELOW',(0,0),(-1,0),.6,NAVY),('LINEBELOW',(0,1),(-1,-1),.35,LINE),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F8')])]))
    return t

def footer(c,doc):
    c.saveState();c.setFillColor(TEAL);c.rect(45,804,29,3,fill=1,stroke=0)
    c.setFont('Bold',8);c.setFillColor(MUTED);c.drawString(82,803,'PATHYA / RESEARCH AND IMPLEMENTATION REPORT')
    c.setStrokeColor(LINE);c.line(45,37,550,37);c.setFont('Body',8);c.drawString(45,24,'Proposal only | Sources accessed 16 Nov 2026');c.drawRightString(550,24,f'{doc.page} / 25');c.restoreState()

story=[]
for idx,pg in enumerate(pages):
    if idx:story.append(PageBreak())
    # Part names are the only main-part headings; internal pages carry concise section labels.
    story.append(Paragraph(pg['part'],styles['small']))
    story.append(Paragraph(pg['title'],styles['title'] if idx==0 else styles['subtitle']))
    for typ,val in pg['items']:
        if typ in ('p','h','small'):story.append(Paragraph(markup(val),styles[typ]))
        elif typ=='table':story.extend([make_table(val),Spacer(1,9)])
        elif typ=='box':
            t=Table([[Paragraph(markup(val),styles['p'])]],colWidths=[505]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.6,LINE),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),3)]));story.extend([t,Spacer(1,8)])
        elif typ=='code':story.append(Paragraph(html.escape(val).replace(' ','&nbsp;').replace('\n','<br/>'),styles['code']))
        elif typ=='diagram':story.append(Diagram(val))
        elif typ=='ref':
            r=val;txt=f'<a name="ref{r["n"]}"/>[{r["n"]}] <link href="{html.escape(r["url"],quote=True)}" color="#087F83">{html.escape(r["title"])}</link>. {html.escape(r["date"])}. {html.escape(r["kind"])}.'
            story.append(Paragraph(txt,styles['ref']))

pdf=OUT/'Pathya_AI_Textbook_Reader_Project_Report.pdf'
doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=45,leftMargin=45,topMargin=54,bottomMargin=48,title='Pathya: AI Textbook Reader - Research and Implementation Report',author='Project research report',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)

# Semantic HTML companion: all text, tables and diagram descriptions, with no PDF tagging claim.
parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pathya - AI textbook reader report</title><style>body{max-width:78ch;margin:2rem auto;padding:0 1rem;font:1.05rem/1.65 Arial,sans-serif;color:#182b38}h1,h2,h3{line-height:1.25;color:#16354b}h1{border-top:4px solid #087f83;padding-top:1rem}table{border-collapse:collapse;width:100%;font-size:.9rem;margin:1rem 0}th,td{border:1px solid #ccdadd;padding:.6rem;vertical-align:top;text-align:left}th{background:#edf5f5}a{color:#006c70}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f6;padding:1rem}aside{border-left:4px solid #087f83;padding:1rem;background:#edf5f5}.scroll{overflow-x:auto}li{margin-bottom:.6rem}</style></head><body><nav aria-label="Report parts"><a href="#part1">Part 1</a> | <a href="#part2">Part 2</a> | <a href="#part3">Part 3</a> | <a href="#references">References</a></nav><main>']
last=None
def hm(s):return markup(s).replace('<link href=', '<a href=').replace(' color="#087F83"','').replace('color="#087F83"','').replace('</link>','</a>')
for pg in pages:
    if pg['part']!=last:
        n=1 if pg['part']==P1 else 2 if pg['part']==P2 else 3
        parts.append(f'<h1 id="part{n}">{pg["part"]}</h1>');last=pg['part']
    parts.append(f'<section><h2>{html.escape(pg["title"])}</h2>')
    if pg['title']=='D. Numbered bibliography (1 of 3)':parts.append('<div id="references"></div>')
    for typ,val in pg['items']:
        if typ in ('p','small'):parts.append('<p>'+hm(val)+'</p>')
        elif typ=='h':parts.append('<h3>'+hm(val)+'</h3>')
        elif typ=='box':parts.append('<aside>'+hm(val)+'</aside>')
        elif typ=='code':parts.append('<pre>'+html.escape(val)+'</pre>')
        elif typ=='table':
            headers,rows,_=val;parts.append('<div class="scroll"><table><thead><tr>'+''.join('<th scope="col">'+hm(x)+'</th>' for x in headers)+'</tr></thead><tbody>')
            for row in rows:parts.append('<tr>'+''.join(('<th scope="row">' if i==0 else '<td>')+hm(v)+('</th>' if i==0 else '</td>') for i,v in enumerate(row))+'</tr>')
            parts.append('</tbody></table></div>')
        elif typ=='diagram':parts.append('<p><strong>Diagram text equivalent:</strong> '+('Client uploads to the API, which validates and schedules a durable worker. The worker extracts and checks content, then stores versioned blocks and artifacts. The study API retrieves eligible evidence from that store. Optional cloud services provide consented enrichment. The client caches complete chapter packages for offline reading.' if val=='architecture' else 'An accepted correction records a new revision, marks dependent audio, search and answers stale, rebuilds affected artifacts, validates and publishes a new manifest. Old derivatives cannot be served as current.')+'</p>')
        elif typ=='ref':parts.append(f'<p id="ref{val["n"]}">[{val["n"]}] <a href="{html.escape(val["url"],quote=True)}">{html.escape(val["title"])}</a>. {html.escape(val["date"])}. {html.escape(val["kind"])}. Accessed 16 November 2026.</p>')
    parts.append('</section>')
parts.append('</main></body></html>');(OUT/'Pathya_Report_Accessible_Companion.html').write_text('\n'.join(parts),encoding='utf-8')
(OUT/'Pathya_Report_Source.json').write_text(json.dumps({'references':refs,'pages':pages},ensure_ascii=False,indent=2),encoding='utf-8')
print(pdf)
print('Authored pages:',len(pages),'References:',len(refs))
