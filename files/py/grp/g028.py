# -*- coding: utf-8 -*-
"""
高清仓库（gqck 系：gqck.cc / gqck.net / gqck.tv）· TVBox Python 插件
=====================================================================
【站情 · 2026-10-02 实地探站】
  标准 MacCMS（stui 主题），服务端直出 HTML。**无盾、无登录墙、无会员墙**，直连 200。

【域池 · 这家的玩法（必须动态）】
  入口域（gqck.cc / gqck.net / gqck.tv / www.gqck.net）**只对根路径 / 做 301/302**，
  每次跳到一个随机子域（实测三次各不相同：gqck.cc→vxlzd6、gqck.net→h2z0r3、gqck.tv→k118fw）。
  而**内容全在子域上**：入口域带路径去请求（哪怕 /vodtype/8/）直接 404。
  另外实测：入口域在部分网络里**完全连不上**（对入口域 IP 的 HTTP/HTTPS 全超时），
  子域却是直连可用、长期有效 —— 所以自举顺序定为「已知活口池 → 入口域跟随跳转」。

【链路（实测）】
  首页  /gqck.html                          ← 根路径 / 只是 js 跳转壳
  分类  /vodtype/<id>/                     第 N 页 = /vodtype/<id>-<N>/
  播放  /vodplay/<id>-<sid>-<nid>/         页内 player_aaaa 直接给明文 m3u8
  搜索  /vodsearch/<词>----------<N>---.html
  卡片  a.stui-vodlist__thumb[href|title|data-original] + span.pic-text（时长），每页 40 张

【取流结论 · 有加密但不用破】
  player_aaaa：encrypt=0 / trysee=0 / points=0 —— 没有会员墙、没有试看、没有 DRM。
  m3u8 是标准 HLS，分片走 AES-128（#EXT-X-KEY，key 在**相对路径** key.key，IV 全 0）。
  实测：key 裸拉 200（16 字节 ASCII）、分片裸拉 200（video/mp2t）、都不需要 Referer；
  AES-128-CBC(key, IV=0) 解出的分片首字节 0x47、188 字节对齐 20/20 命中 —— 是真 TS。
  做法：清单里把 key 与分片的**相对 URI 绝对化后包回本机中继**，播放器按标准 HLS 自行解密。
  （相对 URI 是这类站最常见的坑：播放器按清单所在域去拼，拼错就整片黑。）

【纯标准库】无第三方依赖，按手机壳真实条件写。
自检: python3 高清仓库-TVBox插件.py
"""

import gzip
import json
import re
import threading
import time
import urllib.parse
import urllib.request

try:                                              # TVBox 壳内基类
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):                        # 原生 python 下自检用
        def init(self, *a, **kw):
            return self

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except Exception:
    BaseHTTPRequestHandler = None
    ThreadingHTTPServer = None

# ---------------------------------------------------------------- 常量
SITE_NAME = '高清仓库'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

# 入口域：站方的跳转服务器（只对根路径跳）
ENTRY = ['https://gqck.cc', 'https://gqck.net', 'https://gqck.tv', 'https://www.gqck.net']
# 已知活口子域池：实测见过且验证可用（随机分配但共享同一套后端，长期有效）
POOL = ['https://o4hwka.gqck.net', 'https://vxlzd6.gqck.net', 'https://h2z0r3.gqck.net',
        'https://k118fw.gqck.net', 'https://xdd3f2.gqck.net', 'https://l3myuj.gqck.net',
        'https://u9syd6.gqck.net', 'https://6ger9s.gqck.net', 'https://on7jwi.gqck.net']

P_CAT = '/vodtype/'
P_PLAY = '/vodplay/'
P_SEARCH = '/vodsearch/'
P_HOME = '/gqck.html'

CLASSES = [('日韩AV', '1'), ('国产系列', '2'), ('欧美', '3'), ('动漫', '4'),
           ('无码中文字幕', '8'), ('有码中文字幕', '9'), ('日本无码', '10'), ('日本有码', '7'),
           ('国产视频', '15'), ('吃瓜爆料', '25'), ('欧美高清', '21'), ('动漫剧情', '22')]

PAGE_SIZE = 40
LIVE_TTL = 30 * 60
PAGE_TTL = 2 * 60 * 60

_LIVE = {'base': '', 'at': 0.0}
_LOCK = threading.Lock()


def _host_of(url):
    try:
        p = urllib.parse.urlsplit(url)
        return '%s://%s' % (p.scheme, p.netloc) if p.scheme and p.netloc else ''
    except Exception:
        return ''


def _http(url, timeout=15, ref='', binary=False):
    """纯标准库取页；自动解 gzip。binary=True 返回 bytes。"""
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    req.add_header('Accept', 'text/html,application/xhtml+xml,*/*;q=0.8')
    req.add_header('Accept-Language', 'zh-CN,zh;q=0.9,en;q=0.8')
    if ref:
        req.add_header('Referer', ref)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw if binary else raw.decode('utf-8', 'replace')


def _follow(entry, timeout=5):
    """跟随 301/302 拿落点 host。★入口域只对根路径跳，必须打根路径。"""
    url = entry.rstrip('/') + '/'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', UA)
        req.add_header('Accept', 'text/html,*/*;q=0.8')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _host_of(r.geturl())
    except Exception:
        return ''


def _alive(base):
    """真出卡片才算活，光回 200 不算。"""
    try:
        t = _http(base.rstrip('/') + P_CAT + '8/', timeout=8, ref=base.rstrip('/') + '/')
        return len(t) > 3000 and ('stui-vodlist' in t or P_PLAY in t)
    except Exception:
        return False


def _probe():
    """活口池优先（快、直连可用）→ 入口域跟随跳转（站方整批换子域时靠它跟上）"""
    with _LOCK:
        now = time.time()
        if now - _LIVE['at'] < LIVE_TTL:
            return _LIVE['base']
        if _LIVE['base'] and _alive(_LIVE['base']):
            _LIVE['at'] = now
            return _LIVE['base']
        for h in POOL:
            if _alive(h):
                _LIVE['base'] = h
                _LIVE['at'] = now
                return h
        for e in ENTRY:
            landed = _follow(e)
            if landed and _alive(landed):
                _LIVE['base'] = landed
                _LIVE['at'] = now
                return landed
        _LIVE['at'] = now
        return _LIVE['base']


def _ent(s):
    """解码实体。★这站标题大量用 &#x…; 数字实体，标准 html.unescape 之外再兜一层。"""
    if not s:
        return ''
    t = str(s)
    t = t.replace('\\/', '/').replace('&amp;', '&').replace('&quot;', '"') \
         .replace('&#39;', "'").replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    if '&#' not in t:
        return t

    def _one(m):
        body = m.group(1)
        try:
            cp = int(body[1:], 16) if body[:1] in ('x', 'X') else int(body)
            return chr(cp) if 0 < cp <= 0x10FFFF else m.group(0)
        except Exception:
            return m.group(0)

    return re.sub(r'&#([xX]?[0-9A-Fa-f]{1,7});', _one, t)


_CARD_A = re.compile(r'<a[^>]+class="stui-vodlist__thumb[^"]*"([^>]*)>', re.I)
_DUR = re.compile(r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([^<]{1,24})</span>', re.I)


def _attr(attrs, key):
    m = re.search(key + r'\s*=\s*"([^"]*)"', attrs or '')
    return m.group(1).strip() if m else ''


def _cards(html, base):
    out, seen = [], set()
    if not html or len(html) < 500:
        return out
    for m in _CARD_A.finditer(html):
        a = m.group(1)
        href = _attr(a, 'href')
        if P_PLAY not in href or href in seen:
            continue
        seen.add(href)
        title = _ent(_attr(a, 'title')) or href
        pic = _attr(a, 'data-original')
        if pic.startswith('//'):
            pic = 'https:' + pic
        dm = _DUR.search(html[m.end():m.end() + 400])
        out.append({
            'vod_id': base + href,
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': _ent(dm.group(1)) if dm else '高清',
        })
    return out


# ---------------------------------------------------------------- 本机中继
class _Relay(object):
    """清单改写 / 分片转发 / key 转发 / 封面转发。

    为什么非要有这一层：
      · m3u8 里 key 与分片是**相对路径**，播放器按清单域去拼容易拼错 → 一律绝对化后回本机；
      · 壳的图片加载器不带我们的 UA/Referer，直连常常不出图；
      · 分片要带上与清单一致的 Referer。
    """

    def __init__(self):
        self.httpd = None
        self.port = 0
        self.thread = None
        self.base = ''

    def ensure(self):
        if self.httpd is not None:
            return self.port
        if ThreadingHTTPServer is None:
            return 0
        relay = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self._serve(False)

            def do_HEAD(self):
                self._serve(True)

            def _serve(self, head):
                try:
                    q = urllib.parse.urlsplit(self.path)
                    qs = urllib.parse.parse_qs(q.query)
                    kind = (qs.get('t', [''])[0] or '').strip()
                    src = urllib.parse.unquote(qs.get('u', [''])[0] or '').strip()
                    ref = urllib.parse.unquote(qs.get('r', [''])[0] or '').strip()
                    if kind == 'hls':
                        body, mime = relay._hls(src, ref), 'application/vnd.apple.mpegurl'
                    elif kind == 'seg':
                        body, mime = _http(src, timeout=35, ref=ref, binary=True), 'video/mp2t'
                    elif kind == 'key':
                        body, mime = _http(src, timeout=25, ref=ref, binary=True), 'application/octet-stream'
                    elif kind == 'img':
                        body, mime = _http(src, timeout=18, ref=ref, binary=True), 'image/jpeg'
                    else:
                        body, mime = b'bad type', 'text/plain'
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    if not head:
                        self.wfile.write(body)
                except Exception as e:
                    try:
                        msg = ('relay err %s' % str(e)[:80]).encode()
                        self.send_response(502)
                        self.send_header('Content-Type', 'text/plain')
                        self.send_header('Content-Length', str(len(msg)))
                        self.end_headers()
                        if not head:
                            self.wfile.write(msg)
                    except Exception:
                        pass

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.port

    def stop(self):
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        self.port = 0

    def url(self, kind, src, ref=''):
        p = self.ensure()
        if not p:
            return src
        return 'http://127.0.0.1:%d/proxy?t=%s&u=%s&r=%s' % (
            p, kind, urllib.parse.quote(src, safe=''), urllib.parse.quote(ref or '', safe=''))

    def _hls(self, src, ref):
        text = _http(src, timeout=25, ref=ref)
        if '#EXTM3U' not in text:
            raise Exception('m3u8 fail')
        out = []
        for line in text.split('\n'):
            t = line.strip()
            if not t:
                out.append(line)
            elif t[:1] != '#':
                out.append(self.url('hls' if ('.m3u8' in t.lower() or '.txt' in t.lower()) else 'seg',
                                    urllib.parse.urljoin(src, t), ref))
            elif t.startswith('#EXT-X-KEY') or t.startswith('#EXT-X-MAP'):
                out.append(self._fix_uri(line, src, ref))
            else:
                out.append(line)
        return '\n'.join(out).encode('utf-8')

    def _fix_uri(self, line, base, ref):
        """★关键一步：把 #EXT-X-KEY / #EXT-X-MAP 里的相对 URI 绝对化并包回中继"""
        m = re.search(r'URI="([^"]+)"', line)
        if not m:
            return line
        uri = m.group(1)
        if uri.startswith('http'):
            return line
        absu = urllib.parse.urljoin(base, uri)
        kind = 'key' if 'key' in absu.lower() else 'seg'
        return line[:m.start(1)] + self.url(kind, absu, ref) + line[m.end(1):]


# ---------------------------------------------------------------- 蜘蛛
class Spider(_Spider):

    def __init__(self, *args, **kwargs):
        self.host = ''
        self.relay = _Relay()
        self._cache = {}

    # ---------- 生命周期 ----------
    def init(self, extend=''):
        ext = (extend or '').strip()
        h = ''
        if ext.startswith('{'):
            try:
                h = str(json.loads(ext).get('host', '') or '')
            except Exception:
                h = ''
        elif ext.startswith('http'):
            h = ext
        if h:
            if not h.startswith('http'):
                h = 'https://' + h
            hh = _host_of(h)
            # 配置里填入口域（gqck.cc 这类）不算内容域 —— 走自举，别钉死
            if hh and hh not in [_host_of(e) for e in ENTRY]:
                self.host = hh
        return self

    def getName(self):
        return SITE_NAME

    def destroy(self):
        self._cache.clear()
        self.relay.stop()

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u or '.ts' in u

    def manualVideoCheck(self):
        return False

    # ---------- 基础 ----------
    def _base(self):
        if self.host:
            return self.host
        b = _probe()
        if b:
            self.host = b
            return b
        return POOL[0] if POOL else ENTRY[0]

    def _get(self, path, ref=None):
        url = path if path.startswith('http') else self._base().rstrip('/') + path
        now = time.time()
        hit = self._cache.get(url)
        if hit and now - hit[0] < PAGE_TTL:
            return hit[1]
        t = ''
        try:
            t = _http(url, timeout=20, ref=ref or (self._base().rstrip('/') + '/'))
        except Exception:
            t = ''
        if t and len(t) > 1500:
            self._cache[url] = (now, t)
        return t

    # ---------- 首页 / 分类 ----------
    def homeContent(self, filter=False):
        return {
            'class': [{'type_name': n, 'type_id': i} for n, i in CLASSES],
            'list': _cards(self._get(P_HOME), self._base()),
        }

    def homeVideoContent(self):
        return {'list': _cards(self._get(P_HOME), self._base())}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(str(pg or '1').strip()))
        except Exception:
            page = 1
        cid = str(tid or '').strip() or CLASSES[0][1]
        # ⚠️ 第 N 页是 /vodtype/<id>-<N>/，不是 <id>/<id>-<N>/
        path = P_CAT + cid + '/' if page <= 1 else P_CAT + cid + '-%d/' % page
        lst = _cards(self._get(path), self._base())
        more = len(lst) >= PAGE_SIZE
        return {
            'page': page,
            'pagecount': page + 1 if more else page,
            'limit': len(lst),
            'total': 999999 if more else len(lst),
            'list': lst,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        target = str(ids[0]).strip() if ids else ''
        if target and not target.startswith('http'):
            target = self._base().rstrip('/') + ('/' + target.lstrip('/'))
        html = self._get(target, ref=self._base().rstrip('/') + '/')
        base = self._base()

        blob = ''
        i = html.find('player_aaaa')
        if i >= 0:
            s = html.find('{', i)
            if s >= 0:
                depth, j, instr, esc = 0, s, False, False
                while j < len(html):
                    c = html[j]
                    if instr:
                        if esc:
                            esc = False
                        elif c == '\\':
                            esc = True
                        elif c == '"':
                            instr = False
                    else:
                        if c == '"':
                            instr = True
                        elif c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                blob = html[s:j + 1]
                                break
                    j += 1

        name = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            name = _ent(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        if not name:
            m = re.search(r'property="og:title" content="([^"]*)"', html)
            name = _ent(m.group(1)).strip() if m else ''
        if not name:
            name = SITE_NAME

        pic = ''
        m = re.search(r'property="og:image" content="([^"]*)"', html)
        if m:
            pic = m.group(1)
        if pic.startswith('//'):
            pic = 'https:' + pic

        info = []
        for label, pat in (('类型', r'类型：\s*([^<]{1,40})'), ('地区', r'地区：\s*([^<]{1,30})'),
                           ('年份', r'年份：\s*([^<]{1,20})'), ('更新', r'更新：\s*([0-9\-]{6,14})')):
            mm = re.search(pat, html)
            if mm:
                info.append('%s：%s' % (label, _ent(mm.group(1)).strip()))

        actors = []
        for am in re.finditer(r'<a[^>]+href="/vodsearch/[^"]*"[^>]*>([^<]{1,30})</a>', html):
            a = _ent(am.group(1)).strip()
            if a and a not in actors:
                actors.append(a)
            if len(actors) >= 8:
                break

        desc = ''
        m = re.search(r'name="description" content="([^"]*)"', html)
        if m:
            desc = _ent(m.group(1)).strip()

        # 线路
        eps, names, seen = [], [], set()
        for pm in re.finditer(r'/vodplay/(\d+)-(\d+)-(\d+)/', html):
            k = pm.group(2) + '-' + pm.group(3)
            if k in seen:
                continue
            seen.add(k)
            eps.append(base + '/vodplay/%s-%s-%s/' % (pm.group(1), pm.group(2), pm.group(3)))
            names.append(('线路 %s · 第 %s 集' % (pm.group(2), pm.group(3)))
                         if int(pm.group(2)) > 1 else ('第 %s 集' % pm.group(3)))
        if not eps:
            eps, names = [target], ['播放']

        play_url = '#'.join(['%s$%s' % (names[i], eps[i]) for i in range(len(eps))])
        content = ('【站源】高清仓库 · 免登录直取（站内 player_aaaa 明文出流，没有会员墙这一步）\n'
                   '【取流】页面内联明文 m3u8；分片走标准 HLS AES-128，清单与密钥经本机中继转写\n')
        if info:
            content += '【信息】' + ' · '.join(info) + '\n'
        if actors:
            content += '【主演】' + ' / '.join(actors) + '\n'
        if desc:
            content += '【简介】' + desc
        if blob:
            try:
                content += '\n【线路标记】' + str(json.loads(blob).get('from', ''))
            except Exception:
                pass

        return {'list': [{
            'vod_id': target,
            'vod_name': name,
            'vod_pic': self.relay.url('img', pic, base + '/') if pic.startswith('http') else pic,
            'vod_remarks': '%d 条线路' % len(eps) if len(eps) > 1 else '在线',
            'vod_content': content,
            'vod_play_from': SITE_NAME,
            'vod_play_url': play_url,
        }]}

    # ---------- 取流 ----------
    def playerContent(self, flag, vid, vipFlags=None):
        page = str(vid or '').strip()
        if page.startswith('folder@'):
            page = page[7:]
        if page and not page.startswith('http'):
            page = self._base().rstrip('/') + ('/' + page.lstrip('/'))
        if '.m3u8' in page:
            return {'parse': 0, 'playUrl': '', 'url': self.relay.url('hls', page, page),
                    'header': json.dumps({'User-Agent': UA})}

        html = self._get(page, ref=self._base().rstrip('/') + '/')
        src = ''
        i = html.find('player_aaaa')
        if i >= 0:
            m = re.search(r'"url"\s*:\s*"(https?:[^"]+?\.m3u8[^"]*)"', html[i:i + 4000])
            if m:
                src = m.group(1).replace('\\/', '/')
        if not src:
            m = re.search(r'"url"\s*:\s*"(https?:[^"]+?\.m3u8[^"]*)"', html)
            if m:
                src = m.group(1).replace('\\/', '/')
        url = self.relay.url('hls', src, page) if src else page
        return {'parse': 0, 'playUrl': '', 'url': url,
                'header': json.dumps({'User-Agent': UA})}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg='1'):
        kw = (key or '').strip()
        if not kw:
            return {'list': []}
        try:
            page = max(1, int(str(pg or '1').strip()))
        except Exception:
            page = 1
        tail = '----------1---.html' if page <= 1 else '----------%d---.html' % page
        url = self._base().rstrip('/') + P_SEARCH + urllib.parse.quote(kw) + tail
        lst = _cards(self._get(url), self._base())
        more = len(lst) >= PAGE_SIZE
        return {'page': page, 'pagecount': page + 1 if more else page,
                'limit': len(lst), 'total': len(lst), 'list': lst}

    # ---------- 自检 ----------
    def check(self):
        line = ['%s · 线路 %s' % (SITE_NAME, self._base())]
        try:
            h = self.homeContent(True)
            line.append('home 分类 %d / 首页 %d' % (len(h['class']), len(h.get('list') or [])))
            c = self.categoryContent('8', '1', False, {})
            line.append('cat 8 p1 → %d 条' % len(c.get('list') or []))
            c2 = self.categoryContent('8', '2', False, {})
            d = c.get('list') or []
            d2 = c2.get('list') or []
            line.append('cat 8 p2 → %d 条%s' % (len(d2), '(换内容)' if (d and d2 and d[0]['vod_id'] != d2[0]['vod_id']) else ''))
            s = self.searchContent('巨乳', True)
            line.append('search 巨乳 → %d 条' % len(s.get('list') or []))
            if not d:
                return ' | '.join(line) + ' | 分类空，停'
            first = d[0]
            line.append('首条《%s》' % str(first['vod_name'])[:18])
            det = (self.detailContent([first['vod_id']]).get('list') or [{}])[0]
            play = (det.get('vod_play_url') or '').split('#')[0].split('$')[-1]
            line.append('detail → %s' % (play or '空')[:50])
            p = self.playerContent('', first['vod_id'])
            line.append('player → %s' % str(p.get('url') or '空')[:50])
            # 真拉清单（走中继改写，必须看到标准 HLS 与 #EXTM3U）
            raw = ''
            m = re.search(r'u=([^&]+)', p.get('url') or '')
            if m:
                raw = urllib.parse.unquote(m.group(1))
            if raw:
                txt = _http(raw, timeout=25, ref=play)
                line.append('清单实拉 %d 字节 %s' % (len(txt), '#EXTM3U OK' if '#EXTM3U' in txt else '无 #EXTM3U'))
                m2 = re.search(r'#EXT-X-KEY[^\n]*URI="([^"]+)"', txt)
                if m2:
                    keyu = urllib.parse.urljoin(raw, m2.group(1))
                    kb = _http(keyu, timeout=20, ref=play, binary=True)
                    line.append('key 实拉 %d 字节' % len(kb))
                segs = [l.strip() for l in txt.split('\n') if l.strip() and not l.startswith('#')]
                if segs:
                    sb = _http(urllib.parse.urljoin(raw, segs[0]), timeout=30, ref=play, binary=True)
                    head = sb[0] if sb else 0
                    line.append('分片实拉 %d 字节' % len(sb))
                    if kb if m2 else False:
                        try:
                            from Crypto.Cipher import AES            # 有就顺手解一片验证
                            dec = AES.new(kb[:16], AES.MODE_CBC, b'\x00' * 16).decrypt(sb[:len(sb) - len(sb) % 16])
                            hit = sum(1 for i in range(0, min(len(dec), 188 * 20), 188) if dec[i] == 0x47)
                            line.append('AES 解片 首字节 0x%02x 188对齐 %d/20' % (dec[0], hit))
                        except ImportError:
                            line.append('AES 解片 跳过(无 pycryptodome，头字节 0x%02x)' % head)
                        except Exception as e:
                            line.append('AES 解片 异常 %s' % str(e)[:40])
            else:
                line.append('清单地址 解析失败')
        except Exception as e:
            line.append('自检异常 %s' % str(e)[:140])
        return ' | '.join(line)


if __name__ == '__main__':
    print(Spider().init().check())
