#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2epub.py —— 零依赖 Markdown → EPUB 3 转换器

针对电子墨水屏（Kindle + KOReader）优化的特性：
  * 按 H2 切章，H3 作为二级目录
  * 表格压缩排版（宽表不溢出）、代码块自动换行
  * 生成 EPUB3 nav + EPUB2 NCX 双目录，兼容老阅读器
  * 中文段落自动合并换行，不引入多余空格

用法: python md2epub.py input.md output.epub ["作者"]
"""
import sys, os, re, html, uuid, zipfile, datetime

# ---------- 内联渲染 ----------
def esc(t):
    return html.escape(t, quote=False)

def inline(t):
    s = esc(t)
    # 行内代码优先（内容不再解析）
    s = re.sub(r'`([^`]+)`', lambda m: '<code>%s</code>' % m.group(1), s)
    # 链接
    def _link(m):
        url = m.group(2).replace('"', '%22').replace('<', '%3C').replace('>', '%3E')
        return '<a href="%s">%s</a>' % (url, m.group(1))
    s = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', _link, s)
    # 粗体
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    # 斜体
    s = re.sub(r'(?<!\*)\*(?!\s)([^*]+?)(?<!\s)\*(?!\*)', r'<em>\1</em>', s)
    # 删除线
    s = re.sub(r'~~(.+?)~~', r'<del>\1</del>', s)
    return s

def is_cjk(ch):
    o = ord(ch)
    return 0x3000 <= o <= 0x303F or 0x4E00 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF

def join_lines(parts):
    out = ''
    for p in parts:
        if out and is_cjk(out[-1]) and p and is_cjk(p[0]):
            out += p
        elif out:
            out += ' ' + p
        else:
            out = p
    return out

# ---------- 块解析 ----------
def split_row(row):
    row = row.strip()
    if row.startswith('|'): row = row[1:]
    if row.endswith('|'): row = row[:-1]
    return [c.strip() for c in row.split('|')]

def parse_align(sep):
    cells = split_row(sep)
    al = []
    for c in cells:
        left = c.startswith(':'); right = c.endswith(':')
        if left and right: al.append('center')
        elif right: al.append('right')
        else: al.append('')
    return al

def parse_blocks(text):
    lines = text.splitlines()
    n = len(lines); i = 0; blocks = []
    while i < n:
        raw = lines[i]; s = raw.strip()
        if not s:
            i += 1; continue
        # 围栏代码
        m = re.match(r'^(```+|~~~+)\s*(\S*)\s*$', s)
        if m:
            fence = m.group(1)[0] * 3; lang = m.group(2); i += 1; buf = []
            while i < n and not lines[i].strip().startswith(fence):
                buf.append(lines[i]); i += 1
            i += 1
            blocks.append({'t': 'code', 'lang': lang, 'text': '\n'.join(buf)})
            continue
        # 标题
        m = re.match(r'^(#{1,6})\s+(.*?)\s*#*\s*$', s)
        if m:
            blocks.append({'t': 'h', 'level': len(m.group(1)), 'text': m.group(2)})
            i += 1; continue
        # 分隔线
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
            blocks.append({'t': 'hr'}); i += 1; continue
        # 表格
        if s.startswith('|') and i + 1 < n and re.match(r'^\|[\s:|-]+\|$', lines[i+1].strip()):
            header = split_row(s); align = parse_align(lines[i+1].strip()); i += 2; rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append(split_row(lines[i].strip())); i += 1
            blocks.append({'t': 'table', 'header': header, 'align': align, 'rows': rows})
            continue
        # 引用块
        if s.startswith('>'):
            buf = []
            while i < n and lines[i].strip().startswith('>'):
                buf.append(re.sub(r'^\s*>\s?', '', lines[i])); i += 1
            blocks.append({'t': 'quote', 'text': join_lines([b.strip() for b in buf if b.strip()])})
            continue
        # 列表
        if re.match(r'^(\s*)([-*+]|\d+\.)\s+', raw):
            items = []
            while i < n and re.match(r'^(\s*)([-*+]|\d+\.)\s+', lines[i]):
                m2 = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', lines[i])
                indent = len(m2.group(1).replace('\t', '    '))
                items.append({'indent': indent, 'ordered': m2.group(2)[0].isdigit(), 'text': m2.group(3).strip()})
                i += 1
                while (i < n and lines[i].strip() and
                       not re.match(r'^(\s*)([-*+]|\d+\.)\s+', lines[i]) and
                       not re.match(r'^#{1,6}\s', lines[i].strip()) and
                       not lines[i].strip().startswith(('|', '>', '```')) and
                       not re.match(r'^(-{3,}|\*{3,}|_{3,})$', lines[i].strip())):
                    items[-1]['text'] = join_lines([items[-1]['text'], lines[i].strip()])
                    i += 1
            if items:
                base = min(it['indent'] for it in items)
                for it in items:
                    d = it['indent'] - base
                    it['level'] = 0 if d < 2 else (1 if d < 4 else 2)
            blocks.append({'t': 'list', 'items': items})
            continue
        # 段落
        buf = [s]; i += 1
        while (i < n and lines[i].strip() and
               not re.match(r'^#{1,6}\s', lines[i].strip()) and
               not lines[i].strip().startswith(('|', '>', '```', '~~~')) and
               not re.match(r'^(\s*)([-*+]|\d+\.)\s+', lines[i]) and
               not re.match(r'^(-{3,}|\*{3,}|_{3,})$', lines[i].strip())):
            buf.append(lines[i].strip()); i += 1
        blocks.append({'t': 'p', 'text': join_lines(buf)})
    return blocks

# ---------- 渲染为 XHTML ----------
def render_blocks(blocks, h_offset=1):
    out = []
    for b in blocks:
        t = b['t']
        if t == 'h':
            lv = min(b['level'] + h_offset, 6)
            out.append('<h%d>%s</h%d>' % (lv, inline(b['text']), lv))
        elif t == 'p':
            out.append('<p>%s</p>' % inline(b['text']))
        elif t == 'hr':
            out.append('<hr/>')
        elif t == 'code':
            out.append('<pre><code>%s</code></pre>' % esc(b['text']))
        elif t == 'quote':
            out.append('<blockquote><p>%s</p></blockquote>' % inline(b['text']))
        elif t == 'list':
            out.append(render_list(b['items']))
        elif t == 'table':
            out.append(render_table(b))
    return '\n'.join(out)

def render_list(items):
    out = []; stack = []
    for it in items:
        while len(stack) > it['level']:
            out.append('</%s>' % stack.pop())
        if len(stack) <= it['level']:
            tag = 'ol' if it['ordered'] else 'ul'
            out.append('<%s>' % tag); stack.append(tag)
        out.append('<li>%s</li>' % inline(it['text']))
    while stack:
        out.append('</%s>' % stack.pop())
    return '\n'.join(out)

def render_table(b):
    out = ['<table>', '<thead><tr>']
    for idx, c in enumerate(b['header']):
        al = b['align'][idx] if idx < len(b['align']) else ''
        st = ' class="al-%s"' % al if al else ''
        out.append('<th%s>%s</th>' % (st, inline(c)))
    out.append('</tr></thead>')
    if b['rows']:
        out.append('<tbody>')
        for r in b['rows']:
            out.append('<tr>')
            for idx in range(len(b['header'])):
                c = r[idx] if idx < len(r) else ''
                al = b['align'][idx] if idx < len(b['align']) else ''
                st = ' class="al-%s"' % al if al else ''
                out.append('<td%s>%s</td>' % (st, inline(c)))
            out.append('</tr>')
        out.append('</tbody>')
    out.append('</table>')
    return '\n'.join(out)

# ---------- 模板 ----------
XHTML = ('<?xml version="1.0" encoding="utf-8"?>\n'
         '<!DOCTYPE html>\n'
         '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN" lang="zh-CN">\n'
         '<head><meta charset="utf-8"/><title>%s</title>'
         '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
         '<body>\n%s\n</body></html>\n')

CSS = """@charset "utf-8";
html, body { margin: 0; padding: 0; }
body {
  font-family: "Noto Serif CJK SC", "Source Han Serif SC", serif;
  line-height: 1.65;
  text-align: justify;
  word-wrap: break-word;
  padding: 0.3em 0.5em;
}
h1, h2, h3, h4 { line-height: 1.35; text-align: left; page-break-after: avoid; }
h1 { font-size: 1.35em; margin: 0.8em 0 0.5em; }
h2 { font-size: 1.18em; margin: 0.9em 0 0.45em; border-bottom: 1px solid #bbb; padding-bottom: 0.15em; }
h3 { font-size: 1.06em; margin: 0.8em 0 0.35em; }
h4 { font-size: 1.0em; margin: 0.7em 0 0.3em; }
p { margin: 0.42em 0; text-indent: 0; }
hr { border: 0; border-top: 1px solid #ccc; margin: 1em 0; }
blockquote {
  margin: 0.6em 0; padding: 0.35em 0.7em;
  border-left: 3px solid #999; background: #f6f6f6;
  font-size: 0.94em; color: #333;
}
blockquote p { margin: 0.25em 0; }
code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 0.88em; background: #f0f0f0; padding: 0 0.15em;
}
pre {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 0.78em; line-height: 1.4;
  background: #f4f4f4; border: 1px solid #ddd;
  padding: 0.45em 0.55em; margin: 0.6em 0;
  white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;
}
pre code { background: none; padding: 0; }
ul, ol { margin: 0.4em 0 0.4em 1.1em; padding: 0; }
li { margin: 0.22em 0; text-indent: 0; }
table {
  border-collapse: collapse; width: 100%;
  margin: 0.6em 0; font-size: 0.78em; line-height: 1.4;
  table-layout: fixed;
}
th, td {
  border: 1px solid #aaa; padding: 0.22em 0.3em;
  vertical-align: top; word-wrap: break-word; overflow-wrap: break-word;
  text-align: left; text-indent: 0;
}
th { background: #ececec; font-weight: bold; }
td.al-center, th.al-center { text-align: center; }
td.al-right, th.al-right { text-align: right; }
a { color: #0645ad; text-decoration: none; }
.title-page { text-align: center; margin-top: 22%; }
.title-page .t { font-size: 1.5em; font-weight: bold; line-height: 1.4; }
.title-page .m { font-size: 0.9em; color: #555; margin-top: 2em; }
"""

def build(md_path, out_path, author='本地生成'):
    text = open(md_path, encoding='utf-8').read()
    blocks = parse_blocks(text)
    # 书名 = 首个 H1
    title = os.path.splitext(os.path.basename(md_path))[0]
    body_blocks = []
    for idx, b in enumerate(blocks):
        if b['t'] == 'h' and b['level'] == 1 and idx == 0:
            title = b['text']; continue
        body_blocks.append(b)
    # 按 H2 切章
    chapters = []   # (title, blocks)
    cur = ('前言', [])
    for b in body_blocks:
        if b['t'] == 'h' and b['level'] == 2:
            if cur[1]: chapters.append(cur)
            cur = (b['text'], [])
        else:
            cur[1].append(b)
    if cur[1]: chapters.append(cur)
    if not chapters: chapters = [('正文', [])]

    files = []
    # 封面
    tp = ('<div class="title-page"><p class="t">%s</p>'
          '<p class="m">生成时间：%s<br/>MARKDOWN → EPUB（本地转换）</p></div>'
          % (esc(title), datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))
    files.append(('titlepage.xhtml', XHTML % ('封面', tp)))

    # 章节
    tocs = []          # (chap_href, chap_title, [(sub_href, sub_title)])
    for ci, (ct, cblocks) in enumerate(chapters, 1):
        href = 'chap%02d.xhtml' % ci
        hoff = 0
        parts = [ '<h1>%s</h1>' % inline(ct) ]
        subs = []
        si = 0
        for b in cblocks:
            if b['t'] == 'h' and b['level'] == 3:
                si += 1
                sid = 'sec%02d_%02d' % (ci, si)
                parts.append('<h2 id="%s">%s</h2>' % (sid, inline(b['text'])))
                subs.append(('sec%02d' % 0 + '', b['text'], sid))
            else:
                parts.append(render_blocks([b]))
        files.append((href, XHTML % (esc(ct), '\n'.join(parts))))
        tocs.append((href, ct, subs))

    # nav.xhtml
    nav = ['<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc" id="toc"><h1>目录</h1><ol>']
    for href, ct, subs in tocs:
        nav.append('<li><a href="%s">%s</a>' % (href, esc(ct)))
        real = [s for s in subs if s[2]]
        if real:
            nav.append('<ol>')
            for _, st, sid in real:
                nav.append('<li><a href="%s#%s">%s</a></li>' % (href, sid, esc(st)))
            nav.append('</ol>')
        nav.append('</li>')
    nav.append('</ol></nav>')
    navdoc = XHTML % ('目录', '\n'.join(nav).replace(
        '<nav ', '<nav ', 1))
    files.append(('nav.xhtml', navdoc))

    # toc.ncx (EPUB2 兼容)
    ncx = ['<?xml version="1.0" encoding="utf-8"?>',
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
           '<head><meta name="dtb:uid" content="urn:uuid:%s"/></head>' % uuid.uuid4(),
           '<docTitle><text>%s</text></docTitle>' % esc(title),
           '<navMap>']
    play = 1
    for href, ct, subs in tocs:
        ncx.append('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                   % (play, play, esc(ct), href)); play += 1
    ncx.append('</navMap></ncx>')
    files.append(('toc.ncx', '\n'.join(ncx)))

    files.append(('style.css', CSS))

    # content.opf
    uid = 'urn:uuid:%s' % uuid.uuid4()
    modified = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    man = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
           '<item id="css" href="style.css" media-type="text/css"/>']
    spine = []
    for i, (name, _) in enumerate(files):
        if not name.endswith('.xhtml'): continue
        iid = 'x%d' % i
        man.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (iid, name))
        spine.append('<itemref idref="%s"/>' % iid)
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="zh-CN">\n'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           '<dc:identifier id="bookid">%s</dc:identifier>\n'
           '<dc:title>%s</dc:title>\n<dc:language>zh-CN</dc:language>\n'
           '<dc:creator>%s</dc:creator>\n'
           '<meta property="dcterms:modified">%s</meta>\n'
           '</metadata>\n<manifest>\n%s\n</manifest>\n'
           '<spine toc="ncx">\n%s\n</spine>\n</package>\n'
           % (uid, esc(title), esc(author), modified, '\n'.join(man), '\n'.join(spine)))

    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
                 '</container>\n')

    with zipfile.ZipFile(out_path, 'w') as z:
        zi = zipfile.ZipInfo('mimetype'); zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, 'application/epub+zip')
        z.writestr('META-INF/container.xml', container, zipfile.ZIP_DEFLATED)
        z.writestr('OEBPS/content.opf', opf, zipfile.ZIP_DEFLATED)
        for name, data in files:
            z.writestr('OEBPS/' + name, data, zipfile.ZIP_DEFLATED)
    return title, len(chapters), sum(1 for b in blocks if b['t'] == 'table'), os.path.getsize(out_path)

if __name__ == '__main__':
    md = sys.argv[1]; out = sys.argv[2]
    author = sys.argv[3] if len(sys.argv) > 3 else '本地生成'
    t, nc, nt, size = build(md, out, author)
    print('OK title=%s chapters=%d tables=%d size=%d' % (t, nc, nt, size))
