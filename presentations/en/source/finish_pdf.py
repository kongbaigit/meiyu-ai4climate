from pathlib import Path
import sys
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link

pdf_path = Path(sys.argv[1]).resolve()
reader = PdfReader(pdf_path)
if len(reader.pages) != 10:
    raise ValueError('The English pitch PDF must contain 10 pages.')
writer = PdfWriter(clone_from=reader)
links = [
    ('https://kongbaigit.github.io/meiyu-ai4climate/en/',429),
    ('https://kongbaigit.github.io/meiyu-ai4climate/en/promo/',518),
    ('https://github.com/kongbaigit/meiyu-ai4climate',607),
]
for url, top in links:
    writer.add_annotation(page_number=9,annotation=Link(rect=(58.5,540-(top+43)*0.75,898.5,540-top*0.75),url=url))
writer.add_metadata({'/Title':'Meiyu Prepare: rainfall forecasts and stock relocation decisions','/Author':'Meiyu Prepare team'})
staging = pdf_path.with_suffix('.linked.pdf')
with staging.open('wb') as out:
    writer.write(out)
staging.replace(pdf_path)
verified = PdfReader(pdf_path)
targets = [a.get_object()['/A']['/URI'] for a in verified.pages[9].get('/Annots',[]) if a.get_object().get('/A')]
if not all(url in targets for url,_ in links):
    raise ValueError('The three closing-slide links did not persist.')
print(f'Checked 10 PDF pages and {len(links)} closing-slide links.')
