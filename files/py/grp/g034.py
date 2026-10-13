# -*- coding: utf-8 -*-
"""
久久热（www.99jj25.com）· TVBox Python 插件（纯标准库）
========================================================================
【站情 · 2026-10-02 实地探站】
  KVS(Kernel Video Sharing) 内核的静态站，服务端渲染 HTML，裸 UA 直连（前面挂了层 CDN，不影响抓）。

【路径规律】
  列表： /（首页） → /videos_list_vip.php?page=N（可翻页，每页 24 条）
         分类：/categories/{hash}/ → /categories/{hash}/{N}/（第 2 页内容与第 1 页实测不同）
  详情： /videos/{id}/{slug}/
         ★ 关键坑：只用 id 的 /videos/{id}/ **会 404** —— 必须带 slug 走完整路径。
           所以本插件的 vod_id 存**完整 path**（/videos/{id}/{slug}/），详情直接用它。
  封面： /contents/videos_screenshots/{千位}/{id}/180x135/1.jpg（相对路径，拼主域）

【播放链（实测）】
  详情页里一行 JS：video_url: '…/get_file/3/{hash}/{千位}/{id}/{id}.mp4/'
  ★ /get_file/… 自己不是文件：请求它 → 302 到
       https://media1.99rego.com/remote_control.php?time=…&cv=…&cv2=…&cv3=…&cv4=…&file=…
    而这**一跳的返回体就是 video/mp4 流**（206 + ftypisom，实测 282MB 全片），
    所以它就是最终播放地址。本插件 playerContent 里先解出这一跳给壳，解不出就退回 /get_file/ 原链。
  ★ 注意：不要再对那个媒体地址发第二次探测 —— 它会把整片拖下来（踩过）。

【付费墙的实话】
  这站是**付费站**：详情页里 VIP 条目根本没有 video_url（页面里只有 "VIP" 字样）。
  本插件的处理：没有 video_url 的条目照样返回标题/封面，只是播放地址为空（不报错）；
  有 video_url 的免费条目正常给真链。video_alt_url 常写成 /hd.php 这种中转脚本，
  列出来壳里必然播不了，所以只在它是真 /get_file/ 直链时才列第二路。

【搜索】站方 /search/ 要登录（"请登录后搜索"），未登录只回空页；参数 q/search/keyword
  实测都被忽略。所以走【聚合本地检索】：抓首页 + 最新两页 + 11 个分类页，按标题关键字过滤。

自检: python3 久久热-TVBox插件.py
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

SITE_NAME = '久久热'
HOSTS = ['https://www.99jj25.com']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
PAGE = 24

CATS = [
    ('cb186ba8ba160b86eb97025b94353cac', '高清'),
    ('ffc7a71b8aae8ddd42031cea42f5bb7c', '欧美'),
    ('2f3d48fda20378cbdaaa099069a4af1e', '日本有码'),
    ('5a4e793520c46cbaee2b67760e5aea28', '东京热'),
    ('0c3d3255db00e2d3b27db08661096b23', '肛交'),
    ('281b22d3c2f5255ed57e7a09bee253f1', '韩国女主播系列'),
    ('f8789a0bf37c07c754c8e6fe27daf5f6', '成人动漫'),
    ('5d915fafb4889f0b225f2b80cc975332', '小格式综合'),
    ('251e96ab3240ae3fb3dc8bc854061957', '会员认证作品'),
    ('b8e26987b0bae1d56a00de631e4d1a68', '李宗瑞全集'),
    ('sm', 'SM性虐'),
]

RE_CARD = re.compile(
    r'<div\s+class="item[^"]*"[^>]*>\s*<a[^>]*href="(https?://[^"]*?/videos/(\d+)/[^"]*)"[^>]*title="([^"]*)"',
    re.I)
RE_IMG = re.compile(r'<img[^>]*(?:data-original|data-src|src)="([^"]+)"', re.I)
RE_DUR = re.compile(r'<div class="duration">\s*([0-9:]+)', re.I)


# ---------------------------------------------------------------- 工具
def get(path, must='/videos/', timeout=20):
    for host in HOSTS:
        try:
            req = Request(host + path, headers={
                'User-Agent': UA,
                'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': host + '/',
            })
            with urlopen(req, timeout=timeout) as r:
                t = r.read().decode('utf-8', 'ignore')
            if len(t) < 300:
                continue
            if must and must not in t:
                continue
            return t
        except Exception:
            continue
    return ''


def loc(url, referer=None, timeout=20):
    """只取 302 的 Location（不下载 body）"""
    try:
        req = Request(url, headers={
            'User-Agent': UA,
            'Accept': '*/*',
            'Referer': referer or (HOSTS[0] + '/'),
        })
        class NoRedirect(__import__('urllib.request', fromlist=['HTTPRedirectHandler']).HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = __import__('urllib.request', fromlist=['build_opener']).build_opener(NoRedirect())
        try:
            with op.open(req, timeout=timeout) as r:
                return r.headers.get('Location') or ''
        except __import__('urllib.error', fromlist=['HTTPError']).HTTPError as e:
            return e.headers.get('Location') or ''
    except Exception:
        return ''


def unesc(s):
    if not s:
        return ''
    s = (s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
          .replace('&nbsp;', ' '))
    return re.sub(r'&#(x?)([0-9a-fA-F]+);',
                  lambda m: chr(int(m.group(2), 16) if m.group(1) else int(m.group(2))), s)


def cards(page):
    out, seen = [], set()
    if not page or len(page) < 500:
        return out
    for m in RE_CARD.finditer(page):
        url, vid, title = m.group(1), m.group(2), unesc(m.group(3))
        if vid in seen:
            continue
        seen.add(vid)
        win = page[m.start():m.start() + 1600]
        mp = RE_IMG.search(win)
        pic = mp.group(1).strip() if mp else ''
        if pic.startswith('//'):
            pic = 'https:' + pic
        elif pic.startswith('/'):
            pic = HOSTS[0] + pic
        md = RE_DUR.search(win)
        mp2 = re.match(r'^https?://[^/]+(/.*)$', url)
        path = mp2.group(1) if mp2 else url
        out.append({
            'vod_id': path,          # 完整路径（详情页必须带 slug）
            'vod_name': title or vid,
            'vod_pic': pic,
            'vod_remarks': md.group(1) if md else '',
        })
    return out


def cat_path(tid, page):
    if not tid or tid == 'new':
        return '/videos_list_vip.php?page=%d' % page
    return '/categories/%s/%s' % (tid, '' if page <= 1 else '%d/' % page)


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

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        out = {'class': [], 'list': [], 'filters': {}}
        try:
            out['class'].append({'type_id': 'new', 'type_name': '最新'})
            for cid, name in CATS:
                out['class'].append({'type_id': cid, 'type_name': name})
            out['list'] = cards(get('/', '/videos/'))
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
        out['list'] = cards(get(cat_path((tid or '').strip(), page), '/videos/'))
        return out

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        out = {'list': []}
        try:
            raw = (ids or [''])[0].strip()
            if not raw:
                return out
            path = raw
            m = re.match(r'^https?://[^/]+(/.*)$', raw)
            if m:
                path = m.group(1)
            if not path.startswith('/'):
                path = '/videos/%s/' % path
            body = get(path, 'video_url') or get(path, '<title>')
            name, pic, vurl, vhd = '', '', '', ''
            m1 = re.search(r"video_url:\s*'([^']+)'", body or '')
            if m1:
                vurl = m1.group(1).strip()
            if not vurl:
                m1b = re.search(r'video_url:\s*"([^"]+)"', body or '')
                if m1b:
                    vurl = m1b.group(1).strip()
            m2 = re.search(r"video_alt_url:\s*'([^']+)'", body or '')
            if m2:
                vhd = m2.group(1).strip()
            m3 = re.search(r'og:image"\s+content="([^"]+)"', body or '')
            if m3:
                pic = m3.group(1).strip()
            if not pic:
                m3b = re.search(r'class="thumb[^"]*"[^>]*src="([^"]+)"', body or '')
                if m3b:
                    pic = m3b.group(1).strip()
            m4 = re.search(r'<h1[^>]*>(.*?)</h1>', body or '', re.S)
            if m4:
                name = unesc(re.sub(r'<[^>]+>', ' ', m4.group(1))).strip()
            if not name:
                m4b = re.search(r'og:title"\s+content="([^"]+)"', body or '')
                if m4b:
                    name = unesc(m4b.group(1))
            if not name:
                mi = re.search(r'/videos/(\d+)', path)
                name = '%s %s' % (SITE_NAME, mi.group(1) if mi else path)
            for attr, val in (('pic', pic), ('vurl', vurl)):
                pass
            if pic.startswith('//'):
                pic = 'https:' + pic
            elif pic.startswith('/'):
                pic = HOSTS[0] + pic
            if vurl.startswith('/'):
                vurl = HOSTS[0] + vurl
            if vhd.startswith('/'):
                vhd = HOSTS[0] + vhd

            vod = {
                'vod_id': raw,
                'vod_name': name,
                'vod_pic': pic,
                'vod_content': '来源：%s' % SITE_NAME,
            }
            froms, urls = [], []
            if len(vurl) > 20:
                froms.append('正片')
                urls.append('正片$%s' % vurl)
            # 高清：只在拿到真直链（get_file）时列；/hd.php 这种中转脚本壳里播不了
            if len(vhd) > 20 and '/get_file/' in vhd:
                froms.append('高清')
                urls.append('高清$%s' % vhd)
            if froms:
                vod['vod_play_from'] = '$$$'.join(froms)
                vod['vod_play_url'] = '$$$'.join(urls)
            out['list'].append(vod)
        except Exception:
            pass
        return out

    # ---------------- 搜索（聚合本地检索）----------------
    def searchContent(self, key, quick=False, pg='1'):
        out = {'list': []}
        try:
            kw = (key or '').strip().lower()
            if not kw:
                return out
            paths = ['/', '/videos_list_vip.php?page=1', '/videos_list_vip.php?page=2']
            paths += ['/categories/%s/' % c for c, _ in CATS]
            found, seen = [], set()

            def one(p):
                return cards(get(p, '/videos/'))

            with ThreadPoolExecutor(max_workers=6) as ex:
                for ls in ex.map(one, paths):
                    for c in ls:
                        if kw not in c['vod_name'].lower() or c['vod_id'] in seen:
                            continue
                        seen.add(c['vod_id'])
                        found.append(c)
            out['list'] = found
        except Exception:
            pass
        return out

    # ---------------- 播放 ----------------
    def playerContent(self, flag, vid, vipFlags=None):
        out = {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}}
        try:
            u = (vid or '').strip()
            ref = HOSTS[0] + '/'
            fin = ''
            if len(u) > 20 and ('/get_file/' in u or '/hd.php' in u):
                l = loc(u, ref)
                if l and len(l) > 20:
                    if l.startswith('/'):
                        l = HOSTS[0] + l
                    fin = l
            out['url'] = fin or u
            out['header'] = {'User-Agent': UA, 'Referer': ref}
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

    h = s.homeContent(True)
    ck('首页分类=12(最新+11分类)', len(h.get('class') or []) == 12, len(h.get('class') or []))
    ck('首页列表非空', len(h.get('list') or []) > 0, 'n=%d' % len(h.get('list') or []))
    if h.get('list'):
        c0 = h['list'][0]
        ck('卡片带封面', len(c0.get('vod_pic') or '') > 10, c0.get('vod_pic'))
        ck('卡片带标题', len(c0.get('vod_name') or '') > 2, c0.get('vod_name'))

    c1 = s.categoryContent('cb186ba8ba160b86eb97025b94353cac', '1', True, None)
    c2 = s.categoryContent('cb186ba8ba160b86eb97025b94353cac', '2', True, None)
    o1 = (c1.get('list') or [None])[0]
    o2 = (c2.get('list') or [None])[0]
    ck('分类第1页有货', bool(o1), (o1 or {}).get('vod_id'))
    ck('分类第2页有货且不同', bool(o1 and o2 and o1['vod_id'] != o2['vod_id']), (o2 or {}).get('vod_id'))
    ck('分类-最新有货', len(s.categoryContent('new', '1', True, None).get('list') or []) > 0, '')

    # 付费站：取样多条，找到一条能给真链的就算过
    good, pu, name = '', '', ''
    for c in (c1.get('list') or [])[:8]:
        d = (s.detailContent([c['vod_id']]).get('list') or [{}])[0]
        if not name:
            name = d.get('vod_name') or ''
        t = d.get('vod_play_url') or ''
        if len(t) > 20:
            good, pu = c['vod_id'], t
            break
    ck('详情有标题', len(name) > 2, name)
    ck('详情带播放地址(取样8条)', len(pu) > 20, 'id=%s len=%d' % (good, len(pu)))
    pl = s.playerContent('正片', pu.split('$', 1)[-1] if '$' in pu else pu, None)
    url = pl.get('url') or ''
    ck('播放链解出最终媒体地址(get_file→302)', 'remote_control' in url or '/get_file/' in url, url[:110])

    kw = (o1 or {}).get('vod_name') or ''
    kw = kw[:8] if len(kw) > 8 else kw
    sr = s.searchContent(kw, False, '1')
    ck('搜索有结果(聚合检索)', len(sr.get('list') or []) > 0, 'kw=%s n=%d' % (kw, len(sr.get('list') or [])))

    print('================ 结果 %d/%d ================' % (ok[0], ok[1]))
    sys.exit(0 if ok[0] == ok[1] else 1)
