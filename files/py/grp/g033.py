# -*- coding: utf-8 -*-
"""
天天A片（daydayav.com → 上游 vjav.tube）· TVBox Python 插件（纯标准库）
========================================================================
【为什么走上游 · 2026-10-02 实地探站】
  daydayav.com 以及同门的 instantav / hhhjav / javgogogo / dfjav / pushav **全站挂在
  Cloudflare Managed Challenge 下面**：curl / OkHttp 一律 403 + "Just a moment…"，
  连 /robots.txt、/sitemap.xml、/feed/、/wp-json/ 都一起挡。用真浏览器（chromium）能过盾，
  但拿到的 cf_clearance **绑定 TLS 指纹 + 出口 IP** —— 搬到手机上必然失效，
  壳里请求就是这个下场（实测：cf_clearance 带上直接 curl 还是 403）。
  而 daydayav 的片子**就是 vjav 的片**（详情页主播放器是 videovjav.com / vjav.tube 的 embed，
  data-post-id 对应的就是 vjav 的 video_id）。所以这一路直接打上游 vjav.tube：
  无盾、接口完整、片源一模一样，盒子/手机上都稳。

【接口（全部实测）】
  列表： /api/json/videos2/14400/str/{排序}/25/{段}.{对象}.{页码}.all...json
          最新：段=top-country 对象=sg（pages=2132，每页 25 条）
          分类：段=categories 对象={分类 dir}
  搜索： 排序换成 relevance，尾巴加 &sq=关键字（实测 sq 与 s 都吃）
  详情： /api/json/video/86400/0/{千位}/{id}.json → title / dir / duration / categories / thumb
  播放： /api/videofile.php?video_id={id}&lifetime=8640000

【播放串的混淆（这站最有意思的一层）】
  videofile.php 回的 video_url 是**做过字符混淆的 base64**，还原三步：
    ① 西里尔同形字母换回拉丁：М→M Е→E А→A С→C（U+041C/U+0415/U+0410/U+0421）
    ② 标点换形：`,` → `/`，`~` → `=`（padding）
    ③ 标准 base64 解码
  解出来就是 /get_file/3/{hash}/{千位}/{id}/{id}_hq.mp4/?d=&br=&ti=
  （站方前端 embed1.js 里的 C.decode 就是这个算法）。
  拼上 https://vjav.tube 请求它 → 302 到 vjav0.ahcdn.com 的签名 m3u8（master + 分片），
  playerContent 里把这一跳解到底，给壳的就是最终直链。

【平台声明】本插件播放源来自上游 vjav 的公开接口，daydayav 作为聚合站仅仅是它的展示壳。

自检: python3 天天A片-TVBox插件.py
"""

import base64
import json
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

SITE_NAME = '天天A片'
BASE = 'https://vjav.tube'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
PAGE = 25

SORTS = [('new', 'latest-updates', '最新更新'), ('hot', 'most-popular', '最热门')]
CATS = [('asian', 'Asian'), ('japanese', 'Japanese'), ('hd', 'HD'),
        ('big-tits', 'Big Tits'), ('cuckold', 'Cuckold'), ('dildos-toys', 'Toys')]

HOMO = {
    '\u0410': 'A', '\u0412': 'B', '\u0415': 'E', '\u041a': 'K', '\u041c': 'M',
    '\u041d': 'H', '\u041e': 'O', '\u0420': 'P', '\u0421': 'C', '\u0422': 'T',
    '\u0423': 'Y', '\u0425': 'X',
    '\u0430': 'a', '\u0432': 'b', '\u0435': 'e', '\u043a': 'k', '\u043c': 'm',
    '\u043d': 'h', '\u043e': 'o', '\u0440': 'p', '\u0441': 'c', '\u0442': 't',
    '\u0443': 'y', '\u0445': 'x',
    '\u0456': 'i', '\u0458': 'j', '\u0455': 's',
}
B64V = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


# ---------------------------------------------------------------- 工具
def api(path, timeout=20):
    try:
        req = Request(BASE + path, headers={
            'User-Agent': UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': BASE + '/',
            'X-Requested-With': 'XMLHttpRequest',
        })
        with urlopen(req, timeout=timeout) as r:
            t = r.read().decode('utf-8', 'ignore')
        if len(t) < 20:
            return ''
        if '"error"' in t and '"videos"' not in t and '"video"' not in t:
            return ''
        return t
    except Exception:
        return ''


def loc(url, referer=None, timeout=20):
    """只取 302 的 Location（不下载 body）"""
    try:
        import urllib.request as ur
        import urllib.error as ue

        class NoRedirect(ur.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        op = ur.build_opener(NoRedirect())
        req = ur.Request(url, headers={
            'User-Agent': UA,
            'Accept': '*/*',
            'Referer': referer or (BASE + '/'),
        })
        try:
            with op.open(req, timeout=timeout) as r:
                return r.headers.get('Location') or ''
        except ue.HTTPError as e:
            return e.headers.get('Location') or ''
    except Exception:
        return ''


def b64dec(s):
    """自实现 base64 解码（错误字符直接跳过，容混淆残留）"""
    try:
        if not s or len(s) < 4:
            return ''
        s = s.replace('-', '+').replace('_', '/')
        buf = bits = 0
        raw = bytearray()
        for ch in s:
            v = B64V.find(ch)
            if v < 0:
                continue
            buf = (buf << 6) | v
            bits += 6
            if bits >= 8:
                bits -= 8
                raw.append((buf >> bits) & 0xFF)
        return raw.decode('utf-8', 'ignore')
    except Exception:
        return ''


def deobf(s):
    """站方那层字符混淆的还原（对应 embed1.js 的 C.decode 前置处理）"""
    if not s:
        return ''
    out = []
    for ch in s:
        o = ord(ch)
        if o > 127:
            out.append(HOMO.get(ch, ch))
        elif ch == ',':
            out.append('/')
        elif ch == '~':
            out.append('=')
        else:
            out.append(ch)
    clean = ''.join(c for c in ''.join(out) if c in B64V + '=')
    while len(clean) % 4:
        clean += '='
    return b64dec(clean).strip()


def thumb_of(vid):
    try:
        n = int(vid) // 1000 * 1000
        return 'https://tn.vjav.com/contents/videos_screenshots/%d/%s/240x180/1.jpg' % (n, vid)
    except Exception:
        return ''


def cards(body):
    out = []
    if not body:
        return out
    try:
        o = json.loads(body)
    except Exception:
        return out
    for v in (o.get('videos') or []):
        vid = str(v.get('video_id') or '')
        if not vid:
            continue
        out.append({
            'vod_id': vid,
            'vod_name': v.get('title') or vid,
            'vod_pic': v.get('thumb') or thumb_of(vid),
            'vod_remarks': v.get('duration') or '',
        })
    return out


def list_path(section, obj, page):
    return '/api/json/videos2/14400/str/latest-updates/%d/%s.%s.%d.all...json' % (PAGE, section, obj, page)


def file_url(vid):
    body = api('/api/videofile.php?video_id=%s&lifetime=8640000' % vid)
    if not body:
        return ''
    try:
        a = json.loads(body)
        if not a:
            return ''
        u = deobf(a[0].get('video_url') or '')
        if not u:
            return ''
        return (BASE + u) if u.startswith('/') else u
    except Exception:
        return ''


# ---------------------------------------------------------------- 插件本体
class Spider(object):

    def __init__(self):
        self.extend_host = ''

    def init(self, extend=''):
        try:
            if extend:
                o = json.loads(extend) if isinstance(extend, str) else extend
                h = (o or {}).get('host', '')
                if h and len(h) > 8:
                    if not h.startswith('http'):
                        h = 'https://' + h
                    self.extend_host = h.rstrip('/')
        except Exception:
            pass
        return self

    def getName(self):
        return '🔞' + SITE_NAME

    def _base(self):
        return self.extend_host or BASE

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        out = {'class': [], 'list': [], 'filters': {}}
        try:
            for k, _, n in SORTS:
                out['class'].append({'type_id': k, 'type_name': n})
            for d, n in CATS:
                out['class'].append({'type_id': 'c:' + d, 'type_name': n})
            out['list'] = cards(api(list_path('top-country', 'sg', 1)))
        except Exception:
            pass
        return out

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter=False, extend=None):
        out = {'list': [], 'page': 1, 'pagecount': 9999, 'limit': PAGE, 'total': 9999 * PAGE}
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        out['page'] = page
        t = (tid or '').strip()
        if t.startswith('c:'):
            path = list_path('categories', t[2:], page)
        else:
            sort = 'latest-updates'
            for k, s, _ in SORTS:
                if k == t:
                    sort = s
            path = '/api/json/videos2/14400/str/%s/%d/top-country.sg.%d.all...json' % (sort, PAGE, page)
        out['list'] = cards(api(path))
        return out

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        out = {'list': []}
        try:
            raw = (ids or [''])[0].strip()
            if not raw:
                return out
            m = re.search(r'(\d{4,})', raw)
            vid = m.group(1) if m else raw
            name = pic = dur = cats = ''
            try:
                q = int(vid) // 1000 * 1000
            except Exception:
                q = 0
            body = api('/api/json/video/86400/0/%d/%s.json' % (q, vid))
            if body:
                v = (json.loads(body) or {}).get('video') or {}
                name = v.get('title') or ''
                pic = v.get('thumb') or ''
                dur = v.get('duration') or ''
                cs = v.get('categories') or {}
                if isinstance(cs, dict):
                    cats = ' / '.join((cs[k] or {}).get('title') or '' for k in cs)
            if not name:
                name = '%s %s' % (SITE_NAME, vid)
            sb = []
            if cats:
                sb.append('分类：' + cats)
            if dur:
                sb.append('时长：' + dur)
            sb.append('来源：%s' % SITE_NAME)
            vod = {
                'vod_id': raw,
                'vod_name': name,
                'vod_pic': pic or thumb_of(vid),
                'vod_remarks': dur or cats,
                'vod_content': '\n'.join(sb),
            }
            play = file_url(vid)
            if len(play) > 20:
                vod['vod_play_from'] = '正片'
                vod['vod_play_url'] = '正片$%s' % play
            out['list'].append(vod)
        except Exception:
            pass
        return out

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg='1'):
        out = {'list': []}
        try:
            kw = (key or '').strip()
            if not kw:
                return out
            q = quote(kw, safe='')
            ls = cards(api('/api/json/videos2/14400/str/relevance/%d/top-country.sg.1.all...json?sq=%s' % (PAGE, q)))
            if not ls:
                ls = cards(api('/api/json/videos2/14400/str/relevance/%d/top-country.sg.1.all...json?s=%s' % (PAGE, q)))
            out['list'] = ls
        except Exception:
            pass
        return out

    # ---------------- 播放 ----------------
    def playerContent(self, flag, vid, vipFlags=None):
        out = {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}}
        try:
            u = (vid or '').strip()
            if len(u) > 20:
                fin = ''
                if '/get_file/' in u:
                    l = loc(u, BASE + '/')
                    if l and len(l) > 20:
                        fin = l if l.startswith('http') else BASE + l
                out['url'] = fin or u
            out['header'] = {'User-Agent': UA, 'Referer': BASE + '/'}
        except Exception:
            pass
        return out


# ---------------------------------------------------------------- 自检
if __name__ == '__main__':
    ok = [0, 0]

    def ck(label, cond, detail=''):
        ok[1] += 1
        if cond:
            ok[0] += 1
        print(('  PASS ' if cond else '  FAIL ') + label + (('  | ' + str(detail)[:110]) if detail else ''))

    print('================ %s py 插件自检 ================' % SITE_NAME)
    s = Spider().init('')
    ck('getName', s.getName() == '🔞' + SITE_NAME, s.getName())

    # ① 混淆还原向量（真接口样本）
    obf = ('L2dldF9maWxlLz\u041cv\u041cm\u04150ZGZhZmQzNTZiNmFjNGZj\u041c2FlYT\u041cxNWYx'
           '\u041cWQ4NTNhZD\u04105OW\u041c1Zm\u041cxLzk3ND\u0410w\u041c\u042185NzQwNT\u0415vOTc0'
           '\u041cDUxX2hxLm1wN\u04218,ZD02Nj\u0410mYnI9NzkmdGk9\u041cTc5\u041cDkxNj\u04154OQ~~')
    d = deobf(obf)
    ck('播放串混淆还原(同形字母+标点+base64)', d.startswith('/get_file/') and '_hq.mp4' in d, d)

    h = s.homeContent(True)
    ck('首页分类非空', len(h.get('class') or []) >= 2, len(h.get('class') or []))
    ck('首页列表非空', len(h.get('list') or []) > 0, 'n=%d' % len(h.get('list') or []))
    if h.get('list'):
        c0 = h['list'][0]
        ck('卡片带封面', len(c0.get('vod_pic') or '') > 10, c0.get('vod_pic'))
        ck('卡片带标题', len(c0.get('vod_name') or '') > 2, c0.get('vod_name'))

    c1 = s.categoryContent('new', '1', True, None)
    c2 = s.categoryContent('new', '2', True, None)
    o1 = (c1.get('list') or [None])[0]
    o2 = (c2.get('list') or [None])[0]
    ck('最新第1页有货', bool(o1), 'n=%d' % len(c1.get('list') or []))
    ck('最新第2页有货且不同', bool(o1 and o2 and o1['vod_id'] != o2['vod_id']), (o2 or {}).get('vod_id'))
    ck('最热门有货', len(s.categoryContent('hot', '1', True, None).get('list') or []) > 0, '')
    ck('分类(asian)有货', len(s.categoryContent('c:asian', '1', True, None).get('list') or []) > 0, '')

    d0 = (s.detailContent([o1['vod_id']]).get('list') or [{}])[0] if o1 else {}
    ck('详情有标题', len(d0.get('vod_name') or '') > 2, d0.get('vod_name'))
    ck('详情有封面', len(d0.get('vod_pic') or '') > 10, '-')
    pu = d0.get('vod_play_url') or ''
    ck('详情带播放地址', len(pu) > 20, 'len=%d' % len(pu))
    pl = s.playerContent('正片', pu.split('$', 1)[-1] if '$' in pu else pu, None)
    url = pl.get('url') or ''
    ck('播放链解出 ahcdn 直链(get_file→302)', 'ahcdn' in url, url[:110])

    sr = s.searchContent('ssni', False, '1')
    ck('搜索有结果', len(sr.get('list') or []) > 0, 'n=%d' % len(sr.get('list') or []))

    print('================ 结果 %d/%d ================' % (ok[0], ok[1]))
    sys.exit(0 if ok[0] == ok[1] else 1)
