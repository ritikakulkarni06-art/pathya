from pathlib import Path

path=Path(__file__).with_name('build_roles_pdf.py')
s=path.read_text(encoding='utf-8')
start=s.index("page('01 / THE PRODUCT'")
end=s.index("page('05 / OWNERSHIP AND HANDOFFS'")
roles=r'''
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

'''
s=s[:start]+roles+s[end:]
s=s.replace("page('05 / OWNERSHIP AND HANDOFFS'","page('TEAMWORK / SHARED RESPONSIBILITIES'")
start=s.index("page('06 / DELIVERY SCHEDULE'")
end=s.index('def footer(c,doc):')
s=s[:start]+'''heading('Shared quality responsibilities')
para('Person 1 leads extraction and STEM accuracy checks. Person 2 leads accessibility and usability checks. Person 3 leads backend integrity and answer-grounding checks. Each member fixes failures in their own components, documents their method and limitations, and participates in the integrated demonstration.')
para('The complete system should let a student find a section, read or listen, inspect evidence, correct an extraction error and resume a downloaded chapter. Show unsupported content and unavailable services honestly. The team is responsible for the complete workflow, even though each subsystem has a named owner.')

'''+s[end:]
s=s.replace("'Proposed plan | 3 members | 14 weeks | 504 planned hours'","'Project idea | Three clearly defined roles'")
s=s.replace("f'{doc.page} / 8'","f'{doc.page} / 5'")
s=s.replace('assert len(r.pages)==8','assert len(r.pages)==5')
s=s.replace("assert text.count('168')>=4","assert not re.search(r'\\b(weeks?|hours?|schedule)\\b',text,re.I)")
path.write_text(s,encoding='utf-8')
print('Revised to project overview, three role pages and shared responsibilities.')
