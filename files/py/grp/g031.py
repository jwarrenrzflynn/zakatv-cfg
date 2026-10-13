# -*- coding: utf-8 -*-
"""
酷愛成人網（coolinet.net / www.230304.xyz）· TVBox Python 插件
========================================================================
【站情 · 2026-10-03 实地探站】
  WordPress + 自研 awp 主题，两域互为镜像（www.230304.xyz / www.coolinet.net）。
  CF 前置但**不吃挑战**（直连 200，无盾）、无登录墙、无会员墙。

【链路（实测）】
  首页   /                              第 N 页 /page/N/
  分类   /category/<slug>/              第 N 页 /category/<slug>/page/N/
  搜索   /?s=<词>                       第 N 页 /page/N/?s=<词>
  详情   /?p=<id>（301 到正式地址）     **REST 更稳**：/wp-json/wp/v2/posts/<id>?_embed=1
  播放   //video1.yocoolnet.in/api/player_coolinet.php?player=N&id=<短码>&height=520&req_uri=<来源页>
         → 页内 hls.loadSource("https://v5.yocoolnet.in/files/mp4/…/xxx.m3u8?sk=..&se=..")

【★ 三个必踩的坑（都已在代码里绕开）】
  ① 播放器页**必须带 Referer: https://www.coolinet.net/** —— 裸请求它只回一句
     「想看A片請拜訪 coolinet.net」的占位页（里面一条流都没有，状态码还是 200）。
     只看状态码就会把它当成"取到了"，然后解不出地址。
  ② 清单 URL 带 sk/se 时效签名（se=过期时间戳）。所以**详情页不解流**，
     留到 playerContent 现取现解 —— 用户从打开详情到点播放可能隔很久。
  ③ 首页第一张常是站方的教程/公告文（没播放器），别拿它当"源坏了"的证据；
     分类页里才是纯影片。

【取流结论 · 干净到不用破】
  清单裸取 200（application/vnd.apple.mpegurl、#EXTM3U / VOD / 2529 片），
  分片裸取 200、首字节 0x47、188 对齐 —— 真 TS，清单和分片都不带防盗链。

【纯标准库】无第三方依赖，按手机壳真实条件写。
自检: python3 酷愛成人網-TVBox插件.py
"""

import base64
import json
import re
import time
import urllib.parse
import urllib.request

try:                                              # TVBox 壳内基类
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):                        # 原生 python 下自检用
        def init(self, *a, **kw):
            return self

# ---------------------------------------------------------------- 常量
SITE_NAME = '酷愛成人網'
UA = ('Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

POOL = ['https://www.230304.xyz', 'https://www.coolinet.net']
PLAYER_REF = 'https://www.coolinet.net/'          # ★ 播放器页只认这个 Referer

# 站方导航里的分类（slug, 名）—— 按 REST 分类表核过；公告/未分類不是影片，不接
CLASSES = [
    ('chinese-subtitle', '中文字幕'),
    ('asia-video', '亞洲AV'),
    ('eu-us-movie', '歐美AV'),
    ('%e7%9b%b4%e6%92%ad', '直播'),
    ('%e4%ba%9e%e6%b4%b2%e8%87%aa%e6%8b%8d%e5%81%b7%e6%8b%8d', '亞洲自拍偷拍'),
    ('eu-us-self', '歐美自拍偷拍'),
    ('%e6%80%a7%e6%84%9f%e7%be%8e%e5%9c%96', '性感美圖'),
]

PAGE_SIZE = 20

# ---------------------------------------------------------------- HTTP
_JA3_HDR = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
}


def _http(url, timeout=20, ref=None, headers=None, binary=False):
    h = dict(_JA3_HDR)
    if headers:
        h.update(headers)
    if ref:
        h['Referer'] = ref
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except Exception:
        return b'' if binary else ''
    if binary:
        return raw
    for enc in ('utf-8', 'gbk', 'big5'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', 'replace')


def _b64e(s):
    """URL-safe Base64（不补位）—— 播放参数走它，避免 URL 里的 ?&= 被壳拆坏"""
    try:
        return base64.urlsafe_b64encode((s or '').encode('utf-8')).decode('ascii').rstrip('=')
    except Exception:
        return ''


def _b64d(s):
    try:
        t = (s or '').strip()
        return base64.urlsafe_b64decode(t + '=' * (-len(t) % 4)).decode('utf-8', 'replace')
    except Exception:
        return ''


def _host_of(u):
    try:
        p = urllib.parse.urlparse(u if '://' in u else 'https://' + u)
        return p.netloc
    except Exception:
        return ''


def _ent(s):
    """HTML 实体还原（站方标题里 &#8211; 这类很多，不还原壳里就是乱码）"""
    if not s:
        return ''
    t = (s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#039;', "'").replace('&apos;', "'")
          .replace('&nbsp;', ' ').replace('&hellip;', '…').replace('&mdash;', '—')
          .replace('&ndash;', '–').replace('&rsquo;', '’').replace('&lsquo;', '‘')
          .replace('&ldquo;', '“').replace('&rdquo;', '”').replace('&middot;', '·'))
    return re.sub(r'&#(x?)([0-9a-fA-F]+);',
                  lambda m: chr(int(m.group(2), 16) if m.group(1) else int(m.group(2))), t)


def _strip(h):
    if not h:
        return ''
    s = re.sub(r'(?is)<script.*?</script>', ' ', h)
    s = re.sub(r'(?is)<style.*?</style>', ' ', s)
    s = re.sub(r'(?is)<br\s*/?>', '\n', s)
    s = re.sub(r'(?is)</p>', '\n', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = _ent(s).replace('\u00a0', ' ')
    s = re.sub(r'[ \t\x0b\f\r]+', ' ', s)
    s = re.sub(r'\n{2,}', '\n', s)
    return s.strip()[:1200]


def _probe():
    """域池探活：两个域随便哪个给出真列表页就用哪个，缓存 30 分钟"""
    now = time.time()
    hit = _probe.cache
    if hit and now - hit[0] < 1800:
        return hit[1]
    for h in POOL:
        t = _http(h + '/', timeout=15, ref=h + '/')
        if t and 'videoPost' in t:
            _probe.cache = (now, h)
            return h
    _probe.cache = (now, POOL[0])
    return POOL[0]


_probe.cache = None

# ---------------------------------------------------------------- 列表解析
_RE_CARD = re.compile(r'<div class="videoPost"')


def _cards(html):
    """列表页 → 卡片数组。按 .videoPost 切块，块内逐字段抠（不赌整块正则）"""
    out = []
    if not html or 'videoPost' not in html:
        return out
    for seg in html.split('<div class="videoPost"')[1:]:
        s = seg[:2600]
        m = re.search(r'^\s*id="post-(\d+)"', s) or re.search(r'id="post-(\d+)"', s)
        if not m:
            continue
        pid = m.group(1)
        href = ''
        mh = re.search(r'<a[^>]*class="thlink"[^>]*href="([^"]+)"', s)
        if mh:
            href = mh.group(1)
        title = ''
        mt = re.search(r'<a[^>]*class="videoLink"[^>]*title="([^"]*)"', s)
        if mt:
            title = _ent(mt.group(1))
        if not title:
            mt2 = re.search(r'title="([^"]+)"', s)
            if mt2:
                title = _ent(mt2.group(1))
        pic = ''
        mp = re.search(r'<img[^>]*src="([^"]+)"', s)
        if mp:
            pic = mp.group(1)
        mv = re.search(r'thumbViews">([^<]*)<', s)
        views = _ent(mv.group(1)).strip() if mv else ''
        out.append({
            'vod_id': pid,
            'vod_name': title or ('酷愛 #' + pid),
            'vod_pic': pic,
            'vod_remarks': views.replace(' 觀看', '次') if views else '',
        })
    return out


_RE_IFRAME = re.compile(r'src="(//video[^"\']*player_coolinet[^"\']*)"')
_RE_IFRAME2 = re.compile(r'src="(https?://[^"\']*player_coolinet[^"\']*)"')
_RE_M3U8 = re.compile(r'loadSource\(\s*["\']([^"\']+\.m3u8[^"\']*)["\']')
_RE_M3U8_ANY = re.compile(r'["\'](https?://[^"\'\s<>]+?\.m3u8[^"\'\s<>]*)["\']')


def _iframe_src(html):
    if not html:
        return ''
    for rx in (_RE_IFRAME, _RE_IFRAME2):
        m = rx.search(html)
        if m:
            return m.group(1)
    return ''


class Spider(_Spider):

    def __init__(self, *args, **kwargs):
        self.host = ''
        self._cache = {}

    # ---------------- 基础
    def init(self, extend=''):
        self.host = ''
        ext = (extend or '').strip()
        if ext.startswith('{'):
            try:
                h = (json.loads(ext).get('host') or '').strip()
                if len(h) > 6:
                    self.host = (h if h.startswith('http') else 'https://' + h).rstrip('/')
            except Exception:
                pass
        elif ext.startswith('http'):
            self.host = ext.rstrip('/')
        return self

    def getName(self):
        return SITE_NAME

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def manualVideoCheck(self):
        return False

    def _base(self):
        return self.host if self.host else _probe()

    def _get(self, path, must=None, ttl=1800):
        base = self._base()
        u = path if path.startswith('http') else base + path
        hit = self._cache.get(u)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        t = _http(u, timeout=20, ref=base + '/')
        if t and len(t) > 1500 and (not must or must in t):
            self._cache[u] = (time.time(), t)
            return t
        return t or ''

    def _rest(self, path):
        """REST 一次拿全（标题/封面/日期/正文里的播放器 iframe），失败返回 {}"""
        for h in ([self.host] if self.host else []) + POOL:
            if not h:
                continue
            u = h + path
            t = _http(u, timeout=20, ref=h + '/',
                      headers={'Accept': 'application/json,*/*'})
            if t and t[:1] in ('{', '['):
                try:
                    return json.loads(t)
                except Exception:
                    continue
        return {}

    # ---------------- 首页 / 分类
    def homeContent(self, filter=False):
        cls = [{'type_name': '最新發表', 'type_id': 'home'}]
        cls += [{'type_name': n, 'type_id': t} for t, n in CLASSES]
        return {'class': cls, 'list': _cards(self._get('/', must='videoPost'))}

    def homeVideoContent(self):
        return {'list': _cards(self._get('/', must='videoPost'))}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        t = (tid or '').strip()
        try:
            page = max(1, int(str(pg).strip()))
        except Exception:
            page = 1
        if not t or t == 'home':
            path = '/' if page <= 1 else '/page/%d/' % page
        else:
            path = '/category/%s/%s' % (t, '' if page <= 1 else 'page/%d/' % page)
        body = self._get(path, must='videoPost')
        lst = _cards(body)
        pc = page + 1
        m = re.search(r'class="end"[^>]*href="[^"]*?/page/(\d+)/"', body or '')
        if m:
            pc = int(m.group(1))
        return {'page': page, 'pagecount': pc, 'limit': PAGE_SIZE,
                'total': pc * PAGE_SIZE, 'list': lst}

    # ---------------- 搜索
    def searchContent(self, key, quick=False, pg='1'):
        try:
            page = max(1, int(str(pg).strip()))
        except Exception:
            page = 1
        kw = urllib.parse.quote(key or '')
        path = ('/' if page <= 1 else '/page/%d/' % page) + '?s=' + kw
        lst = _cards(self._get(path, must='videoPost'))
        return {'page': page, 'pagecount': page + 1 if len(lst) >= PAGE_SIZE else page,
                'limit': PAGE_SIZE, 'total': page * PAGE_SIZE, 'list': lst}

    # ---------------- 详情
    def detailContent(self, ids):
        target = ids[0] if isinstance(ids, (list, tuple)) and ids else str(ids or '')
        pid = ''.join(ch for ch in str(target) if ch.isdigit())
        if not pid:
            return {'list': []}

        name = pic = date = desc = player = ''
        d = self._rest('/wp-json/wp/v2/posts/%s?_embed=1' % pid)
        if d:
            name = _ent((d.get('title') or {}).get('rendered', ''))
            date = d.get('date', '') or ''
            content = (d.get('content') or {}).get('rendered', '') or ''
            desc = _strip(content)
            player = _iframe_src(content)
            try:
                fm = (d.get('_embedded') or {}).get('wp:featuredmedia') or []
                if fm:
                    pic = fm[0].get('source_url', '') or ''
            except Exception:
                pic = ''
            if not pic and d.get('featured_media'):
                md = self._rest('/wp-json/wp/v2/media/%s' % d['featured_media'])
                pic = (md or {}).get('source_url', '') or ''

        if not name or not player:
            html = self._get('/?p=%s' % pid, must='allmyplayer')
            if html:
                if not name:
                    m = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.S)
                    if m:
                        name = _ent(_strip(m.group(1)))
                if not name:
                    m = re.search(r'<title>(.*?)</title>', html, re.S)
                    if m:
                        name = _ent(m.group(1)).replace('酷愛成人網', '').replace('–coolinet.net', '').strip()
                if not player:
                    player = _iframe_src(html)
                if not desc:
                    m = re.search(r'id="videoPostContent">(.*?)</div>', html, re.S)
                    if m:
                        desc = _strip(m.group(1))

        if not name:
            name = '酷愛 #' + pid

        froms, urls = [], []
        if player:
            if player.startswith('//'):
                player = 'https:' + player
            for i, tag in enumerate(('酷愛①', '酷愛②', '酷愛③'), start=1):
                line = re.sub(r'player=\d+', 'player=%d' % i, player)
                froms.append(tag)
                urls.append('正片$' + _b64e(line))

        vod = {
            'vod_id': str(target),
            'vod_name': name,
            'vod_pic': pic,
            'vod_year': date[:4] if len(date) >= 4 else '',
            'vod_content': desc,
            'vod_remarks': date[5:10].replace('-', '/') if len(date) >= 10 else '',
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }
        return {'list': [vod]}

    # ---------------- 播放
    def playerContent(self, flag, vid, vipFlags=None):
        u = (vid or '').strip()
        if u.startswith('$'):
            u = u[1:]
        if not u.startswith('http'):
            d = _b64d(u)
            u = d if d.startswith('http') else ''
        line = self._resolve(u) if u else ''
        if line:
            return {'parse': 0, 'jx': 0, 'url': line, 'playUrl': '',
                    'header': {'User-Agent': UA}}
        # 解不出来就把播放器页交回壳自己解（有的壳带内核能兜住）
        return {'parse': 1, 'jx': 0, 'url': u, 'playUrl': '',
                'header': {'User-Agent': UA, 'Referer': PLAYER_REF}}

    def _resolve(self, player_url):
        """播放器页 → m3u8。★ 必须带 Referer，不然拿回来的是占位提示页"""
        if not player_url or len(player_url) < 20:
            return ''
        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        body = _http(player_url, timeout=20, ref=PLAYER_REF)
        if not body or len(body) < 400:
            return ''
        if '想看A片' in body and 'm3u8' not in body:
            return ''
        for rx in (_RE_M3U8, _RE_M3U8_ANY):
            m = rx.search(body)
            if m:
                return m.group(1)
        return ''


# ---------------------------------------------------------------- 自检
if __name__ == '__main__':
    import sys

    ok = bad = 0

    def ck(what, cond, extra=''):
        global ok, bad
        if cond:
            ok += 1
            print('  ✅ %s %s' % (what, ('[%s]' % extra) if extra else ''))
        else:
            bad += 1
            print('  ❌ %s %s' % (what, ('[%s]' % extra) if extra else ''))

    sp = Spider().init('{}')
    print('=========== 酷愛成人網 插件自检 ===========')
    h = sp.homeContent()
    ck('首页分类', len(h['class']) >= 5, '%d 类' % len(h['class']))
    ck('首页卡片', len(h['list']) >= 5, '%d 张' % len(h['list']))

    c = sp.categoryContent(CLASSES[0][0], '1')
    ck('分类页', len(c['list']) >= 5, '%d 张 · 共%s页' % (len(c['list']), c['pagecount']))
    c2 = sp.categoryContent(CLASSES[0][0], '2')
    ck('分类翻页换页', bool(c2['list']) and c2['list'][0]['vod_id'] != c['list'][0]['vod_id'],
       'p1=%s p2=%s' % (c['list'][0]['vod_id'], c2['list'][0]['vod_id']))

    s = sp.searchContent('波多野')
    ck('搜索', len(s['list']) >= 1, '%d 条' % len(s['list']))

    real = c['list'][0]['vod_id'] if c['list'] else ''
    d = sp.detailContent([real])
    if d['list']:
        v = d['list'][0]
        ck('详情标题', len(v['vod_name']) > 3, v['vod_name'][:34])
        ck('详情封面', v['vod_pic'].startswith('http'), v['vod_pic'][:60])
        ck('详情线路', bool(v['vod_play_from']), v['vod_play_from'])
        first = v['vod_play_url'].split('$$$')[0]
        b64 = first.split('$', 1)[-1]
        p = sp.playerContent('酷愛①', b64)   # detail 已把播放器页封成 B64
        url = p.get('url', '')
        ck('解出直链', '.m3u8' in url, url[:80])
        if '.m3u8' in url:
            raw = _http(url, timeout=20, binary=True)
            txt = raw.decode('utf-8', 'replace') if raw else ''
            ck('清单真拉 #EXTM3U', '#EXTM3U' in txt, '%d bytes' % len(raw))
            seg = ''
            for ln in txt.split('\n'):
                ln = ln.strip()
                if ln and not ln.startswith('#'):
                    seg = ln
                    break
            if seg:
                su = urllib.parse.urljoin(url, seg)
                sb = _http(su, timeout=20, binary=True)
                ck('分片真拿 TS', bool(sb) and len(sb) > 50000 and sb[0] == 0x47,
                   '%d bytes 首字节=0x%02x' % (len(sb), sb[0] if sb else 0))
    ck('坏 id 不炸', isinstance(sp.detailContent(['abc']), dict), '')

    print('---------- 酷愛: PASS=%d FAIL=%d ----------' % (ok, bad))
    sys.exit(2 if bad else 0)
