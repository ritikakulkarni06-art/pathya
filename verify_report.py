from pathlib import Path
import json,re
from pypdf import PdfReader
import pdfplumber
root=Path(__file__).parent
out=root/'output'/'pdf'
data=json.loads((out/'Pathya_Report_Source.json').read_text(encoding='utf-8'))
reader=PdfReader(out/'Pathya_AI_Textbook_Reader_Project_Report.pdf')
assert len(reader.pages)==25
assert len({p['part'] for p in data['pages']})==3
seen=set()
for pg in data['pages']:
    for typ,val in pg['items']:
        if typ=='ref':continue
        for match in re.findall(r'\[(\d+(?:[-,]\d+)*)\]',str(val)):
            for bit in match.split(','):
                if '-' in bit:
                    a,b=map(int,bit.split('-'));seen.update(range(a,b+1))
                else:seen.add(int(bit))
assert seen==set(range(1,64)),sorted(set(range(1,64))-seen)
html=(out/'Pathya_Report_Accessible_Companion.html').read_text(encoding='utf-8')
assert html.count('<h1 ')==3
for n in seen:assert f'id="ref{n}"' in html
issues=[]
with pdfplumber.open(out/'Pathya_AI_Textbook_Reader_Project_Report.pdf') as pdf:
    for n,p in enumerate(pdf.pages,1):
        for c in p.chars:
            if c['x0']<40 or c['x1']>556 or c['top']<15 or c['bottom']>824:
                issues.append((n,c['text'],c['x0'],c['top']))
assert not issues,issues[:10]
text='\n'.join(p.extract_text() for p in reader.pages)
assert '\ufffd' not in text
links=sum(len(p.get('/Annots',[])) for p in reader.pages)
assert links>200
checks={'pages':len(reader.pages),'main_parts':3,'references':len(data['references']),'all_references_cited':True,'pdf_link_annotations':links,'text_boundary_issues':issues,'word_count_including_references':len(text.split()),'bytes':(out/'Pathya_AI_Textbook_Reader_Project_Report.pdf').stat().st_size}
(out/'report_validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))
