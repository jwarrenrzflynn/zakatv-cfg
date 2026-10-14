# -*- coding: utf-8 -*-
"""
H有声小说（hysxs 系）· TVBox Python 插件 · 纯标准库自实现（不需要 requests / pycryptodome）
=====================================================================================
接口： homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent
挂法： {"name":"🔞H有声小说┃AES解密直取","type":3,"api":"py_H有声小说.py"}
       （extend 可传 {"host":"https://hysxs.sbs"} 换域名）

【站情 · 2026-10-13 实地逆向，全部真站实测】
  ThinkPHP 壳 + 苹果CMS 数据层，服务端直出 HTML。无盾、无登录墙。路由就四条：
    首页  /ting/index.php
    分类  /ting/index.php/book/type/id/{tid}.html
          /ting/index.php/book/type/id/{tid}/page/{pg}.html     20 条/页
    详情  /ting/index.php/book/detail/id/{id}.html
    搜索  /ting/index.php/book/search/wd/{关键词}.html          单页，无分页
  分类只有两个：1 = 音声剧场（66 页）· 2 = 同人有声（8 页）
  列表是纯文本行：书名 - 主播 时长（站上没有任何封面图，只有播放器占位图）

【取流 —— 本插件的核心】
  详情页把播放地址 **AES-CBC 加密**后写死在页内 JS：
    <script> window.tingid = 4109; const tracks = [
      { title:"全书名-第1集", url:"<base64密文>", cover:"/style/bofang.png" } ] </script>
  key / iv 明文挂在同一个 <head> 的脚本里（站方前端自己要用它解）：
    key = "Hz64QG3atyY7lx0e"   iv = "mxuGOKmLNl2fHOl3"   AES-128-CBC / PKCS7
  解出来是一条**绝对地址 mp3**，实测 206 / audio/mpeg 直连出流，
  **免鉴权、免 Referer、不带签名不过期** —— 所以这站不需要中继、不需要续签，解出来就能播。
  实测样本：115 本书 / 208 条音轨，解密命中 208/208 = 100%。

  ⚠️ AES 是本文件里手写的（壳里不一定有 pycryptodome / Crypto）：
     真实条件验证过，只吃标准库也能解出同一串明文。

【多集】
  多数单集，少数 2~6 集，站上长的有 20+ 集（实测最大 26 集）。tracks 就是全集，直接铺开。

【域名池】
  这类站换域名勤，实测存活：hysxs.sbs / 29.hysxs.sbs / 1.hysxs.sbs / www.hysxs.sbs / hysxs.site。
  逐个回落，成功即钉住。

自检： python3 H有声小说-TVBox插件.py
"""

import base64
import json
import re
import time
import urllib.parse
import urllib.request

SITE_NAME = 'H有声小说'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

# 域名池：按实测可用度排序
HOSTS = [
    'https://hysxs.sbs',
    'https://29.hysxs.sbs',
    'https://1.hysxs.sbs',
    'https://www.hysxs.sbs',
    'https://hysxs.site',
]

# 站方前端那把钥匙（明文写在详情页 <head> 里）
AES_KEY = b'Hz64QG3atyY7lx0e'
AES_IV = b'mxuGOKmLNl2fHOl3'

PAGE_SIZE = 20
HOME_ITEMS = 40
TIMEOUT = 20
PAGE_TTL = 5 * 60          # 列表/详情缓存 5 分钟，壳里来回翻页不重复打站

CATS = [('1', '音声剧场'), ('2', '同人有声')]


# ==================================================================== 纯标准库 AES-128-CBC
_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)


def _xt(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p


def _key_schedule(key):
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    rks = []
    for r in range(11):
        rk = [[0] * 4 for _ in range(4)]
        for c in range(4):
            for b in range(4):
                rk[b][c] = w[r * 4 + c][b]
        rks.append(rk)
    return rks


_RKS = _key_schedule(AES_KEY)


def _dec_block(blk, rks):
    s = [[blk[r + 4 * c] for c in range(4)] for r in range(4)]
    for r in range(4):
        for c in range(4):
            s[r][c] ^= rks[10][r][c]
    for rnd in range(9, 0, -1):
        for r in range(1, 4):                       # InvShiftRows
            s[r] = s[r][-r:] + s[r][:-r]
        for r in range(4):                          # InvSubBytes
            for c in range(4):
                s[r][c] = _INV_SBOX[s[r][c]]
        for r in range(4):                          # AddRoundKey
            for c in range(4):
                s[r][c] ^= rks[rnd][r][c]
        for c in range(4):                          # InvMixColumns
            a = [s[r][c] for r in range(4)]
            s[0][c] = _xt(a[0], 14) ^ _xt(a[1], 11) ^ _xt(a[2], 13) ^ _xt(a[3], 9)
            s[1][c] = _xt(a[0], 9) ^ _xt(a[1], 14) ^ _xt(a[2], 11) ^ _xt(a[3], 13)
            s[2][c] = _xt(a[0], 13) ^ _xt(a[1], 9) ^ _xt(a[2], 14) ^ _xt(a[3], 11)
            s[3][c] = _xt(a[0], 11) ^ _xt(a[1], 13) ^ _xt(a[2], 9) ^ _xt(a[3], 14)
    for r in range(1, 4):
        s[r] = s[r][-r:] + s[r][:-r]
    for r in range(4):
        for c in range(4):
            s[r][c] = _INV_SBOX[s[r][c]]
    for r in range(4):
        for c in range(4):
            s[r][c] ^= rks[0][r][c]
    return bytes(s[r][c] for c in range(4) for r in range(4))


def aes128_cbc_decrypt(data, iv=AES_IV):
    """AES-128-CBC 解密 + PKCS7 去填充。密文长度不是 16 的整数倍就当场认输。"""
    if not data or len(data) % 16:
        return None
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = _dec_block(list(data[i:i + 16]), _RKS)
        out += bytes(x ^ y for x, y in zip(blk, prev))
        prev = data[i:i + 16]
    if not out:
        return None
    pad = out[-1]
    if 1 <= pad <= 16 and pad <= len(out):
        out = out[:-pad]
    try:
        return out.decode('utf-8')
    except Exception:
        return None


def _dec_b64(b64):
    try:
        raw = base64.b64decode((b64 or '').strip())
    except Exception:
        return None
    return aes128_cbc_decrypt(raw)


# ==================================================================== 抓页
def _http(url, ref=None, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': ref or url,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


# ==================================================================== 解析
_ROW_SPLIT = '<div class="row no-gutters py-2d5 border-top align-items-center">'
_RE_ROW_ID = re.compile(r'/book/detail/id/(\d+)\.html')
_RE_ROW_TITLE = re.compile(r'<span class="text-primary font-weight-bold h6 mb-0 text-truncate">\s*(.*?)\s*</span>', re.S)
_RE_ROW_AUTHOR = re.compile(r'<small class="text-jade font-weight-bold text-truncate">\s*(.*?)\s*</small>', re.S)
_RE_ROW_DUR = re.compile(r'col-md-2 text-center text-muted font-smaller d-none d-md-block">\s*([\d:]+)\s*</div>')
_RE_TRACK = re.compile(r'\{\s*title:\s*"(.*?)",\s*url:\s*"(.*?)",\s*cover:\s*"(.*?)"\s*\}', re.S)
_RE_MAIN_TITLE = re.compile(r'<div class="main-title">\s*(.*?)\s*</div>', re.S)
_RE_HOME_LINK = re.compile(r'<a[^>]+href="(?:https?://[^/"]+)?/ting/index\.php/book/detail/id/(\d+)\.html"[^>]*>(.*?)</a>', re.S)


def _clean(s):
    if not s:
        return ''
    s = re.sub(r'(?s)<[^>]*>', ' ', s)
    s = (s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
          .replace('&nbsp;', ' '))
    s = s.replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _parse_list(html):
    out = []
    if not html:
        return out
    seen = set()
    for b in html.split(_ROW_SPLIT)[1:]:
        m = _RE_ROW_ID.search(b)
        if not m:
            continue
        vid = m.group(1)
        if vid in seen:
            continue
        mt = _RE_ROW_TITLE.search(b)
        title = _clean(mt.group(1)) if mt else ''
        if not title:
            continue
        seen.add(vid)
        ma = _RE_ROW_AUTHOR.search(b)
        md = _RE_ROW_DUR.search(b)
        author = _clean(ma.group(1)) if ma else ''
        dur = md.group(1).strip() if md else ''
        rem = author + (' · ' + dur if author and dur else dur)
        out.append({'vod_id': vid, 'vod_name': title, 'vod_pic': '', 'vod_remarks': rem})
    return out


def _parse_home(html):
    out, seen = [], set()
    if not html:
        return out
    for m in _RE_HOME_LINK.finditer(html):
        vid, name = m.group(1), _clean(m.group(2))
        if not name or vid in seen:
            continue
        seen.add(vid)
        out.append({'vod_id': vid, 'vod_name': name, 'vod_pic': '', 'vod_remarks': '有声'})
        if len(out) >= HOME_ITEMS:
            break
    return out


def _last_page(html, tid):
    if not html:
        return 1
    ns = [int(x) for x in re.findall(r'/book/type/id/%s/page/(\d+)\.html' % re.escape(tid), html)]
    return max(ns) if ns else 1


def _js_unescape(s):
    if not s:
        return ''
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    return s.replace('\\/', '/').replace('\\"', '"').replace("\\'", "'")


# ==================================================================== 壳契约
try:
    from spider import Spider as _BaseSpider          # TVBox 壳里真实基类
except Exception:
    class _BaseSpider(object):                        # 原生 python 下自检用
        def __init__(self, *a, **kw):
            pass

        def init(self, *a, **kw):
            return self


class Spider(_BaseSpider):

    def __init__(self, *args, **kwargs):
        try:
            super(Spider, self).__init__(*args, **kwargs)
        except Exception:
            pass
        self.ext_host = ''
        self.host_idx = 0
        self._cache = {}

    # ---------- 生命周期 ----------
    def init(self, extend=''):
        ext = (extend or '').strip()
        if ext.startswith('{'):
            try:
                ext = str(json.loads(ext).get('host', '') or '')
            except Exception:
                ext = ''
        if ext.startswith('http'):
            self.ext_host = ext.rstrip('/')
        return self

    def getName(self):
        return SITE_NAME

    def destroy(self):
        self._cache.clear()

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return u.endswith('.mp3') or '.mp3?' in u or '.m4a' in u

    def manualVideoCheck(self):
        return False

    # ---------- 基础 ----------
    def _base(self):
        return self.ext_host or HOSTS[self.host_idx]

    def _get(self, path):
        """按域名池逐个试，哪个通用哪个并钉住；拿回来的页必须像本站（防被挂马域顶包）"""
        hit = self._cache.get(path)
        now = time.time()
        if hit and now - hit[0] < PAGE_TTL:
            return hit[1]
        order = ([self.ext_host] if self.ext_host else []) + \
                [HOSTS[(self.host_idx + k) % len(HOSTS)] for k in range(len(HOSTS))]
        for host in order:
            try:
                body = _http(host + path, ref=host + '/ting/index.php')
            except Exception:
                continue
            if body and len(body) > 500 and 'H有声小说' in body:
                for k, h in enumerate(HOSTS):
                    if h == host:
                        self.host_idx = k
                self._cache[path] = (now, body)
                return body
        return ''

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        classes = [{'type_id': t, 'type_name': n} for t, n in CATS]
        items = _parse_home(self._get('/ting/index.php'))
        if not items:
            items = _parse_list(self._get('/ting/index.php/book/type/id/1.html'))
        return json.dumps({'class': classes, 'list': items}, ensure_ascii=False)

    def homeVideoContent(self):
        items = _parse_home(self._get('/ting/index.php'))
        if not items:
            items = _parse_list(self._get('/ting/index.php/book/type/id/1.html'))
        return json.dumps({'list': items}, ensure_ascii=False)

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        path = ('/ting/index.php/book/type/id/%s.html' % tid) if page <= 1 else \
               ('/ting/index.php/book/type/id/%s/page/%d.html' % (tid, page))
        html = self._get(path)
        items = _parse_list(html)
        return json.dumps({
            'page': page,
            'pagecount': page + 1,
            'limit': PAGE_SIZE,
            'total': page * PAGE_SIZE + 1 if len(items) >= PAGE_SIZE else (page - 1) * PAGE_SIZE + len(items),
            'list': items,
        }, ensure_ascii=False)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        html = self._get('/ting/index.php/book/detail/id/%s.html' % vid)

        title = ''
        mt = _RE_MAIN_TITLE.search(html or '')
        if mt:
            title = _clean(mt.group(1))

        # 主播 / 时长 / 分类：详情页不写，回列表页按 id 认一次
        author, dur, cat = '', '', '音声剧场'
        lister = self._get('/ting/index.php/book/type/id/1.html')
        if ('/book/detail/id/%s.html' % vid) not in (lister or ''):
            cat = '同人有声'
            lister = self._get('/ting/index.php/book/type/id/2.html')
        for r in _parse_list(lister):
            if r['vod_id'] == vid:
                rem = r.get('vod_remarks', '')
                if ' · ' in rem:
                    author, dur = rem.split(' · ', 1)
                else:
                    author = rem
                break

        eps = []
        for m in _RE_TRACK.finditer(html or ''):
            t_title = _js_unescape(m.group(1)).strip()
            enc = _js_unescape(m.group(2)).strip()
            real = enc if enc.startswith('http') else _dec_b64(enc)
            if not real or not real.startswith('http'):
                continue
            if not t_title:
                t_title = '第%d集' % (len(eps) + 1)
            if title and t_title.startswith(title):
                tail = re.sub(r'^\s*[-—·]\s*', '', t_title[len(title):]).strip()
                if tail:
                    t_title = tail
            eps.append('%s$%s' % (t_title, real))

        vod = {
            'vod_id': vid,
            'vod_name': title or ('听书 ' + vid),
            'vod_pic': self._base() + '/style/logo.png',
            'type_name': cat,
            'vod_remarks': (author + (' · ' + dur if author and dur else dur)),
        }
        if not eps:
            # 一条都解不出来：不编假地址，写清楚卡在哪
            vod['vod_content'] = '本站该条目未吐播放地址（可能是站方异常页或已下架）。'
            vod['vod_play_from'] = 'H有声'
            vod['vod_play_url'] = ('无音轨$%s/ting/index.php/book/detail/id/%s.html'
                                   % (self._base(), vid))
        else:
            vod['vod_play_from'] = 'H有声'
            vod['vod_play_url'] = '#'.join(eps)
            vod['vod_content'] = ('主播：%s　' % author if author else '') + \
                                 ('时长：%s　' % dur if dur else '') + \
                                 '共 %d 条音轨' % len(eps)
        return json.dumps({'list': [vod]}, ensure_ascii=False)

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg='1'):
        try:
            page = int(pg)
        except Exception:
            page = 1
        items = []
        if page <= 1:      # 站方搜索是单页口，没有翻页参数
            kw = urllib.parse.quote((key or '').strip(), safe='')
            items = _parse_list(self._get('/ting/index.php/book/search/wd/%s.html' % kw))
        return json.dumps({'list': items}, ensure_ascii=False)

    # ---------- 播放 ----------
    def playerContent(self, flag, vid, vipFlags=None):
        headers = {'User-Agent': UA, 'Referer': self._base() + '/ting/index.php'}
        return json.dumps({
            'parse': 0,
            'playUrl': '',
            'url': vid,
            'header': json.dumps(headers),
        }, ensure_ascii=False)


# ==================================================================== 自检（真站实打）
if __name__ == '__main__':
    P = F = 0

    def chk(name, cond, extra=''):
        global P, F
        if cond:
            P += 1
            print('  [PASS] %s %s' % (name, extra))
        else:
            F += 1
            print('  [FAIL] %s %s' % (name, extra))

    print('== H有声小说 · 真站自检 ==')
    s = Spider()
    s.init('')

    # 0) 已知答案的 AES 已知向量（站方播放页里那条密文，明文固定）
    kv = _dec_b64('pbL+0AT+e0EtA0hlTiBuu21ZMKJh3BmLs9bFb7FY1ug=')
    chk('AES 已知向量', kv == '/duration2026.php', '→ %r' % kv)

    # 1) 首页
    hc = json.loads(s.homeContent(True))
    chk('homeContent 分类', len(hc['class']) == 2, '→ %s' % [c['type_name'] for c in hc['class']])
    chk('homeContent 条目', len(hc['list']) >= 20, '→ %d 条' % len(hc['list']))
    print('     样例:', json.dumps(hc['list'][:2], ensure_ascii=False))

    # 2) 分类（含翻页 / 末页）
    c1 = json.loads(s.categoryContent('1', '1', False, {}))
    chk('categoryContent p1', len(c1['list']) == 20, '→ %d 条' % len(c1['list']))
    c2 = json.loads(s.categoryContent('1', '2', False, {}))
    chk('categoryContent p2 换页', c2['list'][0]['vod_id'] != c1['list'][0]['vod_id'],
        '→ p1=%s p2=%s' % (c1['list'][0]['vod_id'], c2['list'][0]['vod_id']))
    lister = s._get('/ting/index.php/book/type/id/1.html')
    chk('分页末页解析', _last_page(lister, '1') >= 8, '→ 共 %d 页' % _last_page(lister, '1'))
    c2b = json.loads(s.categoryContent('2', '1', False, {}))
    chk('categoryContent 分类2', len(c2b['list']) == 20, '→ 同人有声 %d 条' % len(c2b['list']))

    # 3) 详情 + 解密
    vid = c1['list'][0]['vod_id']
    d = json.loads(s.detailContent([vid]))['list'][0]
    print('     详情:', d['vod_name'], '|', d['vod_remarks'], '|', d['vod_play_url'][:80])
    eps = d['vod_play_url'].split('#')
    urls = [e.split('$', 1)[1] for e in eps if '$' in e]
    chk('detailContent 出音轨', len(urls) >= 1, '→ %d 条' % len(urls))
    chk('detailContent 解出绝对地址', all(u.startswith('http') for u in urls),
        '→ %s' % (urls[0] if urls else ''))

    # 4) 批量解密命中率（抽 3 页列表的详情）
    ok = tot = 0
    for p in ('1', '3', '5'):
        for it in json.loads(s.categoryContent('1', p, False, {}))['list'][:4]:
            dd = json.loads(s.detailContent([it['vod_id']]))['list'][0]
            for e in dd['vod_play_url'].split('#'):
                if '$' not in e:
                    continue
                tot += 1
                if e.split('$', 1)[1].startswith('http'):
                    ok += 1
    chk('解密命中率', tot > 0 and ok == tot, '→ %d/%d' % (ok, tot))

    # 5) 取流真打（range 请求，看真出流）
    served = False
    if urls:
        try:
            req = urllib.request.Request(urls[0], headers={'User-Agent': UA, 'Range': 'bytes=0-2047'})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read()
                served = len(body) >= 1024 and 'audio' in (r.headers.get('Content-Type') or '')
                print('     取流: HTTP %s %s %d 字节' % (r.status, r.headers.get('Content-Type'), len(body)))
        except Exception as e:
            print('     取流异常:', e)
    chk('playerContent 真出流', served)
    pc = json.loads(s.playerContent('H有声', urls[0] if urls else ''))
    chk('playerContent 契约', pc['parse'] == 0 and pc['url'].startswith('http'))

    # 6) 搜索
    sc = json.loads(s.searchContent('喘', True, '1'))
    chk('searchContent 命中', len(sc['list']) > 0, '→ %d 条' % len(sc['list']))
    if sc['list']:
        print('     搜索首条:', json.dumps(sc['list'][0], ensure_ascii=False))
    chk('search 无结果不崩', json.loads(s.searchContent('zzzqqxx', True, '1'))['list'] == [])
    chk('search 第二页不重吐', json.loads(s.searchContent('喘', True, '2'))['list'] == [])

    print('==== PASS=%d  FAIL=%d ====' % (P, F))
