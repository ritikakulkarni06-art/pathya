from pathlib import Path
import re, html, json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT=Path(__file__).parent
OUT=ROOT/'output'/'pdf';OUT.mkdir(parents=True,exist_ok=True)
for name,file in [('Body','arial.ttf'),('Bold','arialbd.ttf'),('Italic','ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
NAVY=colors.HexColor('#16354B');TEAL=colors.HexColor('#087F83');INK=colors.HexColor('#182B38');MUTED=colors.HexColor('#536574');PALE=colors.HexColor('#EDF5F5');LINE=colors.HexColor('#CCDADC')
S={
'title':ParagraphStyle('title',fontName='Bold',fontSize=26,leading=30,textColor=NAVY,spaceAfter=12),
'sub':ParagraphStyle('sub',fontName='Bold',fontSize=18,leading=23,textColor=NAVY,spaceAfter=12),
'h':ParagraphStyle('h',fontName='Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=9,spaceAfter=6),
'p':ParagraphStyle('p',fontName='Body',fontSize=10.4,leading=14.8,textColor=INK,spaceAfter=8),
'small':ParagraphStyle('small',fontName='Body',fontSize=9,leading=12.2,textColor=MUTED,spaceAfter=8),
'cell':ParagraphStyle('cell',fontName='Body',fontSize=9.2,leading=12.2,textColor=INK),
'th':ParagraphStyle('th',fontName='Bold',fontSize=9.2,leading=12.2,textColor=colors.white),
'bullet':ParagraphStyle('bullet',fontName='Body',fontSize=10.1,leading=14,textColor=INK,leftIndent=11,firstLineIndent=-9,spaceAfter=5),
}
def fmt(t):
    t=html.escape(str(t));return re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',t).replace('\n','<br/>')
def p(t,style='p'):return Paragraph(fmt(t),S[style])
def tab(headers,rows,widths):
    vals=[[p(v,'th') for v in headers]]+[[p(v,'cell') for v in r] for r in rows]
    t=Table(vals,colWidths=[493*w for w in widths],hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,1),(-1,-1),.4,LINE),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F8')])]))
    return t
def box(t):
    b=Table([[p(t)]],colWidths=[493]);b.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.6,LINE),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),3)]));return b
story=[]
def page(k,title,first=False):
    if story:story.append(PageBreak())
    story.extend([p(k,'small'),p(title,'title' if first else 'sub')])
def para(t):story.append(p(t))
def heading(t):story.append(p(t,'h'))
def table(headers,rows,widths):story.extend([tab(headers,rows,widths),Spacer(1,9)])
def callout(t):story.extend([box(t),Spacer(1,9)])

page('PROJECT CONCEPT + THREE-PERSON EXECUTION PLAN','Pathya\nAI Textbook Reader'.replace('\n',' | '),True)
para('**For students with visual impairment or dyslexia**')
para('Pathya is a proposed accessible textbook reader that converts authorized English and Hindi chapters into structured, navigable content. Students can read or listen, return to the original page, flag extraction errors, download prepared chapters and ask for explanations supported by the textbook.')
callout('**Core idea:** make textbook content easier to access, easier to verify and easier to repair. A correction should update the relevant narration, search results and answer evidence throughout the system.')
heading('The problem the project addresses')
para('A scanned page may have no usable text. OCR can mix columns or lose symbols, while ordinary narration can flatten headings, equations and tables. Students need a way to find a specific section, revisit evidence and recognize when extracted content needs review. Hearing text alone does not establish comprehension.')
table(['User group','Proposed support'],[
['Blind students','Semantic structure, keyboard/screen-reader navigation, page/heading jumps and reviewed descriptions.'],
['Students with low vision','Reflow, adjustable text and contrast, plus a separately zoomable source page.'],
['Students with dyslexia','Optional narration, sentence focus, adjustable pace and clear explanations with source links.']],[.29,.71])
heading('Planning assumptions')
para('**3 students; 14 weeks; 12 hours per person per week.** Planned effort is 168 hours each, or 504 team hours. Use an existing preparation laptop and an Android phone; English and Hindi are the initial language scope. Equal hours are a starting allocation, not a guarantee of equal difficulty.')
story.append(p('Prepared 16 November 2026. This document defines a proposed project and team plan. Features, acceptance checks and effort estimates are not implemented or validated results. Fonts and reading preferences are accommodations, not treatments for dyslexia.','small'))

page('01 / THE PRODUCT','What the team will build')
heading('Three flagship capabilities')
table(['Flagship','Meaning in the working system'],[
['1. Shared, page-linked content','Text, headings, tables, reviewed equations, descriptions and audio connect to stable blocks and the original page.'],
['2. Uncertainty and correction','Questionable extraction is flagged with a reason. An accepted correction creates a new revision and triggers affected output rebuilds.'],
['3. Evidence-linked assistance','Search and explanations return supporting passages. The assistant abstains when the source is missing, unreliable or outdated.']],[.32,.68])
heading('The student journey')
para('1. **Import:** upload an authorized PDF or page photo and select language hints.\n2. **Prepare:** extract text/layout, preserve page links and review uncertain content.\n3. **Read:** navigate by heading, printed page or paragraph; choose visual reading, narration or a screen reader.\n4. **Study:** inspect a simple table or reviewed equation, bookmark a passage and open explanation evidence.\n5. **Continue offline:** download a chapter, restart without internet and resume reading.\n6. **Repair:** submit a correction and synchronize the new version when connected.')
heading('A concrete demonstration example')
para('A physics chapter contains a suspicious minus sign. The reader shows a review flag. An authorized helper checks the original crop and corrects the text. The backend marks affected audio and search entries stale, rebuilds them and publishes the new revision. A later answer cites the corrected paragraph. An unsupported question receives a clear abstention.')
heading('MVP boundaries')
para('Support clean PDFs, basic photo input, English/Hindi prose, simple rectangular tables and a small set of reviewed MathML equations and figure descriptions. Cache prepared chapter text/audio for offline use. Keep cloud explanations optional; reading should continue when the assistant is unavailable.')
callout('**Cut first if time is limited:** automatic diagram reasoning, automatic equation OCR, word-level audio alignment and extra languages. If necessary, retain extractive evidence cards and cut generated answer prose. Protect accessible navigation, correction consistency, source links and offline restart.')
story.append(p('The project combines established techniques into a measurable workflow. Do not claim that OCR, TTS, document Q&A, source citations or accessible mathematics are new. Detailed research and references remain in the accompanying full project report.','small'))

# Preserve all three detailed role descriptions and their effort allocations.
md=(ROOT/'Pathya_Three_Person_Role_Plan.md').read_text(encoding='utf-8')
role_sections=re.split(r'^## ',md,flags=re.M)
roles=[s for s in role_sections if s.startswith('Person ')]
stack_notes=[
('Suggested tools','Python, pdfplumber, Pillow/OpenCV, Tesseract eng+hin, Docling and JSON Schema. Use pretrained models and benchmark them on the actual laptop.'),
('Suggested tools','React, TypeScript, semantic HTML/CSS, PDF.js for source views, a speech adapter, IndexedDB/Cache Storage, Playwright and manual assistive-technology checks.'),
('Suggested tools','Python/FastAPI, SQLite, private file storage and a durable worker. Start with chapter search; add local embeddings and an optional hosted LLM adapter after the reader works.')]
for i,section in enumerate(roles,1):
    lines=section.strip().splitlines(); title=lines[0].replace(f'Person {i}: ','')
    page(f'0{i+1} / PERSON {i}',title[0].upper()+title[1:])
    for line in lines[1:]:
        if not line.strip():continue
        if line.startswith('|'):continue
        if line.startswith('- '):story.append(p('- '+line[2:],'bullet'))
        else:para(line)
    heading(stack_notes[i-1][0]);story.append(p(stack_notes[i-1][1],'small'))
    rows=[]
    for line in lines:
        if line.startswith('|'):
            vals=[v.strip() for v in line.strip('|').split('|')]
            if vals[0] not in ('Work package','---'):rows.append(vals)
    heading('Planned workload')
    table(['Work package','Hours'],rows,[.85,.15])

page('05 / OWNERSHIP AND HANDOFFS','How the three roles connect')
callout('**Person 1 produces structured content. Person 3 stores and versions it. Person 2 makes it usable.** Every feature has one accountable owner and explicit supporting contributions.')
table(['Feature','Owner','Required handoff'],[
['OCR, layout and quality flags','Person 1','Person 3 schedules extraction jobs; Person 2 displays progress, content and review states.'],
['Shared schema and identifiers','Person 3','Person 1 supplies extraction fields; Person 2 supplies navigation requirements. All agree before implementation.'],
['Correction workflow','Person 3','Person 2 collects edits; Person 1 applies content operations; Person 3 commits versions and rebuilds dependencies.'],
['Reader and source navigation','Person 2','Person 1 supplies page geometry; Person 3 delivers authorized, versioned blocks and assets.'],
['Speech and synchronization','Person 2','Person 1 supplies source text/language metadata. Person 2 owns segmentation and speech; Person 3 schedules and stores artifacts.'],
['Offline reading','Person 2','Person 3 publishes immutable chapter manifests. Person 2 downloads, validates, caches and restores them.'],
['Evidence retrieval and answers','Person 3','Person 1 supplies source eligibility and provenance; Person 2 presents citations, uncertainty and return navigation.'],
['Evaluation and release','All three','Person 1 leads extraction/STEM checks; Person 2 leads accessibility/usability; Person 3 leads integrity, security and grounding.']],[.29,.15,.56])
heading('Agree on these contracts in week 1')
para('**Content block:** document ID, page ID, printed label, block ID, type, text, language, reading order, bounding box, revision, review status and provenance. **Audio unit:** sentence offsets, source revision, language, voice, file hash and duration. **Answer:** document revision, claims, evidence block IDs and an abstention reason when needed.')
heading('Correction and synchronization rule')
para('Edits include the revision on which they were made. Conflicting edits require reconciliation. Accepted changes invalidate dependent audio, index chunks and answers; outdated outputs cannot be presented as current. A failed rebuild must leave an explicit state and a usable text fallback.')

page('06 / DELIVERY SCHEDULE','Fourteen weeks, integrated from the start')
table(['Weeks','Person 1','Person 2','Person 3'],[
['1-2','Corpus, rights ledger and OCR/layout feasibility experiment.','Accessible mock reader, user tasks, phone/voice checks.','Shared schema, mock API, storage and job skeleton.'],
['3-4','Extraction adapter, block structure and source mapping.','Reader navigation against mock and actual content.','Upload/status/manifest APIs and durable jobs.'],
['5-6','Quality flags and content correction operations.','Review forms, narration and sentence highlighting.','Revision transactions, conflicts and invalidation.'],
['7-8','Simple tables and reviewed STEM assets.','Offline download, restart, search and resume.','Consistent manifest publishing and private asset delivery.'],
['9-10','Evidence quality and eligibility checks.','Open citations, return to answer and show abstention.','Retrieval, evidence cards and optional generation.'],
['11-12','Held-out extraction and STEM evaluation.','Keyboard/screen-reader checks and formative sessions.','Grounding, cost, consistency and failure tests.'],
['13-14','Fix content failures and document results.','Fix interaction barriers and rehearse reader demo.','Fix integration failures and package deployment.']],[.11,.30,.30,.29])
heading('Joint milestone gates')
table(['By the end of','Acceptance check - proposed, not achieved'],[
['Week 2','Choose supported source quality and parser after measuring errors, memory, latency and review effort.'],
['Week 4','One chapter imports and opens end to end with correct page/block links.'],
['Week 6','One accepted correction updates relevant text and speech without serving outdated output as current.'],
['Week 8','A downloaded chapter works after network loss and application restart.'],
['Week 10','A supported answer opens exact evidence; an unsupported question abstains.'],
['Week 14','Fresh setup, integrated demonstration and actual evaluation results are documented.']],[.22,.78])
heading('Weekly team routine')
para('Hold one short planning meeting and one end-to-end integration review each week. Keep shared types, mock fixtures and setup instructions in the repository. Rebalance bounded tasks using actual effort. Avoid leaving integration, accessibility repairs or documentation to one person at the end.')

page('07 / VERIFICATION AND PRESENTATION','What each person must prove')
table(['Person','Evidence to collect','Individual demonstration'],[
['1 - Document AI','OCR character/word errors, reading-order errors, flagged critical errors, correction time and separate STEM failures.','Show source page, structured output, uncertainty and before/after extraction results.'],
['2 - Reader and offline','Keyboard/screen-reader task completion, navigation errors, zoom/reflow behavior, narration checks and offline restart results.','Find a passage, read a table, play synchronized speech and resume after disabling network.'],
['3 - Backend and AI','Revision consistency, rejected stale/cross-document citations, grounding/abstention results, job recovery and API usage.','Correct a passage, show dependent outputs updating, open valid evidence and demonstrate abstention.']],[.22,.43,.35])
heading('Shared definition of done')
for t in [
'A student can import or open a prepared chapter, find a section and return from evidence without losing context.',
'Each correction has a traceable revision; relevant narration, search and answers stay consistent.',
'Prepared content remains readable offline; unavailable AI or audio is clearly identified.',
'No unresolved blocker remains in core keyboard and screen-reader flows. Report unsupported content honestly.',
'Any user evaluation uses accessible consent and appropriate institutional processes. Small formative studies do not establish clinical or population-wide efficacy.',
'Each member documents their own method, results, limitations and setup requirements; the team verifies the integrated release.'
]:story.append(p('- '+t,'bullet'))
heading('Cross-review and final submission')
para('Person 1 reviews Person 3\'s source support. Person 2 reviews Person 1\'s content usability. Person 3 reviews Person 2\'s cache/version handling. Person 2 coordinates report readability, Person 1 checks citations and content permissions, and Person 3 checks architecture and configuration consistency. Each member repairs failures in their own components.')
callout('**Final project statement:** Pathya is a proposed accessible English-Hindi textbook reader with structured source navigation, visible extraction uncertainty, revision-aware corrections, offline study and optional evidence-linked explanations. Its contribution should be demonstrated through reliability and user tasks, without exaggerating novelty.')
story.append(p('Suggested submission package: working application, reproducible setup, model/dependency and content-rights manifests, evaluation results, architecture/schema documentation, final report and a rehearsed team demonstration.','small'))

def footer(c,doc):
    c.saveState();c.setFillColor(TEAL);c.rect(45,804,28,3,fill=1,stroke=0);c.setFillColor(MUTED);c.setFont('Bold',8);c.drawString(82,803,'PATHYA / PROJECT IDEA AND THREE-PERSON ROLE PLAN')
    c.setStrokeColor(LINE);c.line(45,37,550,37);c.setFont('Body',8);c.drawString(45,24,'Proposed plan | 3 members | 14 weeks | 504 planned hours');c.drawRightString(550,24,f'{doc.page} / 8');c.restoreState()
pdf=OUT/'Pathya_Project_Idea_and_Three_Person_Roles.pdf'
doc=SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=54,bottomMargin=48,title='Pathya - Project Idea and Three-Person Roles',author='Pathya project planning',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
r=PdfReader(pdf);assert len(r.pages)==8,len(r.pages)
text='\n'.join(page.extract_text() for page in r.pages)
assert all(f'PERSON {i}' in text for i in (1,2,3))
assert text.count('168')>=4
assert '\ufffd' not in text
print(json.dumps({'file':str(pdf),'pages':len(r.pages),'bytes':pdf.stat().st_size,'words':len(text.split())},indent=2))
