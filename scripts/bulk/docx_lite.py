# -*- coding: utf-8 -*-
"""A small .docx writer: headings, paragraphs with bold/italic runs, bullets, tables, portrait and
landscape sections. Stdlib only (a .docx is a zip of XML), so the memo needs no new dependency.

    d = Doc('Title')
    d.heading('Section', 1); d.para([('bold ', 'b'), ('plain', '')]); d.bullet('text')
    d.table(['A', 'B'], [['1', '2']], widths_in=[1.5, 3]); d.landscape(); d.save('out.docx')
"""
import re, struct, zipfile
from xml.sax.saxutils import escape

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
PORTRAIT = (12240, 15840)            # US Letter, twentieths of a point
MARGIN = 1080                        # 0.75 in


def _t(text):
    return f'<w:t xml:space="preserve">{escape(str(text))}</w:t>'


def runs_from_md(text):
    """'plain **bold** plain' -> [(text, 'b' or '')]."""
    out = []
    for i, part in enumerate(re.split(r'\*\*(.+?)\*\*', text or '')):
        if part:
            out.append((part, 'b' if i % 2 else ''))
    return out


class Doc:
    def __init__(self, title=''):
        self.body, self.title = [], title
        self.orient = 'portrait'
        self.images = []                 # (zip name, bytes)

    def _run(self, text, fmt='', size=None, color=None):
        rpr = ''.join(['<w:b/>' if 'b' in fmt else '', '<w:i/>' if 'i' in fmt else '',
                       f'<w:color w:val="{color}"/>' if color else '', f'<w:sz w:val="{size}"/>' if size else ''])
        return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}{_t(text)}</w:r>'

    def _p(self, runs, style=None, extra_ppr='', size=None, color=None):
        if isinstance(runs, str):
            runs = runs_from_md(runs)
        ppr = (f'<w:pStyle w:val="{style}"/>' if style else '') + extra_ppr
        return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{"".join(self._run(t, f, size, color) for t, f in runs)}</w:p>'

    def heading(self, text, level=1):
        self.body.append(self._p([(text, '')], f'Heading{level}'))

    def title_block(self, title, subtitle=''):
        self.body.append(self._p([(title, '')], 'Title'))
        if subtitle:
            self.body.append(self._p([(subtitle, 'i')], color='595959'))

    def para(self, runs, size=None, color=None, italic=False):
        if italic and isinstance(runs, str):
            runs = [(t, (f + 'i')) for t, f in runs_from_md(runs)]
        self.body.append(self._p(runs, size=size, color=color))

    def bullet(self, runs, level=0):
        self.body.append(self._p(runs, extra_ppr=f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="1"/></w:numPr>'))

    def table(self, header, rows, widths_in, size=16, shade_col=None, shade_cells=None, rule_rows=None):
        """size in half-points (16 = 8 pt). shade_col: {row_index: 'RRGGBB'} to shade whole rows; shade_cells:
        {(row_index, col_index): 'RRGGBB'} for single cells; rule_rows: row indices that get a heavy rule above them
        (to separate groups of rows, e.g. one site from the next)."""
        tw = [int(w * 1440) for w in widths_in]
        grid = ''.join(f'<w:gridCol w:w="{w}"/>' for w in tw)
        rule_rows = set(rule_rows or ())

        def cell(text, w, hdr=False, fill=None, rule=False):
            shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill or ("D9E2F3" if hdr else "FFFFFF")}"/>'
            shd = ('<w:tcBorders><w:top w:val="single" w:sz="18" w:space="0" w:color="404040"/></w:tcBorders>' if rule else '') + shd
            paras = str('' if text is None else text).split('\n')
            ps = ''.join(self._p([(t, 'b')] if hdr else runs_from_md(t), size=size, extra_ppr='<w:spacing w:before="0" w:after="0"/>') for t in paras)
            return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}</w:tcPr>{ps}</w:tc>'
        trs = [f'<w:tr><w:trPr><w:tblHeader/></w:trPr>{"".join(cell(h, w, True) for h, w in zip(header, tw))}</w:tr>']
        for i, r in enumerate(rows):
            fill = (shade_col or {}).get(i)
            trs.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>' + ''.join(cell(v, w, fill=(shade_cells or {}).get((i, j), fill), rule=i in rule_rows)
                                                                        for j, (v, w) in enumerate(zip(r, tw))) + '</w:tr>')
        self.body.append(f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{sum(tw)}" w:type="dxa"/>'
                         f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')
        self.body.append(self._p([('', '')]))

    def banner(self, runs, fill, bar, size=24):
        """A full-width shaded line with a thick coloured bar at the left (colour-coded status headers)."""
        ppr = (f'<w:keepNext/><w:pBdr><w:left w:val="single" w:sz="48" w:space="6" w:color="{bar}"/></w:pBdr>'
               f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/><w:spacing w:before="0" w:after="80"/>')
        self.body.append(self._p(runs, extra_ppr=ppr, size=size))

    def image(self, path, width_in, caption=None, px=None):
        """An inline PNG or JPEG scaled to width_in, with an optional italic caption under it.
        px = (width, height) in pixels; read from the PNG header when omitted."""
        data = open(path, 'rb').read()
        ext = 'jpg' if path.lower().endswith(('.jpg', '.jpeg')) else 'png'
        w_px, h_px = px or struct.unpack('>II', data[16:24])     # PNG IHDR
        n = len(self.images) + 1
        rid = f'rIdImg{n}'
        self.images.append((f'media/image{n}.{ext}', data))
        cx = int(width_in * 914400); cy = int(cx * h_px / w_px)
        self.body.append(
            f'<w:p><w:pPr><w:spacing w:before="0" w:after="40"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{n}" name="Picture {n}"/>'
            f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{n}" name="image{n}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        if caption:
            self.body.append(self._p([(caption, 'i')], size=16, color='595959'))

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def _sect(self, orient):
        w, h = PORTRAIT if orient == 'portrait' else PORTRAIT[::-1]
        o = '' if orient == 'portrait' else ' w:orient="landscape"'
        return (f'<w:sectPr><w:pgSz w:w="{w}" w:h="{h}"{o}/><w:pgMar w:top="{MARGIN}" w:right="{MARGIN}" w:bottom="{MARGIN}" '
                f'w:left="{MARGIN}" w:header="540" w:footer="540" w:gutter="0"/></w:sectPr>')

    def landscape(self):
        """End the current section; what follows is landscape."""
        self.body.append(f'<w:p><w:pPr>{self._sect(self.orient)}</w:pPr></w:p>')
        self.orient = 'landscape'

    def portrait(self):
        self.body.append(f'<w:p><w:pPr>{self._sect(self.orient)}</w:pPr></w:p>')
        self.orient = 'portrait'

    def usable_width_in(self):
        w = PORTRAIT[0] if self.orient == 'portrait' else PORTRAIT[1]
        return (w - 2 * MARGIN) / 1440

    def save(self, path):
        doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>'
               f'{"".join(self.body)}{self._sect(self.orient)}</w:body></w:document>')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', CONTENT_TYPES)
            z.writestr('_rels/.rels', RELS)
            img_rels = ''.join(f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{name}"/>'
                               for i, (name, _) in enumerate(self.images, 1))
            z.writestr('word/_rels/document.xml.rels', DOC_RELS.replace('</Relationships>', img_rels + '</Relationships>'))
            for name, data in self.images:
                z.writestr(f'word/{name}', data)
            z.writestr('word/document.xml', doc)
            z.writestr('word/styles.xml', STYLES)
            z.writestr('word/numbering.xml', NUMBERING)
            z.writestr('docProps/core.xml', CORE.format(title=escape(self.title)))


CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Default Extension="png" ContentType="image/png"/>'
                 '<Default Extension="jpg" ContentType="image/jpeg"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                 '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                 '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '</Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            '</Relationships>')
CORE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:creator>TBDI bulk pipeline</dc:creator></cp:coreProperties>')
STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="1F3864"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="1F3864"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="23"/><w:color w:val="2F5496"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/><w:left w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/><w:right w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/></w:tblBorders>
<w:tblCellMar><w:top w:w="30" w:type="dxa"/><w:left w:w="70" w:type="dxa"/><w:bottom w:w="30" w:type="dxa"/><w:right w:w="70" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>'''
NUMBERING = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0">
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="240"/></w:pPr></w:lvl>
<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8211;"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="240"/></w:pPr></w:lvl>
</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'''
