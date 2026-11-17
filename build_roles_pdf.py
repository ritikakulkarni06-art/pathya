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

page('PROJECT IDEA AND THREE CLEAR TEAM ROLES','Pathya | AI Textbook Reader',True)
para('**For students with visual impairment or dyslexia**')
para('Pathya is a proposed accessible textbook reader that converts authorized English and Hindi chapters into structured, navigable content. Students can read or listen, return to the original page, flag extraction errors, download prepared chapters and ask for explanations supported by the textbook.')
callout('**Core idea:** make textbook content easier to access, easier to verify and easier to repair. A correction should update the relevant narration, search results and answer evidence throughout the system.')
heading('The problem the project addresses')
para('A scanned page may have no usable text. OCR can mix columns or lose symbols, while ordinary narration can flatten headings, equations and tables. Students need a way to find a specific section, revisit evidence and recognize when extracted content needs review. Hearing text alone does not establish comprehension.')
table(['User group','Proposed support'],[
['Blind students','Semantic structure, keyboard/screen-reader navigation, page/heading jumps and reviewed descriptions.'],
['Students with low vision','Reflow, adjustable text and contrast, plus a separately zoomable source page.'],
['Students with dyslexia','Optional narration, sentence focus, adjustable pace and clear explanations with source links.']],[.29,.71])
heading('The three roles at a glance')
table(['Member','Main responsibility'],[
['Person 1 - Document AI','Convert textbook pages into reliable, structured content and identify extraction problems.'],
['Person 2 - Accessible reader','Build the student interface, narration, reading controls and offline experience.'],
['Person 3 - Backend and AI','Manage storage, corrections and versions; retrieve evidence and generate supported answers.']],[.34,.66])
story.append(p('This is a proposed project and responsibility split. Capabilities described here are intended behavior, not implemented or validated results. Reading preferences are accommodations, not treatments for dyslexia.','small'))


role_data=[
{
'title':'Document AI and content engineering',
'purpose':'Person 1 is responsible for understanding the textbook page and converting it into content the application can use. This person makes sure text, reading order, tables and source locations are preserved, and identifies content that needs human review.',
'rows':[
['PDF and image preparation','Inspect existing PDF text and prepare scanned pages or photographs using rotation, cropping and conservative image cleanup.'],
['OCR and layout extraction','Integrate English/Hindi OCR and identify headings, paragraphs, columns, captions and reading order.'],
['Structured textbook content','Produce blocks with stable identifiers, page locations, language labels, text and provenance. Preserve links to the original page.'],
['Uncertainty and content repair','Flag suspicious symbols, missing text and incorrect order. Apply accepted text, order, language and structure corrections.'],
['Tables, equations and figures','Prepare simple table headers/cells and a limited set of reviewed MathML equations and figure descriptions. Flag unsupported content.'],
['Dataset and extraction evaluation','Maintain legally usable examples and reference annotations. Measure OCR errors, reading-order errors, STEM failures and review effort.']
],
'output':'A document-processing module that returns structured textbook blocks, source geometry, quality flags and explicit review states.',
'tools':'Python, pdfplumber, Pillow/OpenCV, Tesseract English/Hindi, Docling and a shared JSON schema.',
'example':'If OCR changes a minus sign or mixes two columns, Person 1 develops the extraction checks and content operations needed to detect or repair the problem.',
'handoff':'Send structured content and provenance to Person 3. Supply page geometry and reviewed content to Person 2. Person 2 owns correction forms; Person 3 owns authorization, persistence and revision transactions.'
},
{
'title':'Accessible reader, speech and offline experience',
'purpose':'Person 2 is responsible for everything a student directly uses. This person turns the extracted content into an accessible reading experience, with independent controls for different needs and reliable access to downloaded chapters.',
'rows':[
['Reader interface and navigation','Build a responsive reader with headings, page/paragraph navigation, bookmarks, reading-position recovery and an optional source view.'],
['Accessibility and preferences','Support keyboard and screen-reader operation, reflow and magnification. Provide independent text, spacing, contrast, focus, voice and speed controls.'],
['Speech and synchronization','Build the speech adapter, split text into suitable sentence units, synchronize sentence highlighting and maintain pronunciation overrides.'],
['Review and evidence interaction','Show uncertainty reasons, provide labeled correction forms, open supporting passages and let students return to the answer without losing context.'],
['Offline reading','Implement explicit chapter downloads, local text/audio caching, offline search/bookmarks and restart/resume behavior. Show missing content clearly.'],
['Accessibility and usability evaluation','Test keyboard, NVDA, TalkBack, zoom/reflow, narration and student tasks. Coordinate consent-based formative sessions where feasible.']
],
'output':'A usable student-facing reader that can find, present, narrate, review, download and resume a prepared chapter.',
'tools':'React, TypeScript, semantic HTML/CSS, PDF.js, a speech adapter, IndexedDB/Cache Storage and Playwright, alongside manual accessibility checks.',
'example':'A blind student opens a cited paragraph using keyboard navigation, listens to a sentence, downloads the chapter and resumes after restarting without internet.',
'handoff':'Consume Person 3\'s versioned APIs and Person 1\'s structured content. Person 2 owns speech generation and sentence segmentation; Person 3 schedules speech jobs and stores the generated files.'
},
{
'title':'Backend, revision consistency and grounded AI',
'purpose':'Person 3 is responsible for the application services and data integrity. This person connects extraction and reading, keeps every output aligned with the correct content revision, and implements answers that can be checked against the textbook.',
'rows':[
['APIs and access control','Build upload, status, content, correction, question and deletion endpoints. Validate inputs and restrict access to authorized documents and assets.'],
['Storage and processing jobs','Manage the database, private source/derived files, job status, retries and processing failures. Integrate extraction and speech adapters.'],
['Corrections and version control','Record edits, check their base revision and handle conflicts. Mark affected audio, search chunks, embeddings and answers stale, then rebuild them.'],
['Retrieval and grounded answers','Search only the selected authorized chapter. Return evidence passages and optional generated explanations with source-block references.'],
['Citation checks and abstention','Validate citation identifiers and revisions. Refuse or qualify answers when evidence is missing, unreliable or outdated; evaluate claim support separately.'],
['Operations and evaluation','Manage deployment, usage limits, cost tracking, retention and deletion. Test authorization, job recovery, version consistency and answer grounding.']
],
'output':'A reliable backend that stores and serves authorized content, propagates corrections and returns evidence-linked answers or clear abstentions.',
'tools':'Python/FastAPI, SQLite, private file storage, a durable worker, chapter search, optional local embeddings and a hosted LLM adapter.',
'example':'After a passage is corrected, Person 3 ensures an old audio file or answer cannot appear current, rebuilds affected outputs and checks new citations against the accepted revision.',
'handoff':'Integrate Person 1\'s extraction output and Person 2\'s speech component. Publish consistent chapter manifests and evidence responses for the reader. Extraction and interface implementation stay with their respective owners.'
}
]
for i,r in enumerate(role_data,1):
    page(f'ROLE {i} / PERSON {i}',r['title'])
    heading('Main purpose');para(r['purpose'])
    heading('Responsibilities explained')
    table(['Area','What this person does'],r['rows'],[.29,.71])
    heading('Main deliverable');para(r['output'])
    heading('Suggested tools');story.append(p(r['tools'],'small'))
    heading('Example contribution');para(r['example'])
    heading('Working with the other members');para(r['handoff'])

page('TEAMWORK / SHARED RESPONSIBILITIES','How the three roles connect')
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
heading('Correction and synchronization rule')
para('Edits include the revision on which they were made. Conflicting edits require reconciliation. Accepted changes invalidate dependent audio, index chunks and answers; outdated outputs cannot be presented as current. A failed rebuild must leave an explicit state and a usable text fallback.')

heading('Shared quality responsibilities')
para('Person 1 leads extraction and STEM accuracy checks. Person 2 leads accessibility and usability checks. Person 3 leads backend integrity and answer-grounding checks. Each member fixes failures in their own components, documents their method and limitations, and participates in the integrated demonstration.')
para('The complete system should let a student find a section, read or listen, inspect evidence, correct an extraction error and resume a downloaded chapter. Show unsupported content and unavailable services honestly. The team is responsible for the complete workflow, even though each subsystem has a named owner.')

def footer(c,doc):
    c.saveState();c.setFillColor(TEAL);c.rect(45,804,28,3,fill=1,stroke=0);c.setFillColor(MUTED);c.setFont('Bold',8);c.drawString(82,803,'PATHYA / PROJECT IDEA AND THREE-PERSON ROLE PLAN')
    c.setStrokeColor(LINE);c.line(45,37,550,37);c.setFont('Body',8);c.drawString(45,24,'Project idea | Three clearly defined roles');c.drawRightString(550,24,f'{doc.page} / 5');c.restoreState()
pdf=OUT/'Pathya_Project_Idea_and_Three_Person_Roles.pdf'
doc=SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=54,bottomMargin=48,title='Pathya - Project Idea and Three-Person Roles',author='Pathya project planning',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
r=PdfReader(pdf);assert len(r.pages)==5,len(r.pages)
text='\n'.join(page.extract_text() for page in r.pages)
assert all(f'PERSON {i}' in text for i in (1,2,3))
assert not re.search(r'\b(weeks?|hours?|schedule)\b',text,re.I)
assert '\ufffd' not in text
print(json.dumps({'file':str(pdf),'pages':len(r.pages),'bytes':pdf.stat().st_size,'words':len(text.split())},indent=2))
