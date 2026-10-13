# -*- coding: utf-8 -*-
import re
import json
import base64
import urllib.request
import urllib.parse
import ssl

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

try:
    from Crypto.Cipher import AES as FastAES
except Exception:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        class FastAESWrapper(object):
            def __init__(self, key, iv):
                self.key = key
                self.iv = iv
            def decrypt(self, data):
                c = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).decryptor()
                return c.update(data) + c.finalize()
        FastAES = FastAESWrapper
    except Exception:
        FastAES = None

class Spider(BaseSpider):

    HOST = "https://91crdjai.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    CHANNELS = [
        ("duanju", "成人短剧", True),
        ("manju", "成人漫剧", False),
        ("zhenrenju", "真人剧", False),
        ("shipin", "成人视频", True),
        ("paihang", "热播榜", True)
    ]

    IMG_KEY_RAW = "102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48"
    IMG_IV_RAW = "57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49"

    TAGS = [
        ('aiduanju', 'AI短剧'), ('aichengrenduanju', 'AI成人短剧'), ('91chengrenduanju', '91成人短剧'), ('aishipin', 'AI视频'),
        ('juru', '巨乳'), ('houru', '后入'), ('gaoyanzhi', '高颜值'), ('aichengrenxiaoshuo', 'AI成人小说'), ('fancha', '反差'),
        ('mugou', '母狗'), ('youhuo', '诱惑'), ('meiru', '美乳'), ('koujiao', '口交'), ('zhongchu', '中出'), ('juqing', '剧情'),
        ('xinggan', '性感'), ('aimogai', 'AI魔改'), ('diaojiao', '调教'), ('meitui', '美腿'), ('nvshen', '女神'),
        ('zipai', '自拍'), ('ai', 'AI'), ('dantimogai', '单体魔改'), ('mote', '模特'), ('aimeinv', 'ai美女'), ('jipin', '极品'),
        ('siwa', '丝袜'), ('gufeng', '古风'), ('nvshangwei', '女上位'), ('shenhou', '深喉')
    ]

    def __init__(self):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.HOST + "/",
            "Connection": "keep-alive"
        }
        self._meta = {}
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def getName(self):
        return "91成人短剧"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return None

    def liveContent(self):
        return ""

    def _fetch(self, url, ajax=False, referer=None, timeout=12):
        hdrs = dict(self.headers)
        if ajax:
            hdrs["X-Requested-With"] = "XMLHttpRequest"
        if referer:
            hdrs["Referer"] = referer

        req = urllib.request.Request(url, headers=hdrs)
        try:
            res = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout)
            raw = res.read()
            try:
                return raw.decode("utf-8")
            except Exception:
                return raw.decode("gbk", errors="ignore")
        except Exception:
            return ""

    def _fetch_bin(self, url, timeout=10):
        req = urllib.request.Request(url, headers=self.headers)
        try:
            res = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout)
            return res.read()
        except Exception:
            return b""

    @staticmethod
    def e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def d64(s):
        s = str(s or "")
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4)).decode("utf-8")

    @classmethod
    def _img_key_iv(cls):
        def conv(raw):
            return "".join([chr(int(x)) for x in raw.split("_")]).encode("utf-8")
        return conv(cls.IMG_KEY_RAW), conv(cls.IMG_IV_RAW)

    def img_decrypt(self, body):
        key, iv = self._img_key_iv()
        data = body[:len(body) - len(body) % 16]
        if not data:
            return body

        if FastAES is not None:
            try:
                if hasattr(FastAES, 'MODE_CBC'):
                    cipher = FastAES.new(key, FastAES.MODE_CBC, iv)
                    return cipher.decrypt(data)
                else:
                    cipher = FastAES(key, iv)
                    return cipher.decrypt(data)
            except Exception:
                pass

        return body

    def proxy_url(self):
        try:
            u = self.getProxyUrl()
            return u if u else "http://127.0.0.1:9978/proxy?do=py"
        except Exception:
            return "http://127.0.0.1:9978/proxy?do=py"

    def proxy_img(self, url):
        if not url or not url.startswith("http"):
            return url or ""
        return "%s&type=img&url=%s" % (self.proxy_url(), self.e64(url))

    @staticmethod
    def _unesc(s):
        s = s or ""
        for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
            s = s.replace(a, b)
        return s.strip()

    @classmethod
    def _norm_ids(cls, ids):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        v = str(ids or "").strip().split("#")[0].strip()
        if v.count("|") >= 2:
            return v.replace("|", ".")
        if v.count(".") >= 2 and "/" not in v:
            return v
        m = re.search(r'/(duanju|manju|zhenrenju|shipin)/(\d+)-([a-z0-9-]+)', v)
        if m:
            return "%s.%s.%s" % (m.group(1), m.group(2), m.group(3))
        return v

    @staticmethod
    def split_id(vid):
        p = str(vid or "").replace("|", ".").split(".")
        while len(p) < 3:
            p.append("")
        return p[0], p[1], p[2]

    def detail_url(self, vid):
        ch, i, slug = self.split_id(vid)
        return "%s/%s/%s-%s/" % (self.HOST, ch, i, slug)

    def parse_cards(self, html):
        vods = []
        if not html:
            return vods
        seen = set()
        for m in re.finditer(r'<a class="card"\s+href="([^"]+)"([\s\S]{0,1800}?)</a>', html):
            href, blk = m.group(1), m.group(2)
            g = re.search(r'/(duanju|manju|zhenrenju|shipin)/(\d+)-([a-z0-9-]+)/', href)
            if not g:
                continue
            vid = "%s.%s.%s" % (g.group(1), g.group(2), g.group(3))
            if vid in seen:
                continue
            seen.add(vid)
            name = self._unesc((re.search(r'data-track-item-name="([^"]*)"', blk) or [None, ""])[1]) \
                or self._unesc((re.search(r'<h3>([^<]*)</h3>', blk) or [None, ""])[1])
            pic_raw = self._unesc((re.search(r'data-src="([^"]+)"', blk) or [None, ""])[1])
            pic = self.proxy_img(pic_raw)
            flag = self._unesc((re.search(r'class="eps-flag">([^<]*)<', blk) or [None, ""])[1])
            badge = self._unesc((re.search(r'<span class="badge[^"]*">([^<]*)</span>', blk) or [None, ""])[1])
            score = self._unesc((re.search(r'class="score">([^<]*)<', blk) or [None, ""])[1])

            raw_rm = " · ".join([x for x in (flag or badge, score) if x])
            remarks = "ZakaTV | %s" % raw_rm if raw_rm else "ZakaTV"

            self._meta[vid] = {"name": name, "pic": pic, "remark": remarks}
            vods.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })
        return vods

    @staticmethod
    def max_page(html):
        pages = [int(x) for x in re.findall(r'/page/(\d+)/', html or "")]
        return max(pages) if pages else 1

    def homeContent(self, filter=False):
        classes = [{"type_id": t, "type_name": n} for t, n, _ in self.CHANNELS]
        filters = {}
        sort_f = {
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最新", "v": "new"}, {"n": "最热", "v": "hot"}]
        }
        tag_f = {
            "key": "tag",
            "name": "标签",
            "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": s} for s, n in self.TAGS]
        }
        for t, _, _ in self.CHANNELS:
            filters[t] = [sort_f, tag_f] if t != "paihang" else [tag_f]

        return {
            "class": classes,
            "filters": filters
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend or {}
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        tag = (extend.get("tag") or "").strip()
        sort = (extend.get("sort") or "").strip()

        if tag:
            url = "%s/biaoqian/%s/" % (self.HOST, tag)
            if page > 1:
                url += "page/%d/" % page
        else:
            url = "%s/%s/" % (self.HOST, tid)
            if page > 1:
                url += "page/%d/" % page
            if sort and sort != "new":
                url += "?sort=%s" % urllib.parse.quote(sort)

        html = self._fetch(url)
        vods = self.parse_cards(html)
        pc = self.max_page(html)
        if not vods and page > 1:
            pc = page - 1

        return {
            "code": 1,
            "msg": "数据列表",
            "list": vods,
            "page": page,
            "pagecount": max(pc, page if vods else 1),
            "limit": 24,
            "total": max(pc, 1) * 24
        }

    def detailContent(self, ids):
        vid = self._norm_ids(ids)
        ch, sid, slug = self.split_id(vid)
        if not ch or not sid:
            return {"code": 0, "msg": "无数据", "list": []}

        base_url = self.detail_url(vid)
        html = self._fetch(base_url)
        cached = self._meta.get(vid, {})

        title = self._unesc((re.search(r'<h1 class="detail-title">([^<]*)', html) or [None, ""])[1]) \
            or cached.get("name") or slug
        pic_raw = self._unesc((re.search(r'class="p-img"[^>]*data-src="([^"]+)"', html) or [None, ""])[1])
        pic = self.proxy_img(pic_raw) if pic_raw else (cached.get("pic") or "")
        desc = re.sub(r'<[^>]+>', '', (re.search(r'id="viBody">([\s\S]*?)</p>', html) or [None, ""])[1])
        desc = self._unesc(re.sub(r'\s+', ' ', desc))
        score = self._unesc((re.search(r'class="rv">([^<]*)', html) or [None, ""])[1])

        tags = []
        for slug2, name in re.findall(r'/biaoqian/([a-z0-9]+)/"[^>]*>([^<]{1,24})</a>', html):
            n = self._unesc(name)
            if slug2 == "suiji" or not n or n in tags:
                continue
            tags.append(n)

        meta = {}
        for k, v in re.findall(r'<dt>([^<]+)</dt><dd>(?:<a[^>]*>)?([^<]*)', html):
            meta[self._unesc(k)] = self._unesc(v)
        times = re.findall(r'<time datetime="([^"]+)"', html)

        raw_rm = " · ".join([x for x in (
            meta.get("状态", ""), meta.get("集数", ""),
            ("热度 " + meta["热度"]) if meta.get("热度") else "",
            ("★" + score) if score else ""
        ) if x])
        remarks = "ZakaTV | %s" % raw_rm if raw_rm else "ZakaTV"

        eps = sorted(set([int(x) for x in re.findall(r'href="[^"]*/%s-%s/(\d+)/"' % (sid, re.escape(slug)), html)]))
        if not eps:
            eps = sorted(set([int(x) for x in re.findall(r'href="[^"]*/(\d+)/"[^>]*>\s*\d+\s*</a>', html)]))
        if not eps:
            eps = [1]

        ep_titles = {}
        pd = self.play_data(vid, eps[0])
        if pd:
            for e in (pd.get("eps") or []):
                try:
                    ep_titles[int(e.get("n"))] = self._unesc(e.get("title") or "")
                except Exception:
                    pass
            if not pic:
                pic = self.proxy_img(pd.get("poster") or "")
            if not desc:
                desc = self._unesc(pd.get("description") or "")

        items = []
        for n in eps:
            nm = ep_titles.get(n) or ("第%d集" % n)
            nm = re.sub(r'[$#]', ' ', nm)
            items.append("%s$%s@%d" % (nm, vid, n))

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": meta.get("分类", "") or ", ".join(tags[:3]),
            "vod_year": (times[0][:4] if times else ""),
            "vod_area": "国产",
            "vod_lang": "国语",
            "vod_remarks": remarks,
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": "📺官方交流群: https://t.me/+3t5XRPPo9mlkZDRl | 严禁盗卖，完全免费！\n\n%s" % desc,
            "vod_tag": ", ".join(tags[:20]),
            "vod_play_from": "Zaka专线",
            "vod_play_url": "#".join(items)
        }

        return {
            "code": 1,
            "msg": "数据列表",
            "list": [vod],
            "page": 1,
            "pagecount": 1,
            "limit": 1,
            "total": 1
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        kw = str(key or "").strip()
        if not kw:
            return {"code": 0, "msg": "无数据", "list": []}

        url = "%s/search/?kw=%s" % (self.HOST, urllib.parse.quote(kw))
        if page > 1:
            url += "&page=%d" % page
        html = self._fetch(url)
        vods = self.parse_cards(html)

        if not vods and page == 1:
            for slug, name in self.TAGS:
                if kw in name or kw.lower() == slug:
                    vods = self.parse_cards(self._fetch("%s/biaoqian/%s/" % (self.HOST, slug)))
                    break

        return {
            "code": 1,
            "msg": "数据列表",
            "list": vods,
            "page": page,
            "pagecount": page + 1 if vods else page,
            "limit": 24,
            "total": 999999
        }

    def play_data(self, vid, ep):
        ch, sid, slug = self.split_id(vid)
        url = "%s/%s/%s-%s/%s/" % (self.HOST, ch, sid, slug, ep)
        html = self._fetch(url, referer=self.detail_url(vid))
        m = re.search(r'<script id="playInitialData"[^>]*>([\s\S]*?)</script>', html or "")
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def playback(self, sid, ep, referer=None):
        url = "%s/videos/%s/episodes/%s/playback" % (self.HOST, sid, ep)
        txt = self._fetch(url, ajax=True, referer=referer or (self.HOST + "/"), timeout=15)
        if not txt:
            return {}
        try:
            j = json.loads(txt)
        except Exception:
            return {}
        return (j.get("data") or {}) if j.get("status") in (1, "1", True) else (j.get("data") or {})

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        if raw.startswith("http"):
            return {
                "parse": 0,
                "url": raw,
                "header": {"User-Agent": self.UA}
            }

        vid, _, ep = raw.partition("@")
        vid = self._norm_ids(vid)
        ch, sid, slug = self.split_id(vid)
        ep = ep or "1"

        url = ""
        d = self.playback(sid, ep, referer=self.detail_url(vid))
        if d:
            url = d.get("src") or d.get("srcHevc") or ""

        if not url:
            pd = self.play_data(vid, ep)
            cur = (pd.get("current") or {}) if pd else {}
            url = cur.get("src") or cur.get("srcHevc") or ""

        if not url:
            return {"parse": 0, "url": "", "header": {}}

        url = self._unesc(url)
        return {
            "parse": 0,
            "url": url,
            "header": {
                "User-Agent": self.UA,
                "Referer": self.HOST + "/"
            }
        }

    def localProxy(self, params):
        params = params or {}
        ptype = str(params.get("type") or "img")
        raw = params.get("url") or ""
        try:
            url = self.d64(raw)
        except Exception:
            url = str(raw)
        if not url.startswith("http") or ptype != "img":
            return [404, "text/plain", b""]

        body = self._fetch_bin(url)
        if not body:
            return [502, "text/plain", b""]

        out = self.img_decrypt(body)
        ct = "image/jpeg"
        if out[:8] == b'\x89PNG\r\n\x1a\n':
            ct = "image/png"
        elif out[:3] == b'GIF':
            ct = "image/gif"
        elif out[:4] == b'RIFF' and out[8:12] == b'WEBP':
            ct = "image/webp"
        elif out[:2] != b'\xff\xd8':
            out = body
            ct = "image/jpeg"

        return [200, ct, out]
