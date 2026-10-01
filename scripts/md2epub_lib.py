#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2epub_lib.py —— markdown + ebooklib 转换引擎（依赖 pylib 下的第三方库）

用法: python md2epub_lib.py 输入1.md [输入2.md ...] -o 输出.epub [-t 书名] [-a 作者]
多个输入会合并成一本书，每章标题带上来源文件名。
"""
import sys, os, re, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'pylib'))

import markdown
from ebooklib import epub

MD_EXTS = ['tables', 'fenced_code', 'sane_lists', 'attr_list', 'md_in_html']

def load_css():
    p = os.path.join(HERE, 'eink.css')
    if os.path.exists(p):
        return open(p, encoding='utf-8').read()
    return ''

def parse_doc(text):
    """返回 (文档H1标题, [(章标题, 章正文 markdown)])"""
    lines = text.splitlines()
    title = None
    for i, l in enumerate(lines):
        m = re.match(r'^#\s+(.*)$', l)
        if m:
            title = m.group(1).strip()
            lines = lines[:i] + lines[i+1:]
            break
    chapters = []
    cur = None
    buf = []
    def flush():
        if cur is not None or any(x.strip() for x in buf):
            chapters.append((cur if cur else '前言', '\n'.join(buf)))
    for l in lines:
        m = re.match(r'^##\s+(.*)$', l)
        if m:
            flush()
            cur = m.group(1).strip(); buf = []
        else:
            buf.append(l)
    flush()
    return title, chapters

def md2html(text):
    md = markdown.Markdown(extensions=MD_EXTS)
    return md.convert(text)

def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def build(inputs, out_path, title=None, author='本地生成'):
    css = load_css()
    book = epub.EpubBook()
    book.set_identifier('urn:uuid:%s' % uuid.uuid4())
    book.set_language('zh-CN')
    book.add_author(author)
    style = epub.EpubItem(uid='style', file_name='style/eink.css',
                          media_type='text/css', content=css)
    book.add_item(style)

    chapters = []
    for path in inputs:
        text = open(path, encoding='utf-8').read()
        doc_title, chaps = parse_doc(text)
        if title is None and doc_title:
            title = doc_title
        for ct, body in chaps:
            chapters.append((ct, body, doc_title))

    if not title:
        title = os.path.splitext(os.path.basename(inputs[0]))[0]
    book.set_title(title)

    merge = len(inputs) > 1
    spine = ['nav']
    toc = []
    for i, (ct, body, doc_title) in enumerate(chapters, 1):
        disp = ('%s / %s' % (doc_title, ct)) if (merge and doc_title and ct != '前言') else ct
        item = epub.EpubHtml(title=disp, file_name='chap_%02d.xhtml' % i, lang='zh-CN')
        item.content = '<h1>%s</h1>\n%s' % (esc(disp), md2html(body))
        item.add_item(style)
        book.add_item(item)
        spine.append(item)
        toc.append(item)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    epub.write_epub(out_path, book)
    return title, len(chapters), os.path.getsize(out_path)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('-t', '--title')
    ap.add_argument('-a', '--author', default='本地生成')
    a = ap.parse_args()
    t, n, s = build(a.inputs, a.output, a.title, a.author)
    print('OK engine=lib title=%s chapters=%d size=%d' % (t, n, s))
