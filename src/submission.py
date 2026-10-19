"""从四页排版源生成项目说明候选稿，不覆盖正式材料。"""
from pathlib import Path
from html import escape
import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET


def build_html(root: Path, output: Path):
    source = root / 'templates/submission'
    html = (source / '参赛项目说明.html').read_text(encoding='utf-8')
    document = ET.fromstring(html.split('\n', 1)[1])
    if len(document.findall('./body/section')) != 4:
        raise ValueError('排版源必须包含四个章节页。')
    markdown = ['# 梅雨有数：让降雨概率成为可解释的准备参考', '\n2026-10-19参赛材料。团队身份按实际信息填写；公开入口以README为准。']
    for section in document.findall('./body/section'):
        for element in section:
            text = ''.join(element.itertext())
            if element.tag in {'h1', 'h2'}:
                markdown.append('\n' + ('## ' if element.tag == 'h1' else '### ') + text)
            elif element.tag == 'table':
                rows = [[''.join(cell.itertext()) for cell in row] for row in element.findall('.//tr')]
                markdown.append('\n| ' + ' | '.join(rows[0]) + ' |\n| ' + ' | '.join(['---'] * len(rows[0])) + ' |\n' + '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows[1:]))
            elif element.tag in {'p', 'aside', 'small'}:
                markdown.append('\n' + text)
    (output / '参赛项目说明.html').write_text(html, encoding='utf-8')
    (output / '参赛项目说明.md').write_text('\n'.join(markdown) + '\n', encoding='utf-8')
    shutil.copyfile(source / '演示页面.png', output / '演示页面.png')


def build(root: Path, output: Path, with_pdf=False, font=None):
    root, output = root.resolve(), output.resolve()
    # 所有生成结果限于独立build子目录，保护源码、正式材料及冻结数据。
    if not output.is_relative_to(root / 'build') or output == root / 'build':
        raise ValueError('输出必须是工程 build/ 下的独立子目录。')
    if output.exists():
        raise ValueError('候选目录已存在，请选用新的版本目录。')
    if with_pdf and (font is None or not font.is_file()):
        raise ValueError('PDF需要可用中文TTF字体，请通过 --font 指定。')
    output.mkdir(parents=True)
    build_html(root, output)
    if with_pdf:
        build_pdf(output, font)
    files = [{'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.iterdir()) if p.is_file()]
    (output / '生成摘要.json').write_text(json.dumps({'source': 'templates/submission/参赛项目说明.html', 'files': files}, ensure_ascii=False, indent=2), encoding='utf-8')
    return output


def build_pdf(output: Path, font: Path):
    OUT = output
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    pdfmetrics.registerFont(TTFont('Hei', str(font)))
    styles = {name: ParagraphStyle(name, fontName='Hei', fontSize=size, leading=leading, textColor=colors.HexColor('#173e42'), wordWrap='CJK', spaceAfter=after, alignment=TA_LEFT) for name, size, leading, after in [('p',10.2,16,7),('small',8.4,12.8,6),('h1',24,31,15),('h2',14,21,9),('cell',9,13,0),('aside',9.5,14,7)]}
    document = ET.fromstring((OUT / '参赛项目说明.html').read_text(encoding='utf-8').split('\n',1)[1])
    story = []
    width = 174 * mm
    for page_index, section in enumerate(document.findall('./body/section')):
        if page_index:
            story.append(PageBreak())
        for element in section:
            text = escape(''.join(element.itertext()))
            if element.tag in styles:
                item = Paragraph(text, styles[element.tag])
                if element.tag == 'aside':
                    box = Table([[item]], colWidths=[width])
                    box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eff5f1')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#d6e4df')),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                    story.extend([KeepTogether([box]),Spacer(1,8)])
                else:
                    story.append(item)
            elif element.tag == 'table':
                rows = [[Paragraph(escape(''.join(cell.itertext())),styles['cell']) for cell in row] for row in element.findall('.//tr')]
                count = len(rows[0])
                fractions = [0.34,0.33,0.33] if count == 3 else [0.44,0.14,0.14,0.14,0.14]
                grid = Table(rows, colWidths=[width * fraction for fraction in fractions], repeatRows=1)
                grid.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f3ed')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#d6e4df')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
                story.extend([KeepTogether([grid]),Spacer(1,10)])
            elif element.tag == 'img':
                from PIL import Image as PILImage
                path = OUT / element.attrib['src']
                with PILImage.open(path) as picture:
                    ratio = picture.height / picture.width
                story.extend([Image(str(path),width=width,height=width*ratio),Spacer(1,7)])
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d6e4df'))
        canvas.line(18*mm,15*mm,192*mm,15*mm)
        canvas.setFont('Hei',8)
        canvas.setFillColor(colors.HexColor('#597579'))
        canvas.drawString(18*mm,10*mm,'梅雨有数 · 参赛材料 · 本地提交准备版')
        canvas.drawRightString(192*mm,10*mm,f'{doc.page} / 4')
    pdf = SimpleDocTemplate(str(OUT/'参赛项目说明.pdf'),pagesize=(210*mm,297*mm),leftMargin=18*mm,rightMargin=18*mm,topMargin=17*mm,bottomMargin=22*mm,title='梅雨有数：让降雨概率成为可解释的准备参考',author='梅雨有数')
    pdf.build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    reader = PdfReader(OUT/'参赛项目说明.pdf')
    assert len(reader.pages) == 4, f'实际页数{len(reader.pages)}，需调整排版'
    full_text = '\n'.join(page.extract_text() for page in reader.pages)
    for required in ['0.0455','636','240','85/273','六页','4月至9月','73.866666667']:
        assert required in full_text, required
    print('四页PDF生成；关键数字和产品描述提取核对通过。')



def main():
    parser = argparse.ArgumentParser(description='生成独立候选稿；不修改docs及其他材料')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True, help='工程build下尚不存在的子目录')
    parser.add_argument('--pdf', action='store_true')
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/simhei.ttf'))
    args = parser.parse_args()
    try:
        build(args.root, args.output, args.pdf, args.font)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'生成失败：{exc}\n')
    print('候选稿已生成；逐页检查后再同步正式材料。')


if __name__ == '__main__':
    main()
