"""分阶段生成本地比赛材料：先HTML，确认后导PDF；不发布、不注册。"""
from pathlib import Path
from html import escape
import argparse
import json
import sys
import xml.etree.ElementTree as ET
import shutil
import hashlib
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.submission import build_html, build_pdf

DOCS = [('data_ai_statement.md', '04_数据与AI使用说明'), ('90天验证计划.md', '05_90天验证计划')]


def prepare(output):
    import markdown
    output.mkdir(parents=True, exist_ok=False)
    statement = output / '01_项目说明'
    statement.mkdir()
    build_html(ROOT, statement)
    for source, name in DOCS:
        content = (ROOT / 'docs' / source).read_text(encoding='utf-8-sig')
        (output / (name + '.md')).write_text(content, encoding='utf-8')
        body = markdown.markdown(content, extensions=['tables', 'fenced_code'])
        page = '<html lang="zh-CN"><head><meta charset="utf-8"/><title>' + escape(name[3:]) + '</title><style>body{max-width:180mm;margin:20mm auto;font:11pt/1.65 "Microsoft YaHei",sans-serif;color:#173e42}h1{font-size:24pt}h2{font-size:15pt;margin-top:7mm}table{border-collapse:collapse;width:100%;font-size:9pt}td,th{padding:2.5mm;border-bottom:1px solid #d6e4df;vertical-align:top}th{background:#e9f3ed}a{color:#216f67}code{overflow-wrap:anywhere}footer{margin-top:10mm;font-size:9pt;color:#597579}@page{size:A4;margin:17mm}</style></head><body>' + body + '<footer>梅雨有数 · 2026-10-18 · 本地提交准备版</footer></body></html>'
        ET.fromstring(page)
        (output / (name + '.html')).write_text(page, encoding='utf-8')
    print('HTML与Markdown已生成，结构解析通过；确认后执行PDF阶段。')


def render_document(html_path, font):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    pdfmetrics.registerFont(TTFont('CompetitionCN', str(font)))
    styles = {name: ParagraphStyle(name, fontName='CompetitionCN', fontSize=size, leading=leading,
                                  textColor=colors.HexColor('#173e42'), wordWrap='CJK', spaceAfter=space,
                                  keepWithNext=name in {'h1', 'h2', 'h3'})
              for name, size, leading, space in [('p',10,16,7),('h1',23,30,16),('h2',14,21,9),('h3',11,18,7),('cell',8.7,13.5,0)]}
    document = ET.fromstring(html_path.read_text(encoding='utf-8'))
    title = document.find('./head/title').text
    story = []

    def inline(element):
        parts = [escape(element.text or '')]
        for child in element:
            value = inline(child)
            if child.tag == 'a':
                value = '<link href="' + escape(child.attrib['href'], quote=True) + '" color="#216f67">' + value + '</link>'
            elif child.tag in {'strong', 'b'}:
                value = '<b>' + value + '</b>'
            parts.extend([value, escape(child.tail or '')])
        return ''.join(parts)

    for element in document.find('body'):
        if element.tag in styles:
            story.append(Paragraph(inline(element), styles[element.tag]))
        elif element.tag in {'ul', 'ol'}:
            for item in element:
                story.append(Paragraph(inline(item), styles['p'], bulletText='-'))
        elif element.tag == 'table':
            rows = [[Paragraph(inline(cell), styles['cell']) for cell in row] for row in element.findall('.//tr')]
            cols = len(rows[0])
            fractions = [0.27,0.36,0.37] if cols == 3 else [1/cols] * cols
            table = Table(rows, colWidths=[174*mm*f for f in fractions], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f3ed')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#d6e4df')),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.extend([table, Spacer(1,10)])
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d6e4df'))
        canvas.line(18*mm,15*mm,192*mm,15*mm)
        canvas.setFont('CompetitionCN',8)
        canvas.setFillColor(colors.HexColor('#597579'))
        canvas.drawString(18*mm,10*mm,'梅雨有数 · '+title+' · 2026-10-18')
        canvas.drawRightString(192*mm,10*mm,str(doc.page))
    pdf = html_path.with_suffix('.pdf')
    SimpleDocTemplate(str(pdf),pagesize=(210*mm,297*mm),leftMargin=18*mm,rightMargin=18*mm,
                      topMargin=17*mm,bottomMargin=22*mm,title=title,author='梅雨有数').build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    return {'file': pdf.name, 'pages':len(reader.pages), 'characters':sum(len(p.extract_text() or '') for p in reader.pages)}


def package(output, release):
    from src.package import build_package, _iter_allowed_files
    if not release.is_relative_to(ROOT / 'dist') or release == ROOT / 'dist':
        raise ValueError('提交目录必须位于工程dist下')
    if release.exists() or release.with_suffix('.zip').exists():
        raise ValueError('提交输出已存在，请改用新的--release目录')
    baseline = json.loads((ROOT.parent / 'handoff_manifest.json').read_text(encoding='utf-8'))
    for path, expected in baseline['frozen_sha256'].items():
        if hashlib.sha256((ROOT.parent / path).read_bytes()).hexdigest() != expected:
            raise ValueError('冻结摘要不一致：' + path)
    video = ROOT / 'media/demo.mp4'
    if hashlib.sha256(video.read_bytes()).hexdigest() != '085c0ea556b42fad0c3939ca27c217e7b534aeddeff255eb35a37cabc9fe3504':
        raise ValueError('影片版本变化，需重新确认技术检查及人工验收')
    release.mkdir(parents=True)
    def copy(source, relative):
        target = release / relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    # 只有完成HTML/PDF逐页检查后才执行此阶段。
    for name in ['参赛项目说明.md','参赛项目说明.html','参赛项目说明.pdf','演示页面.png']:
        source = output/'01_项目说明'/name
        target = ROOT/'docs'/name
        try:
            if target.read_bytes() != source.read_bytes():
                shutil.copyfile(source, target)
        except PermissionError:
            if name != '参赛项目说明.pdf': raise
            shutil.copyfile(source, ROOT/'docs/参赛项目说明_20261018.pdf')
        copy(output/'01_项目说明'/name, '可编辑源稿/项目说明/'+name)
    for _, name in DOCS:
        for suffix in ['.md','.html']:
            copy(output/(name+suffix), '可编辑源稿/'+name+suffix)
        copy(output/(name+'.pdf'), name+'.pdf')
        shutil.copyfile(output/(name+'.pdf'), ROOT/'docs'/(name[3:]+'.pdf'))
    copy(ROOT/'templates/submission/00_提交前检查.md', '00_提交前检查.md')
    copy(output/'01_项目说明/参赛项目说明.pdf','01_项目说明.pdf')
    copy(video, '02_演示视频.mp4')
    copy(ROOT/'demo.html','03_可运行成果/demo.html')
    instructions = '# 可运行成果\n\n双击demo.html可离线体验历史案例。打开页面不请求天气，点击更新才访问公开接口。完整工程.zip含源码、原始公开数据和冻结结果；解压后读meiyu/README.md。\n\n这些都是本地文件，本轮未发布；不是报名表所需的公开网址。后续需用团队授权的托管或仓库提供评委可访问链接。不要把本地路径或127.0.0.1填作公共链接。\n'
    (release/'03_可运行成果/使用说明.md').write_text(instructions,encoding='utf-8')
    for name in ['报名填写草稿.md','三分钟答辩讲稿.md','十分钟问答演练.md','演示与答辩事实卡.md','视频人工验收表.md','赛事要求核对_20261018.md']:
        copy(ROOT/'docs'/name, '补充材料/'+name)
    copy(ROOT/'dist/梅雨有数_用户测试执行包_20261016.zip','补充材料/用户测试执行包.zip')
    engine = release/'03_可运行成果/完整工程.zip'
    snapshot = output/'工程快照'
    snapshot.mkdir(exist_ok=False)
    source_files,_ = _iter_allowed_files(ROOT)
    for source in source_files:
        target=snapshot/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    # 交付快照使用已核验的完整候选稿，原目录旧PDF即使被占用也不影响版本一致。
    for name in ['参赛项目说明.md','参赛项目说明.html','参赛项目说明.pdf','演示页面.png']:
        shutil.copyfile(output/'01_项目说明'/name,snapshot/'docs'/name)
    built = build_package(snapshot, engine)
    with zipfile.ZipFile(engine) as z:
        if z.testzip() is not None: raise ValueError('工程CRC错误')
        manifest = json.loads(z.read('meiyu/reports/package_manifest.json'))
        if set(z.namelist()) != {'meiyu/'+e['path'] for e in manifest['files']}: raise ValueError('工程范围错误')
        for e in manifest['files']:
            content=z.read('meiyu/'+e['path'])
            if content != (snapshot/e['path']).read_bytes() or len(content) != e['bytes']: raise ValueError('工程字节错误')
            if not e.get('self_manifest') and hashlib.sha256(content).hexdigest()!=e['sha256']: raise ValueError('工程摘要错误')
        for name,expected in baseline['frozen_sha256'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=expected: raise ValueError('包内冻结不一致')
    entries=[]
    for p in sorted(release.rglob('*')):
        if p.is_file(): entries.append({'path':p.relative_to(release).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest={'built_at_utc':datetime.now(timezone.utc).isoformat(),'status':'本地提交准备版；身份与网址留空；未公开未提交','files':entries,'hash_policy':'清单不自哈希，ZIP摘要另存。'}
    (release/'文件清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=release.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(release.rglob('*')):
            if p.is_file(): z.write(p,(Path(release.name)/p.relative_to(release)).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('提交包CRC错误')
        for e in entries:
            if hashlib.sha256(z.read(release.name+'/'+e['path'])).hexdigest()!=e['sha256']: raise ValueError('提交包摘要错误')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    report={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest,'file_count':len(entries)+1,'engine_files':built['file_count'],'frozen':6,'crc':'passed','manifest_matches_source':True,'video_unchanged':True,'public_upload':False,'registration':False,'actual_user_test':False}
    (ROOT/'reports/internal/比赛提交材料核验_20261018.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['html','pdf','package'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/simhei.ttf'))
    parser.add_argument('--release', type=Path, default=ROOT/'dist/梅雨有数_比赛提交材料_20261018')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'build') or output == ROOT / 'build':
        parser.error('只允许工程build下的独立候选目录')
    if args.phase == 'html':
        prepare(output)
    elif args.phase == 'pdf':
        if not output.is_dir():
            parser.error('请先生成并检查HTML')
        build_pdf(output / '01_项目说明', args.font)
        reports = [render_document(output / (name + '.html'), args.font) for _, name in DOCS]
        (output / 'PDF页数核验.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(reports,ensure_ascii=False))
    else:
        package(output,args.release.resolve())


if __name__ == '__main__':
    main()
