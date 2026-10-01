#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_font.py —— 往 EPUB 内嵌裁剪后的字体，并注入 @font-face

设计要点
--------
* 只保留 EPUB 正文实际用到的字符（子集化），因此体积从 8MB 降到几百 KB。
* 自动改写 OPF 清单、在现有 CSS 末尾追加 @font-face 与字体族声明，
  对 pandoc / ebooklib / 内置引擎产出的 EPUB 一律通用。
* 只做加法：不改动正文 XHTML，不删原有样式；出问题可随时用原文件替换。

用法
----
  python embed_font.py 书.epub --regular 常规字重字体 --bold 粗体字体 [--family 名称]
"""
import sys, os, re, io, json, html, zipfile, argparse, posixpath

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'pylib'))
from fontTools import subset


def collect_text(z):
    """收集 EPUB 中可见文本的字符集"""
    buf = []
    for n in z.namelist():
        if n.endswith(('.xhtml', '.html', '.htm')):
            t = z.read(n).decode('utf-8', 'replace')
            t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', t)
            t = re.sub(r'<[^>]+>', ' ', t)
            buf.append(html.unescape(t))
    text = ''.join(buf)
    keep = set(text)
    keep.update('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    keep.update(' .,:;!?()[]{}<>/\\|_-+=*&^%$#@~`\'"“”‘’—…、。，；：？！（）《》【】')
    keep.update('①②③④⑤⑥⑦⑧⑨⑩→←↑↓≥≤≠≈±×÷℃％‰')
    return ''.join(sorted(c for c in keep if c.strip() or c == ' '))


def subset_font(src, text, dst):
    opts = subset.Options()
    opts.drop_tables += ['DSIG']
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.recalc_timestamp = False
    opts.name_IDs = ['*']
    opts.name_legacy = True
    opts.layout_features = ['*']
    font = subset.load_font(src, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=text)
    sub.subset(font)
    subset.save_font(font, dst, opts)
    return os.path.getsize(dst)


def find_opf(z):
    cont = z.read('META-INF/container.xml').decode('utf-8')
    m = re.search(r'full-path="([^"]+)"', cont)
    if not m:
        raise RuntimeError('container.xml 里找不到 rootfile')
    return m.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('epub')
    ap.add_argument('--regular', required=True)
    ap.add_argument('--bold')
    ap.add_argument('--family', default='KindleCN')
    ap.add_argument('--out')
    a = ap.parse_args()

    src_epub = a.epub
    out_epub = a.out or src_epub
    tmp = os.path.join(HERE, '.tmp')
    os.makedirs(tmp, exist_ok=True)

    z = zipfile.ZipFile(src_epub)
    names = z.namelist()
    opf_path = find_opf(z)
    opf_dir = posixpath.dirname(opf_path)
    opf = z.read(opf_path).decode('utf-8')

    text = collect_text(z)
    print('  用到字符数: %d' % len(text))

    f_reg = os.path.join(tmp, 'font-regular.otf')
    n1 = subset_font(a.regular, text, f_reg)
    print('  常规字重子集: %.1f KB' % (n1 / 1024))
    f_bold = None
    if a.bold:
        f_bold = os.path.join(tmp, 'font-bold.otf')
        n2 = subset_font(a.bold, text, f_bold)
        print('  粗体字重子集: %.1f KB' % (n2 / 1024))

    # 1) 追加 @font-face 到现有 CSS
    css_items = re.findall(r'<item\b[^>]*media-type="text/css"[^>]*>', opf)
    css_href = None
    m = re.search(r'href="([^"]+)"', css_items[0]) if css_items else None
    if m:
        css_href = m.group(1)
    if not css_href:
        css_href = 'style.css'
    css_full = posixpath.normpath(posixpath.join(opf_dir, css_href)) if opf_dir else css_href
    css_dir = posixpath.dirname(css_full)
    css_old = z.read(css_full).decode('utf-8') if css_full in names else ''

    font_dir = posixpath.join(opf_dir, 'fonts') if opf_dir else 'fonts'
    rel_css_to_font = posixpath.relpath(font_dir, css_dir or '.')
    reg_name = 'regular.otf'; bold_name = 'bold.otf'
    rules = ['', '/* ==== 内嵌字体（子集化，仅供本书使用）==== */']
    rules.append('@font-face { font-family: "%s"; font-weight: 400; font-style: normal; '
                 'src: url("%s/%s"); }' % (a.family, rel_css_to_font, reg_name))
    if f_bold:
        rules.append('@font-face { font-family: "%s"; font-weight: 700; font-style: normal; '
                     'src: url("%s/%s"); }' % (a.family, rel_css_to_font, bold_name))
    rules.append('body, p, li, td, th, blockquote, div, h1, h2, h3, h4, h5, h6 '
                 '{ font-family: "%s", sans-serif; }' % a.family)
    rules.append('code, pre { font-family: "DejaVu Sans Mono", monospace; }')
    css_new = css_old + '\n'.join(rules) + '\n'

    # 2) OPF 清单里登记字体
    add_items = ['<item id="embfont-reg" href="%s/%s" media-type="font/otf"/>'
                 % (posixpath.relpath(font_dir, opf_dir) if opf_dir else 'fonts', reg_name)]
    if f_bold:
        add_items.append('<item id="embfont-bold" href="%s/%s" media-type="font/otf"/>'
                         % (posixpath.relpath(font_dir, opf_dir) if opf_dir else 'fonts', bold_name))
    opf_new = opf.replace('</manifest>', '\n'.join(add_items) + '\n</manifest>')

    # 3) 重写 zip（mimetype 必须首个且不压缩）。先写临时文件再原子替换，避免原地重写把源文件截断
    tmp_out = out_epub + '.tmp'
    with zipfile.ZipFile(tmp_out, 'w') as zo:
        zi = zipfile.ZipInfo('mimetype'); zi.compress_type = zipfile.ZIP_STORED
        zo.writestr(zi, z.read('mimetype'))
        for n in names:
            if n == 'mimetype':
                continue
            if n == opf_path:
                data = opf_new.encode('utf-8')
            elif n == css_full:
                data = css_new.encode('utf-8')
            else:
                data = z.read(n)
            zo.writestr(n, data, zipfile.ZIP_DEFLATED)
        zo.write(f_reg, posixpath.join(font_dir, reg_name), zipfile.ZIP_DEFLATED)
        if f_bold:
            zo.write(f_bold, posixpath.join(font_dir, bold_name), zipfile.ZIP_DEFLATED)
    z.close()
    os.replace(tmp_out, out_epub)

    print('  内嵌完成: %s  (%.1f KB)' % (out_epub, os.path.getsize(out_epub) / 1024))
    print('  CSS: %s   字体目录: %s' % (css_full, font_dir))


if __name__ == '__main__':
    main()


