#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opds_server.py —— 本地 OPDS 书库服务器（KOReader 可通过 Wi-Fi 直接下载）

用法: python opds_server.py <书目录> [端口]
然后在 KOReader: 菜单 -> 云存储/OPDS -> 添加目录 -> http://<本机IP>:<端口>/opds
"""
import http.server, os, sys, html, socket, datetime, urllib.parse, uuid

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
PORT = int(sys.argv[2] if len(sys.argv) > 2 else 8080)
MEDIA = {'.epub': 'application/epub+zip', '.pdf': 'application/pdf',
         '.mobi': 'application/x-mobipocket-ebook', '.azw3': 'application/x-mobipocket-ebook',
         '.fb2': 'application/fb2+xml', '.txt': 'text/plain', '.cbz': 'application/vnd.comicbook+zip'}

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80)); return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        ua = '-'
        try:
            ua = (self.headers.get('User-Agent') or '-')[:70]
        except Exception:
            pass
        sys.stderr.write("[opds] %s | %s | %s\n" % (self.address_string(), ua, fmt % args))
        sys.stderr.flush()

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/opds', '/opds/', '/opds.xml'):
            data = self._feed().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/atom+xml; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            return
        return super().do_HEAD()
    def _send(self, ctype, body):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/opds', '/opds/', '/opds.xml'):
            return self._send('application/atom+xml; charset=utf-8', self._feed())
        if path == '/':
            host = self.headers.get('Host') or ('%s:%d' % (lan_ip(), PORT))
            items = []
            for name in sorted(os.listdir(ROOT)):
                fp = os.path.join(ROOT, name)
                if os.path.isfile(fp) and os.path.splitext(name)[1].lower() in MEDIA:
                    items.append('<li><a href="/%s">%s</a> <small>(%d KB)</small></li>'
                                 % (urllib.parse.quote(name), html.escape(name),
                                    os.path.getsize(fp) // 1024))
            page = ('<html><head><meta charset="utf-8"/><title>本地书库</title></head><body>'
                    '<h1>本地书库</h1>'
                    '<p>OPDS 目录（KOReader 用）：<code>http://%s/opds</code></p>'
                    '<ul>%s</ul></body></html>') % (host, ''.join(items) or '<li>(空)</li>')
            return self._send('text/html; charset=utf-8', page)
        return super().do_GET()

    def _feed(self):
        host = self.headers.get('Host') or ('%s:%d' % (lan_ip(), PORT))
        base = 'http://%s' % host
        now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        books = []
        for name in sorted(os.listdir(ROOT)):
            p = os.path.join(ROOT, name)
            if not os.path.isfile(p): continue
            mt = MEDIA.get(os.path.splitext(name)[1].lower())
            if not mt: continue
            books.append((name, mt, os.path.getsize(p),
                          datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
        out = ['<?xml version="1.0" encoding="utf-8"?>',
               '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">',
               '  <title>本地书库</title>',
               '  <id>urn:uuid:%s</id>' % uuid.uuid4(),
               '  <updated>%s</updated>' % now,
               '  <author><name>本地</name></author>']
        for name, mt, size, mtime in books:
            href = base + '/' + urllib.parse.quote(name)
            title = html.escape(os.path.splitext(name)[0])
            out += ['  <entry>',
                    '    <title>%s</title>' % title,
                    '    <id>urn:uuid:%s</id>' % uuid.uuid5(uuid.NAMESPACE_URL, href),
                    '    <updated>%s</updated>' % mtime,
                    '    <dc:language>zh-CN</dc:language>',
                    '    <link rel="http://opds-spec.org/acquisition" type="%s" href="%s"/>' % (mt, href),
                    '    <link rel="alternate" type="%s" href="%s"/>' % (mt, href),
                    '    <summary>%s (%d KB)</summary>' % (html.escape(name), size // 1024),
                    '  </entry>']
        out.append('</feed>')
        return '\n'.join(out)

class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == '__main__':
    ip = lan_ip()
    srv = Server(('0.0.0.0', PORT), Handler)
    print('OPDS 服务已启动')
    print('  目录: %s' % ROOT)
    print('  书数: %d' % len([n for n in os.listdir(ROOT) if os.path.splitext(n)[1].lower() in MEDIA]))
    print('  KOReader 里填: http://%s:%d/opds' % (ip, PORT))
    sys.stdout.flush()
    srv.serve_forever()



