#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SupJav TVBox 爬虫 (type=3 Python spider)
================================================================
数据源: supjav.com (WordPress supjav2 主题, Cloudflare 保护)
过盾:   页面全部走 1314/page (Playwright 真实浏览器 + challenge 重试)
播放链: 详情 data-link(hex)
        → supjav.php?l=<hex>        (需 Referer=详情页)
        → 页内 OLID 反转
        → supjav.php?c=<reversed>   (需 Referer=step1)
        → TV 线路: 明文 m3u8 (turboviplay)
          FST 线路: packer 解包 → m3u8 (premilkyway)
        master m3u8 实测免 Referer 直连可播 → 直接给 TVBox
"""
import re
import json
import time
import base64
import codecs
import urllib.parse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object

try:
    import requests
except Exception:
    requests = None

import urllib.request
import ssl

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

HOST = 'https://supjav.com'
PROXY_BASE = 'https://py.fzcrym.link:1314'
PAGE_API = PROXY_BASE + '/page?u='
FS_PAGE_API = PROXY_BASE + '/fs?u='
STREAM_API = PROXY_BASE + '/stream?u='
SJ_HLS_API = PROXY_BASE + '/sj_hls?u='
SJ_IMG_API = PROXY_BASE + '/sj_img?u='
LK_BASE = 'https://lk1.supremejav.com/supjav.php'

# 分类严格对齐站点导航栏 (supjav.com 顶部 nav):
#   Home / Popular / Censored / Uncensored / Amateur / Chn Sub /
#   Reducing Mosaic / Eng Sub
# Maker / Cast / Genre 是索引页(不是影片列表), 不做分类
CATS = [
    ('__home', '最新'),
    ('__popular', '热门'),
    ('censored-jav', '有码 Censored'),
    ('uncensored-jav', '无码 Uncensored'),
    ('amateur', '素人 Amateur'),
    ('chinese-subtitles', '中文字幕 Chn Sub'),
    ('reducing-mosaic', '破解 Reducing Mosaic'),
    ('english-subtitles', '英文字幕 Eng Sub'),
]

# 线路排序(数字越小越靠前): VOE 第一, TV 最后
#   VOE 720p/1080p, 走 stream 代理转流, 分片稳定
#   FST 480p, packer 解包 + token 绑 IP, 走代理
#   ST  streamtape mp4 直链, 播放器自跟 302 + Range
#   TV  1080p 但分片伪装 PNG, 需 /sj_hls 逐片剥头, 开销最大 → 垫底
LINE_ORDER = {
    'VOE': 0,
    'FST': 10,
    'ST': 20,
    'TV': 90,
}

# 站点支持 ?sort=views 排序
SORTS = [
    {'key': 'sort', 'name': '排序',
     'value': [{'n': '最新', 'v': ''}, {'n': '最多观看', 'v': 'views'}]},
]


class Spider(BaseSpider):

    def __init__(self):
        if hasattr(BaseSpider, '__init__'):
            try:
                super().__init__()
            except Exception:
                pass
        self.name = 'SupJav'
        self._sess = None
        if requests is not None:
            try:
                self._sess = requests.Session()
                self._sess.headers.update({'User-Agent': UA})
            except Exception:
                self._sess = None

    def getName(self):
        return self.name

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        return [404, 'text/plain', '']

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', url, re.I))

    # ---------------- 网络层 ----------------
    def _get(self, url, timeout=60):
        """requests 优先, urllib 兜底"""
        if self._sess is not None:
            try:
                r = self._sess.get(url, timeout=timeout, verify=False)
                if r.status_code == 200:
                    return r.text
            except Exception:
                pass
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode('utf-8', 'replace')
        except Exception:
            return ''

    def _page(self, url, retries=2):
        """站内页面: 走代理 /fs (clearance 快速通道 + FlareSolverr 兜底)

        代理侧优先用缓存的 cf_clearance 直连(约 0.7s), 失效才回落过盾(约 15s)。
        """
        api = FS_PAGE_API + urllib.parse.quote(url, safe='')
        for _ in range(max(1, retries)):
            html = self._get(api, timeout=220)
            if html and 'Just a moment' not in html and len(html) > 3000:
                return html
        # 兜底: 退回 Playwright 通道
        api2 = PAGE_API + urllib.parse.quote(url, safe='')
        html = self._get(api2, timeout=90)
        if html and 'Just a moment' not in html and len(html) > 3000:
            return html
        return ''

    def _stream(self, url, referer='', timeout=90):
        """第三方跳转页: 走 curl_cffi 代理并带 Referer"""
        api = STREAM_API + urllib.parse.quote(url, safe='')
        if referer:
            api += '&r=' + urllib.parse.quote(referer, safe='')
        return self._get(api, timeout=timeout)

    # 播放地址解析缓存: 三跳解析(?l= → OLID 反转 → ?c=)每次要 3~6s,
    # 用户切线路/重进详情会反复付这个成本。token 有效期远大于 90s, 可安全缓存。
    _PLAY_CACHE = {}
    _PLAY_TTL = 90

    @classmethod
    def _play_cache_get(cls, key):
        v = cls._PLAY_CACHE.get(key)
        if not v:
            return None
        if time.time() - v[0] > cls._PLAY_TTL:
            cls._PLAY_CACHE.pop(key, None)
            return None
        return v[1]

    @classmethod
    def _play_cache_put(cls, key, val):
        cls._PLAY_CACHE[key] = (time.time(), val)
        if len(cls._PLAY_CACHE) > 60:
            for k in sorted(cls._PLAY_CACHE,
                            key=lambda x: cls._PLAY_CACHE[x][0])[:20]:
                cls._PLAY_CACHE.pop(k, None)


    # ---------------- 解析层 ----------------
    @staticmethod
    def _cards(html):
        """列表卡片: <div class="post"> 块 → 去重列表"""
        out, seen = [], set()
        blocks = re.split(r'<div class="post">', html)[1:]
        for b in blocks:
            m = re.search(r'href="' + re.escape(HOST) + r'/(\d+)\.html"', b)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            t = re.search(r'title="([^"]+)"', b)
            title = t.group(1) if t else ''
            title = (title.replace('&amp;', '&').replace('&#8217;', "'")
                     .replace('&quot;', '"').replace('&#8211;', '-')).strip()
            if not title:
                continue
            seen.add(vid)
            pic = ''
            # 站点用 lazy-load: 真实地址在 data-original，src 是 data: 占位符
            for pat in (r'<img[^>]+data-original="([^"]+)"',
                        r'<img[^>]+data-src="([^"]+)"',
                        r'<img[^>]+src="(https?://[^"]+)"'):
                pm = re.search(pat, b)
                if pm:
                    pic = pm.group(1)
                    break
            if pic.startswith('//'):
                pic = 'https:' + pic
            # img.supjav.com 有 UA 门槛(无 UA 直接 403), TVBox 图片加载器
            # 不一定带 UA → 统一走代理补 header
            if pic.startswith('http'):
                pic = SJ_IMG_API + urllib.parse.quote(pic, safe='')
            # 番号: 标题里的 ABC-123 / FC2PPV 1234567
            code = ''
            cm = re.search(r'\b([A-Z]{2,6}-?\d{2,6}|FC2PPV[\s-]?\d{5,8})\b', title)
            if cm:
                code = cm.group(1)
            out.append({
                'vod_id': vid,
                'vod_name': title[:90],
                'vod_pic': pic,
                'vod_remarks': code,
            })
        return out

    @staticmethod
    def _pagecount(html, cur):
        nums = [int(x) for x in re.findall(r'/page/(\d+)', html)]
        if not nums:
            return cur
        mx = max(nums)
        return mx if 0 < mx <= 5000 else cur

    @staticmethod
    def _unpack(text):
        """Dean Edwards packer 解包"""
        m = re.search(r"}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", text, re.S)
        if not m:
            return ''
        payload, base, count, keys = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split('|')
        try:
            payload = payload.encode().decode('unicode_escape')
        except Exception:
            pass
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'

        def enc(num):
            out = ''
            while num > 0:
                out = digits[num % base] + out
                num //= base
            return out or '0'

        table = {}
        for i in range(count):
            if i < len(keys) and keys[i]:
                table[enc(i)] = keys[i]
        return re.sub(r'\b\w+\b', lambda mm: table.get(mm.group(0), mm.group(0)), payload)

    # ---------------- TVBox 接口 ----------------
    def homeContent(self, filter):
        classes = [{'type_id': cid, 'type_name': cname} for cid, cname in CATS]
        # 只有真实 /category/ 分类支持 ?sort=views, 首页/热门不支持
        filters = {}
        for cid, _ in CATS:
            if not cid.startswith('__'):
                filters[cid] = SORTS
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        html = self._page(HOST + '/')
        return {'list': self._cards(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        tid = str(tid).strip()
        ext = extend if isinstance(extend, dict) else {}
        sort = str(ext.get('sort') or '').strip()

        # 站点导航里的 Home / Popular 不是 /category/ 路径
        if tid == '__home':
            url = HOST + '/' if page == 1 else HOST + '/page/%d/' % page
        elif tid == '__popular':
            url = (HOST + '/popular/' if page == 1
                   else HOST + '/popular/page/%d/' % page)
        else:
            base = HOST + '/category/' + tid
            # 尾斜杠形式更稳（无斜杠更容易触发 CF challenge）
            url = base + ('/' if page == 1 else '/page/%d/' % page)
            if sort:
                url += '?sort=' + urllib.parse.quote(sort)

        html = self._page(url)
        items = self._cards(html)
        if not items:                      # CF 间歇拦截兜底：再试两轮
            for _ in range(2):
                html = self._page(url, retries=2)
                items = self._cards(html)
                if items:
                    break
        return {
            'page': page,
            'pagecount': self._pagecount(html, page),
            'limit': len(items) or 24,
            'total': len(items),
            'list': items,
        }

    def searchContent(self, key, quick, pg="1"):
        page = max(1, int(pg or 1))
        kw = urllib.parse.quote(str(key))
        url = (HOST + '/?s=' + kw) if page == 1 else (HOST + '/page/%d/?s=%s' % (page, kw))
        html = self._page(url)
        items = self._cards(html)
        if not items:                      # CF 间歇拦截兜底
            for _ in range(2):
                html = self._page(url, retries=2)
                items = self._cards(html)
                if items:
                    break
        return {
            'page': page,
            'pagecount': self._pagecount(html, page),
            'limit': len(items) or 24,
            'total': len(items),
            'list': items,
        }

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, list) else ids)
        vid = re.sub(r'\D', '', vid.split('/')[-1].replace('.html', '')) or vid
        durl = HOST + '/' + vid + '.html'
        html = self._page(durl)

        title = ''
        tm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if tm:
            title = re.sub(r'<[^>]+>', '', tm.group(1))
            title = (title.replace('&amp;', '&').replace('&#8217;', "'")
                     .replace('&#8211;', '-')).strip()

        pic = ''
        pm = re.search(r'background-image:\s*url\((https://img\.supjav\.com/[^)]+)\)', html)
        if pm:
            pic = pm.group(1)
        if not pic:
            # 兜底: 页内任意 img.supjav.com 图片
            im = re.search(r'(https://img\.supjav\.com/[^\s"\'<>)]+\.(?:jpg|jpeg|png|webp)[^\s"\'<>)]*)',
                           html, re.I)
            if im:
                pic = im.group(1)
        if pic.startswith('//'):
            pic = 'https:' + pic
        if pic.startswith('http'):
            pic = SJ_IMG_API + urllib.parse.quote(pic, safe='')

        views = ''
        vm = re.search(r'<span class="views">([^<]+)</span>', html)
        if vm:
            views = vm.group(1).strip()

        # 标签 / 演员
        tags = []
        for _kind, slug in re.findall(r'href="' + re.escape(HOST) + r'/(tag|actress)/([^"/]+)', html):
            s = slug.replace('-', ' ').strip()
            if s and s not in tags:
                tags.append(s)
        year = ''
        ym = re.search(r'/images/(\d{4})/', html)
        if ym:
            year = ym.group(1)

        # 线路: data-link
        links = re.findall(r'data-link="([0-9a-f]{40,})"', html)
        names = re.findall(r'data-link="[0-9a-f]{40,}"[^>]*>([^<]{1,12})<', html)
        pairs = []
        for i, lk in enumerate(links):
            nm = names[i].strip() if i < len(names) else ('线路%d' % (i + 1))
            pairs.append((nm, '正片$%s|%s' % (vid, lk)))

        # 线路排序: VOE 优先(1080p/720p 直连稳), TV 垫底(需 PNG 剥头转流)
        # 数字越小越靠前, 未列出的线路排中间
        def _rank(nm):
            u = nm.strip().upper()
            return LINE_ORDER.get(u, 50)

        pairs.sort(key=lambda x: _rank(x[0]))
        froms = [p[0] for p in pairs]
        urls = [p[1] for p in pairs]

        content = title
        if tags:
            content += '\n标签: ' + ', '.join(tags[:10])

        vod = {
            'vod_id': vid,
            'vod_name': title or ('SupJav ' + vid),
            'vod_pic': pic,
            'vod_year': year,
            'vod_remarks': views,
            'vod_content': content[:600],
            'vod_play_from': '$$$'.join(froms) if froms else 'SupJav',
            'vod_play_url': '$$$'.join(urls) if urls else ('正片$%s|' % vid),
        }
        return {'list': [vod]}

    @staticmethod
    def _voe_decode(html):
        """VOE 系(tracylocalschool.com 等)混淆解包 → 返回 config dict

        混淆链路(实测): <script type="application/json"> 里的 payload
          1. 去掉哨兵串 @$ ^^ ~@ %? *~ !! #&
          2. rot13
          3. base64 解码
          4. 每字符 -3 (shift)
          5. 整串反转
          6. base64 解码 → JSON
        """
        m = re.search(
            r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
            html or '', re.S)
        if not m:
            return {}
        blk = m.group(1).strip()
        try:
            j = json.loads(blk)
            raw = j[0] if isinstance(j, list) and j else blk
        except Exception:
            raw = blk

        s = str(raw)
        for k in ('@$', '^^', '~@', '%?', '*~', '!!', '#&'):
            s = s.replace(k, '_')
        s = s.replace('_', '')

        def b64d(x):
            x = re.sub(r'[^A-Za-z0-9+/=]', '', x)
            x += '=' * (-len(x) % 4)
            return base64.b64decode(x).decode('utf-8', 'replace')

        try:
            t = b64d(codecs.encode(s, 'rot13'))
            t = ''.join(chr(ord(c) - 3) for c in t)
            t = b64d(t[::-1])
            cfg = json.loads(t)
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def _extract_stream(self, s2, ref):
        """从 step2 页面抽取播放地址。返回 (m3u8, direct_mp4)

        supjav 四条线路各不相同:
          TV  turboviplay  → 页内明文 m3u8
          FST premilkyway  → packer 解包后 m3u8
          ST  streamtape   → 二跳 embed 页, robotlink 拼接 get_video 直链
          VOE tracylocal.. → 二跳 + application/json 六层混淆, 取 source(m3u8)
        """
        # 1) 明文 m3u8
        hits = re.findall(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', s2)
        if hits:
            return hits[0], ''

        # 2) packer 解包
        if 'eval(function(p,a,c,k,e' in s2:
            dec = self._unpack(s2)
            hits = re.findall(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', dec)
            if hits:
                return hits[0], ''

        # 3) Streamtape: /e/<id> → robotlink 拼 get_video
        em = re.search(r'https?://streamtape\.com/e/([A-Za-z0-9]+)', s2)
        if em:
            eurl = 'https://streamtape.com/e/%s/' % em.group(1)
            page = self._stream(eurl, referer=HOST + '/')
            for pat in (r"innerHTML\s*=\s*'([^']+)'\s*\+\s*\('([^']+)'\)"
                        r"\.substring\((\d+)\)",
                        r'innerHTML\s*=\s*"([^"]+)"\s*\+\s*\("([^"]+)"\)'
                        r'\.substring\((\d+)\)'):
                mm = re.search(pat, page or '')
                if not mm:
                    continue
                link = mm.group(1) + mm.group(2)[int(mm.group(3)):]
                if link.startswith('//'):
                    link = 'https:' + link
                if 'dl=' not in link:
                    link += ('&dl=1' if '?' in link else '?dl=1')
                return '', link

        # 4) VOE 系: 二跳后解混淆 JSON
        tgt = re.findall(r"window\.location\.href\s*=\s*'([^']+)'", s2)
        tgt += re.findall(r'https?://[a-z0-9.-]+/e/[a-z0-9]{8,}', s2)
        if tgt:
            page = self._stream(tgt[0], referer=ref)
            cfg = self._voe_decode(page)
            src = str(cfg.get('source') or '')
            if '.m3u8' in src:
                return src, ''
            dau = str(cfg.get('direct_access_url') or '')
            if dau.startswith('http'):
                return '', dau
            if src.startswith('http'):
                return '', src

        return '', ''

    def playerContent(self, flag, id, vipFlags):
        raw = str(id)
        vid, _, lk = raw.partition('|')
        vid = re.sub(r'\D', '', vid) or vid
        detail = HOST + '/' + vid + '.html'
        fail = {'parse': 0, 'playUrl': '', 'url': '', 'jx': 0}

        if not lk:
            return fail

        # 命中解析缓存直接返回（三跳解析要 3~6s，切线路/重进详情不必重付）
        cached = self._play_cache_get(lk)
        if cached:
            return cached

        # step1: supjav.php?l=<hex>  (Referer=详情页) → 页内 OLID 反转
        s1_url = LK_BASE + '?l=' + lk
        s1 = self._stream(s1_url, referer=detail)
        olid = ''
        om = re.search(r"var\s+OLID\s*=\s*'([0-9a-f]{40,})'", s1 or '')
        if om:
            olid = om.group(1)[::-1]
        else:
            olid = lk[::-1]   # 兜底: JS 逻辑固定为反转 data-link

        # step2: supjav.php?c=<reversed>  (Referer=step1) → 各家播放页
        s2 = self._stream(LK_BASE + '?c=' + olid, referer=s1_url)
        if not s2:
            return fail

        m3u8, direct = self._extract_stream(s2, s1_url)

        if not m3u8 and not direct:
            return fail

        if direct:
            # Streamtape / VOE mp4 直链:
            #  - get_video 链接本身不绑 IP (VPS 取也 200), 但 302 终点
            #    tapecontent.net 绑 IP (VPS 取 403)
            #  - 不能走 /stream 代理: fetch_stream 会把整个 mp4(1.6GB) 读进内存,
            #    实测 502 超时
            #  → 直接把 get_video 链接交 TVBox, 由播放器自己跟 302 并发 Range 请求,
            #    这样最终 IP 就是 TVBox 自己的 IP, 与 302 签发方一致
            res = {
                'parse': 0,
                'playUrl': '',
                'url': direct,
                'jx': 0,
                'header': {'User-Agent': UA, 'Referer': HOST + '/'},
            }
            self._play_cache_put(lk, res)
            return res

        m3u8 = m3u8.replace('\\/', '/').replace('&amp;', '&')

        # 线路差异处理:
        #  - premilkyway (FST): 分片是真 TS, token 绑 IP → 必须走代理转流,
        #    否则 TVBox 客户端 IP 与取 token 的服务器 IP 不同, 分片 403
        #  - turbosplayer (TV): 分片伪装成 image/png 托在 googleusercontent,
        #    播放器不认 → 走 /sj_hls 拍平并剥 PNG 头
        low = m3u8.lower()
        if 'turbosplayer' in low or 'turboviplay' in low:
            play = SJ_HLS_API + urllib.parse.quote(m3u8, safe='')
        else:
            play = STREAM_API + urllib.parse.quote(m3u8, safe='')

        res = {
            'parse': 0,
            'playUrl': '',
            'url': play,
            'jx': 0,
            'header': {'User-Agent': UA},
        }
        self._play_cache_put(lk, res)
        return res
