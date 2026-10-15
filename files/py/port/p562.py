# -*- coding: utf-8 -*-
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

PARENT_GROUPS = [
    ("g_guochan", "国产自拍", [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35]),
    ("g_men", "门事件黑料", [36, 37, 38, 39, 40, 41, 42, 43]),
    ("g_zhifu", "制服诱惑", [44, 45, 46, 47, 48, 49, 50, 51]),
    ("g_lunli", "伦理片", [52, 53, 54, 55, 56, 57, 58, 59, 60]),
    ("g_zhibo", "直播专区", [61, 62, 63, 64, 65, 66, 71, 98]),
    ("g_gcav", "国产AV主播", [67, 68, 72]),
    ("g_oumei", "欧美专区", [69, 70, 73, 74, 75, 78]),
    ("g_zhongkou", "重口区", [76, 77, 79, 80, 81, 82]),
    ("g_dongman", "动漫专区", [83, 84, 85, 86, 87, 88, 89, 90]),
    ("g_riben", "日本AV", [91, 92, 93, 94, 95, 96, 97, 99, 100]),
]

CHILD_TYPES = {
    20: "学生少女", 21: "技师风采", 22: "熟女少妇", 23: "国产热播", 24: "反差母狗",
    25: "美脚丝足", 26: "情侣自拍", 27: "私房俱乐部", 28: "偷情约炮", 29: "真实偷拍",
    30: "高潮喷水", 31: "强奸迷奸", 32: "户外露出", 33: "SM调教", 34: "情趣内衣",
    35: "精选探花", 36: "网曝门事件", 37: "校园猛料", 38: "网红流出", 39: "明星黑料",
    40: "裸贷肉偿", 41: "婚闹恶俗", 42: "抓奸名场面", 43: "男同女同", 44: "JK少女",
    45: "黑丝白丝", 46: "女仆", 47: "cosplay", 48: "OL制服", 49: "旗袍",
    50: "空姐制服", 51: "护士医生", 52: "伦理之爱", 53: "禁忌母子", 54: "兄弟姐妹",
    55: "爱上嫂子", 56: "狂操小姨", 57: "换夫换妻", 58: "淫荡儿媳", 59: "爷爷奶奶",
    60: "伦理精选", 61: "啪啪直播", 62: "学生直播", 63: "自慰诱惑", 64: "乱伦直播",
    65: "户外勾搭", 66: "车震直播", 67: "国产AV", 68: "网红主播", 69: "欧美精选",
    70: "户外搭讪", 71: "美女自慰", 72: "乱伦直播②", 73: "黑人大屌", 74: "群P大作战",
    75: "欧美重口", 76: "人兽性交", 77: "SM性虐", 78: "人妖伪娘", 79: "孕妇内射",
    80: "吃屎喝尿", 81: "扩阴拳交", 82: "阳具巨物", 83: "3D动漫", 84: "同人动漫",
    85: "剧情故事", 86: "国产动漫", 87: "日韩动漫", 88: "欧美动漫", 89: "港台动漫",
    90: "海外动漫", 91: "日本中文", 92: "无码流出", 93: "FC2", 94: "HEYZO",
    95: "东京热", 96: "一本道", 97: "人妻斩", 98: "主播网黄", 99: "色情综艺",
    100: "情色AV",
}

YEARS = ["全部"] + [str(y) for y in range(2026, 2014, -1)]
LETTERS = ["全部"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
SORTS = [("time", "最新"), ("hits", "最热"), ("score", "评分")]
ROOT_TID = "19"

RE_ITEM = re.compile(
    r'<a[^>]+href="(?P<href>/index\.php/vod/detail/id/(?P<vid>\d+)\.html)"(?P<attrs>[^>]*)>'
    r'(?P<inner>[\s\S]*?)</a>', re.S)
RE_PAGE = re.compile(r'共(\d+)条数据[，,]?\s*当前(\d+)/(\d+)页')
RE_PAGE2 = re.compile(r'共(\d+)页')
RE_PLAYER = re.compile(r'player_aaaa\s*=\s*(\{[\s\S]{0,2000}?\})\s*(?:;|</script>)', re.S)
RE_M3U8 = re.compile(r'https?://[^\s"\'<>\\]+\.(?:m3u8|mp4)[^\s"\'<>\\]*')

RECT_178_STYLE = {"type": "rect", "ratio": 1.78}

class Spider(BaseSpider):

    def init(self, extend=""):
        self.host = "https://moj.ygxs.lol"
        if extend and isinstance(extend, str) and extend.startswith("http"):
            self.host = extend.rstrip("/")
        self.ua = "Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        self.timeout = 10.0

    def _get_ssl_context(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _get(self, url, referer=None):
        if url.startswith("/"):
            url = self.host + url
        elif not url.startswith("http"):
            url = urllib.parse.urljoin(self.host + "/", url)

        headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer if referer else (self.host + "/")
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._get_ssl_context()) as resp:
                raw_bytes = resp.read()
                for enc in ("utf-8", "gbk"):
                    try:
                        return raw_bytes.decode(enc)
                    except Exception:
                        continue
                return raw_bytes.decode("utf-8", "ignore")
        except Exception:
            return ""

    def _abs(self, pic):
        if not pic:
            return ""
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return self.host + pic
        return pic

    def _parse_list(self, h):
        out = []
        seen = set()
        for m in RE_ITEM.finditer(h or ""):
            inner = m.group("inner")
            if "<img" not in inner:
                continue
            vid = m.group("vid")
            if vid in seen:
                continue
            seen.add(vid)

            pic = ""
            for attr in ["data-original", "data-src", "src"]:
                mp = re.search(r'%s="([^"]+)"' % attr, inner)
                if mp and "loading" not in mp.group(1):
                    pic = self._abs(mp.group(1).strip())
                    break

            if not pic:
                mp = re.search(r'src="([^"]+)"', inner)
                if mp:
                    pic = self._abs(mp.group(1).strip())

            title = ""
            mt = re.search(r'title="([^"]*)"', m.group("attrs") or "")
            if mt:
                title = mt.group(1)
            if not title:
                mt = re.search(r'<img[^>]+title="([^"]*)"', inner)
                if mt:
                    title = mt.group(1)
            if not title:
                title = re.sub(r'<[^>]+>', '', inner)
            title = re.sub(r'\s+', ' ', title).strip()

            note = ""
            mn = re.search(r'<span>([^<]*)</span>', inner)
            if mn:
                note = mn.group(1).strip().strip(".")

            vod_remarks = "ZakaTV | %s" % note if note else "ZakaTV"

            out.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": vod_remarks,
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV",
                "style": RECT_178_STYLE
            })
        return out

    def _parse_page(self, h):
        m = RE_PAGE.search(h or "")
        if m:
            total, cur, pages = int(m.group(1)), int(m.group(2)), int(m.group(3))
            limit = int(total / pages) + (1 if total % pages else 0) if pages else 24
            return total, cur, max(pages, 1), max(limit, 1)
        m2 = RE_PAGE2.search(h or "")
        pages = int(m2.group(1)) if m2 else 1
        return 0, 1, max(pages, 1), 24

    def _strip(self, s):
        s = re.sub(r'<script[\s\S]*?</script>', ' ', s or '')
        s = re.sub(r'<[^>]+>', ' ', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        return re.sub(r'\s+', ' ', s).strip()

    def _parse_detail(self, h, vid):
        blk = ""
        m = re.search(r'<div class="media">([\s\S]*?)<div class="clearfix">', h or "")
        if m:
            blk = m.group(1)
        if not blk:
            blk = h or ""

        name = ""
        mt = re.search(r'片名[:：]\s*([^<\n]*)', blk)
        if mt:
            name = mt.group(1).strip()
        if not name:
            mt = re.search(r'<title>([^<]*)</title>', h or "")
            if mt:
                name = mt.group(1).split('详情')[0].strip()

        type_name = ""
        mt = re.search(r'类型[:：]\s*<a[^>]*>([^<]*)</a>', blk)
        if mt:
            type_name = self._strip(mt.group(1))

        pic = ""
        for attr in ["data-original", "data-src", "src"]:
            mp = re.search(r'<img[^>]+%s="([^"]+)"' % attr, blk)
            if mp and "loading" not in mp.group(1):
                pic = self._abs(mp.group(1).strip())
                break

        if not pic:
            mp = re.search(r'<img[^>]+src="([^"]+)"', blk)
            if mp:
                pic = self._abs(mp.group(1).strip())

        year = ""
        mt = re.search(r'年代[:：]?\s*(\d{4})', blk) or re.search(r'/search/year/(\d{4})\.html', blk)
        if mt:
            year = mt.group(1)

        tags = []
        for t in re.findall(r'/index\.php/vod/search/class/([^"\'?]+)\.html', blk):
            t = urllib.parse.unquote(t).strip()
            if t and t not in tags:
                tags.append(t)

        content = ""
        mt = re.search(r'简介[:：]\s*([^<\n]*)', blk)
        if mt:
            content = mt.group(1).strip()
        if not content:
            mt = re.search(r'name="description"\s+content="([^"]*)"', h or "")
            if mt:
                content = mt.group(1).strip()
        if content and name and content == name:
            content = name

        actor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        mt = re.search(r'主演[:：]\s*([^<\n]*)', blk)
        if mt and mt.group(1).strip():
            actor = "%s | 📺TG群: https://t.me/+3t5XRPPo9mlkZDRl" % mt.group(1).strip()

        director = "📺ZakaTV"
        mt = re.search(r'导演[:：]\s*([^<\n]*)', blk)
        if mt and mt.group(1).strip():
            director = "%s | 📺ZakaTV" % mt.group(1).strip()

        area = ""
        mt = re.search(r'地区[:：]\s*<a[^>]*>([^<]*)</a>', blk)
        if mt:
            area = self._strip(mt.group(1))

        plays = []
        seen = set()
        for sid, nid in re.findall(r'/index\.php/vod/play/id/%s/sid/(\d+)/nid/(\d+)\.html' % vid, h or ""):
            key = (sid, nid)
            if key in seen:
                continue
            seen.add(key)
            plays.append((sid, nid))
        plays.sort(key=lambda x: (int(x[0]), int(x[1])))

        urls = []
        if plays:
            by_sid = {}
            for sid, nid in plays:
                by_sid.setdefault(sid, []).append(nid)
            for sid in sorted(by_sid, key=lambda x: int(x)):
                eps = []
                for nid in by_sid[sid]:
                    ep = "正片" if len(by_sid[sid]) == 1 else "第%s集" % nid
                    ep_url = "/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (vid, sid, nid)
                    eps.append("%s$%s" % (ep, ep_url))
                urls.append("#".join(eps))
        else:
            ep_url = "/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid
            urls.append("正片$%s" % ep_url)

        play_from = "$$$".join(
            ["Zaka专线%s" % s for s in (sorted(set([x for x, _ in plays]), key=lambda v: int(v)) or ["1"])])

        full_content = "📺ZakaTV官方交流群：https://t.me/+3t5XRPPo9mlkZDRl\n%s" % (content if content else "暂无简介")

        vod_remarks = "ZakaTV | %s" % "|".join(tags) if tags else "ZakaTV"

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": type_name or (CHILD_TYPES.get(int(vid), "") if vid.isdigit() else ""),
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": full_content,
            "vod_remarks": vod_remarks,
            "vod_play_from": play_from,
            "vod_play_url": "$$$".join(urls),
        }
        return vod

    def _resolve_play(self, play_url):
        h = self._get(play_url, referer=self.host + "/")
        if not h:
            return ""
        raw = ""
        m = RE_PLAYER.search(h)
        if m:
            txt = m.group(1).replace('\\/', '/')
            try:
                j = json.loads(txt)
                raw = (j.get("url") or "").strip()
            except Exception:
                mm = re.search(r'"url"\s*:\s*"([^"]+)"', txt)
                if mm:
                    raw = mm.group(1).replace('\\/', '/')
        if not raw:
            mm = RE_M3U8.search(h.replace('\\/', '/'))
            if mm:
                raw = mm.group(0)
        if raw and not re.match(r'^https?://', raw):
            raw = urllib.parse.urljoin(self.host + "/", raw)
        return raw

    def playerContent(self, flag, id, vipFlags):
        url = id or ""
        if url.startswith("/") or (url.startswith("http") and 'vod/play/' in url):
            real = self._resolve_play(url)
            url = real or url
        elif not self.isVideoFormat(url):
            real = self._resolve_play(url)
            url = real or url
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": self.ua, "Referer": self.host + "/"},
            "jx": 0,
        }

    def _filters_for(self, tid):
        fl = []
        if str(tid).startswith("g_"):
            subs = []
            for gid, gname, tids in PARENT_GROUPS:
                if gid == tid:
                    subs.append({"n": "全部", "v": "all"})
                    for t in tids:
                        subs.append({"n": CHILD_TYPES.get(t, str(t)), "v": str(t)})
                    break
            if subs:
                fl.append({"key": "sub", "name": "子分类", "value": subs})
        fl.append({"key": "year", "name": "年代",
                   "value": [{"n": y, "v": y} for y in YEARS]})
        fl.append({"key": "letter", "name": "字母",
                   "value": [{"n": l, "v": l} for l in LETTERS]})
        fl.append({"key": "by", "name": "排序",
                   "value": [{"n": n, "v": v} for v, n in SORTS]})
        return fl

    def homeContent(self, filter):
        classes = [
            {"type_id": "new", "type_name": "最近更新"},
            {"type_id": ROOT_TID, "type_name": "全部影片"},
        ]
        for gid, gname, tids in PARENT_GROUPS:
            classes.append({"type_id": gid, "type_name": gname})
        for tid in sorted(CHILD_TYPES.keys()):
            classes.append({"type_id": str(tid), "type_name": CHILD_TYPES[tid]})

        filters = {}
        if filter:
            for c in classes:
                filters[c["type_id"]] = self._filters_for(c["type_id"])

        return {
            "class": classes,
            "filters": filters,
            "list": [],
            "style": RECT_178_STYLE
        }

    def homeVideoContent(self):
        return {"list": []}

    def _ext(self, extend, key, default=""):
        if not extend:
            return default
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                return default
        if isinstance(extend, dict):
            v = extend.get(key, default)
            return default if v is None else str(v)
        return default

    def _build_list_url(self, tid, pg, year="", letter="", by=""):
        base = "/index.php/vod/type/id/%s" % tid
        if year and year != "全部":
            base += "/year/%s" % urllib.parse.quote(str(year))
        if letter and letter != "全部":
            base += "/letter/%s" % urllib.parse.quote(str(letter))
        if by and by in ("hits", "time", "score"):
            base += "/by/%s" % by
        base += "/page/%s.html" % pg
        return base

    def _fetch_list(self, tid, pg, year="", letter="", by=""):
        h = self._get(self._build_list_url(tid, pg, year, letter, by))
        lst = self._parse_list(h)
        total, cur, pages, limit = self._parse_page(h)
        return lst, cur, pages, limit

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        year = self._ext(extend, "year", "全部")
        letter = self._ext(extend, "letter", "全部")
        by = self._ext(extend, "by", "time")
        sub = self._ext(extend, "sub", "")
        if by == "全部":
            by = ""

        if tid == "new":
            lst, cur, pages, limit = self._fetch_list(ROOT_TID, pg, year, letter, by)
            return {
                "list": lst,
                "page": cur,
                "pagecount": pages,
                "limit": limit,
                "total": pages * limit if pages else len(lst),
                "style": RECT_178_STYLE
            }

        if tid.startswith("g_"):
            target_tid = ""
            if sub and sub != "all" and sub.isdigit():
                target_tid = sub
            else:
                for gid, gname, ts in PARENT_GROUPS:
                    if gid == tid:
                        target_tid = str(ts[0]) if ts else ""
                        break
            if not target_tid:
                return {
                    "list": [],
                    "page": pg,
                    "pagecount": 1,
                    "limit": 0,
                    "total": 0,
                    "style": RECT_178_STYLE
                }

            lst, cur, pages, limit = self._fetch_list(target_tid, pg, year, letter, by)
            return {
                "list": lst,
                "page": cur,
                "pagecount": pages,
                "limit": limit,
                "total": pages * limit if pages else len(lst),
                "style": RECT_178_STYLE
            }

        if tid.isdigit() and sub.isdigit() and sub != tid:
            tid = sub
        lst, cur, pages, limit = self._fetch_list(tid, pg, year, letter, by)
        return {
            "list": lst,
            "page": cur,
            "pagecount": pages,
            "limit": limit,
            "total": pages * limit if pages else len(lst),
            "style": RECT_178_STYLE
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0] if isinstance(ids, list) else ids)
        vid = re.sub(r'\D', '', vid)
        if not vid:
            return {"list": []}
        h = self._get("/index.php/vod/detail/id/%s.html" % vid)
        if not h:
            return {"list": []}
        return {"list": [self._parse_detail(h, vid)]}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        url = "/index.php/vod/search.html?wd=%s&page=%s" % (urllib.parse.quote(key or ""), pg)
        h = self._get(url, referer=self.host + "/")
        lst = self._parse_list(h)
        total, cur, pages, limit = self._parse_page(h)
        if not lst and '%' in (key or ''):
            h = self._get("/index.php/vod/search/wd/%s/page/%s.html" % (urllib.parse.quote(key or ""), pg))
            lst = self._parse_list(h)
        return {
            "list": lst,
            "page": pg,
            "pagecount": pages,
            "limit": limit,
            "total": total,
            "style": RECT_178_STYLE
        }

    def action(self, action):
        return ""

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [200, "text/plain", ""]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I))

    def destroy(self):
        pass