# coding=utf-8
#!/usr/bin/env python3
"""红果听书 · 官方 App 接口版
======================================================================
数据来源：红果免费短剧官方 App（com.phoenix.read 7.3.7.32）解包扒出的 RPC 接口，
          不是官网 SEO 站。
  · 书单      /reading/bookapi/bookmall/homepage/v1/     （书名/封面/简介/评分/收听数）
  · 音色      /reading/bookapi/audio/toneinfo/           （多角色对话/成熟男声…）
  · 章节目录  fanqienovel.com/api/reader/directory/detail （App 侧目录对游客空返回，走 web 侧口）
  · 音频流    POST /reading/bookapi/audio/playurl/       （data.main_url，带时效签名，每次实时取）
通用参数 aid=1967 & app_name=novelapp，不需要 x-argus/x-gorgon 签名，裸请求即 200。
======================================================================
"""

import json
import re
import sys
import time
from urllib.parse import quote

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        pass

APP_UA = "com.dragon.read/73732 (Linux; U; Android 13; zh_CN; Pixel 6; Build/TQ3A)"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 接入点轮换：单点打多了会被限流
TTS_BASE = "https://tts.ystv.top"
# 自建朗读音色（官方音轨是 CENC + Intertrust DRM 加密流，第三方播放器拿到的是密文）
VOICES = [
    ("YunxiNeural", "\u2601\ufe0f 云希 · 青年男声"),
    ("YunyangNeural", "\U0001f4e2 云扬 · 播报男声"),
    ("YunjianNeural", "\U0001f4aa 云健 · 浑厚男声"),
    ("XiaoxiaoNeural", "\U0001f338 晓晓 · 温柔女声"),
    ("XiaoyiNeural", "\U0001f380 晓伊 · 甜美女声"),
    ("XiaobeiNeural", "\U0001f35c 晓北 · 东北女声"),
]

HOSTS = [
    "https://api5-normal-sinfonlineb.fqnovel.com",
    "https://api5-normal-sinfonlinea.fqnovel.com",
    "https://api.fqnovel.com",
]

COMMON = ("aid=1967&app_name=novelapp&version_code=73732&version_name=7.3.7.32"
          "&device_platform=android&os_version=13&channel=hongguo_android"
          "&device_id=8666886688668866&iid=8666886688668866")

WEB_DIR = "https://fanqienovel.com/api/reader/directory/detail?bookId="
WEB_PAGE = "https://fanqienovel.com/page/"

HOME_TTL = 600      # 首页 JSON 280KB+，缓存 10 分钟
DIR_TTL = 1800      # 目录缓存 30 分钟
FALLBACK_CATS = [
    ("c1", "现代都市"), ("c2", "异世玄幻"), ("c3", "悬疑推理"), ("c4", "历史穿越"),
    ("c5", "武侠仙侠"), ("c6", "科幻末世"), ("c7", "青春甜宠"), ("c8", "宫斗宅斗"),
]


class Spider(BaseSpider):

    def getName(self):
        return "红果听书"

    def init(self, extend=""):
        self._sess = requests.Session()
        self._sess.headers.update({"Accept": "application/json, text/plain, */*"})
        self._home = None
        self._home_ts = 0.0
        self._dirs = {}
        self._metas = {}
        self._idx = 0
        return None

    # ──────────────── 网络层 ────────────────

    def _host(self):
        h = HOSTS[abs(self._idx) % len(HOSTS)]
        self._idx += 1
        return h

    def _app_get(self, path):
        full = path + ("&" if "?" in path else "?") + COMMON
        for _ in range(len(HOSTS)):
            h = self._host()
            try:
                r = self._sess.get(h + full, headers={"User-Agent": APP_UA},
                                   timeout=20)
                if r.status_code == 200 and len(r.text) > 2:
                    return r.text
                if r.status_code == 200 and len(r.text) <= 2:
                    return ""
            except Exception:
                pass
            time.sleep(0.5)
        return None

    def _app_post(self, path, body):
        full = path + ("&" if "?" in path else "?") + COMMON
        for _ in range(len(HOSTS)):
            h = self._host()
            try:
                r = self._sess.post(h + full, data=json.dumps(body),
                                    headers={"User-Agent": APP_UA,
                                             "Content-Type": "application/json; charset=utf-8"},
                                    timeout=20)
                if r.status_code == 200 and len(r.text) > 2:
                    return r.text
            except Exception:
                pass
            time.sleep(0.5)
        return None

    def _web_get(self, url):
        try:
            r = self._sess.get(url, headers={"User-Agent": WEB_UA,
                                             "Accept-Language": "zh-CN,zh;q=0.9",
                                             "Referer": "https://fanqienovel.com/"},
                               timeout=25)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""

    # ──────────────── 首页数据 ────────────────

    def _home_raw(self):
        now = time.time()
        if self._home and (now - self._home_ts) < HOME_TTL:
            return self._home
        j = self._app_get("/reading/bookapi/bookmall/homepage/v1/")
        if j and len(j) > 200:
            self._home = j
            self._home_ts = now
        return j

    def _collect_books(self, node, out, depth=0):
        if node is None or depth > 6 or len(out) > 120:
            return
        if isinstance(node, dict):
            bid = str(node.get("book_id") or "")
            bn = str(node.get("book_name") or "")
            if len(bid) > 10 and bn and len(str(node.get("thumb_url") or "")) > 4:
                out.append(node)
                return
            for v in node.values():
                self._collect_books(v, out, depth + 1)
        elif isinstance(node, list):
            for v in node:
                self._collect_books(v, out, depth + 1)

    def _cells(self):
        out = []
        raw = self._home_raw()
        if not raw or len(raw) < 10:
            return out
        try:
            root = json.loads(raw)
        except Exception:
            return out
        cells = root.get("data") or []
        if not isinstance(cells, list):
            return out
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            name = str(cell.get("cell_name") or "")
            if not name:
                continue
            books = []
            self._collect_books(cell, books, 0)
            if len(books) >= 3:
                out.append((name, books))
        return out

    def _find_book(self, book_id):
        for _name, books in self._cells():
            for b in books:
                if str(b.get("book_id") or "") == book_id:
                    return b
        return None

    # ──────────────── 数据加工 ────────────────

    @staticmethod
    def _remarks(b):
        out = []
        try:
            sc = float(b.get("score") or 0)
        except Exception:
            sc = 0
        if sc > 0:
            out.append(("%g" % sc) + "分")
        lc = str(b.get("listen_count") or "")
        if lc and lc != "0":
            out.append(lc + "人在听")
        cs = str(b.get("creation_status") or "")
        if cs == "0":
            out.append("连载")
        elif cs:
            out.append("完结")
        return " · ".join(out)

    def _book_vod(self, b):
        pic = str(b.get("thumb_url") or "") or str(b.get("audio_thumb_uri") or "")
        return {
            "vod_id": str(b.get("book_id") or ""),
            "vod_name": str(b.get("book_name") or ""),
            "vod_pic": pic,
            "vod_year": "",
            "vod_area": "听书",
            "vod_remarks": self._remarks(b),
            "vod_content": str(b.get("abstract") or ""),
        }

    # ──────────────── 壳入口 ────────────────

    def homeContent(self, filter=False):
        classes = []
        cells = self._cells()
        if cells:
            for i, (name, _books) in enumerate(cells):
                nm = name[:12]
                classes.append({"type_id": "cell:%d" % i, "type_name": "🎧 " + nm})
        else:
            classes = [{"type_id": cid, "type_name": "🎧 " + nm} for cid, nm in FALLBACK_CATS]
        out = {"class": classes}
        if cells:
            out["list"] = [self._book_vod(b) for b in cells[0][1]]
        return out

    def homeVideoContent(self):
        lst = []
        for _name, books in self._cells():
            for b in books:
                lst.append(self._book_vod(b))
                if len(lst) >= 30:
                    break
            if len(lst) >= 30:
                break
        return {"list": lst}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = int(str(pg or 1))
        except Exception:
            page = 1
        if page < 1:
            page = 1
        lst = []
        cells = self._cells()
        if page <= 1:
            idx = -1
            t = str(tid or "")
            if t.startswith("cell:"):
                try:
                    idx = int(t[5:])
                except Exception:
                    idx = -1
            if 0 <= idx < len(cells):
                lst = [self._book_vod(b) for b in cells[idx][1]]
            else:
                for _name, books in cells:
                    lst.extend([self._book_vod(b) for b in books])
                    if len(lst) > 40:
                        break
        return {"page": page, "pagecount": page if page > 1 else 1,
                "limit": 20, "total": len(lst), "list": lst}

    def detailContent(self, ids):
        if not isinstance(ids, list):
            ids = [ids]
        book_id = self._clean_id(ids[0] if ids else "")
        name, pic, intro, score = "", "", "", ""
        hit = self._find_book(book_id)
        if hit:
            name = str(hit.get("book_name") or "")
            pic = str(hit.get("thumb_url") or "") or str(hit.get("audio_thumb_uri") or "")
            intro = str(hit.get("abstract") or "")
            score = str(hit.get("score") or "")
        if not name:
            name, pic, intro = self._web_meta(book_id)

        froms = [str(v[0]) + "|" + str(v[1]) for v in VOICES]

        chapters = self._chapters(book_id)
        groups = []
        for _f in froms:
            parts = []
            for iid, title in chapters:
                parts.append(title + "$" + book_id + "|" + iid)
            groups.append("#".join(parts))

        content = intro
        if score:
            content += ("\n\n评分：" + score)
        content += "\n\n数据来源：红果 App 接口（aid=1967）· 音轨为官方 TTS 合成"
        vod = {
            "vod_id": book_id,
            "vod_name": name or ("红果听书 " + book_id),
            "vod_pic": pic,
            "vod_year": "",
            "vod_area": "听书",
            "vod_remarks": ("%d 集 · %d 音色" % (len(chapters), len(froms))) if chapters else "音色可选",
            "vod_content": content.strip(),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(groups),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        lst = []
        try:
            kw = quote(str(key or ""), safe="")
            raw = self._app_get("/reading/bookapi/search/search/v1/?query=%s&page=0&need_bookinfo=1" % kw)
            if raw and len(raw) > 10:
                data = (json.loads(raw) or {}).get("data") or {}
                books = data.get("book_list") or data.get("books") or data.get("search_data") or []
                for b in books:
                    if isinstance(b, dict):
                        lst.append(self._book_vod(b))
        except Exception:
            pass
        # App 搜索口对游客偶发空返回 → 退回首页本地过滤，保证搜得到
        if not lst and key:
            k = str(key)
            for _name, books in self._cells():
                for b in books:
                    if k in str(b.get("book_name") or "") or k in str(b.get("author") or ""):
                        lst.append(self._book_vod(b))
                    if len(lst) >= 30:
                        break
                if len(lst) >= 30:
                    break
        return {"list": lst}

    def playerContent(self, flag, id, vipFlags=None):
        book_id, item_id = "", ""
        s = str(id or "")
        if "|" in s:
            book_id, item_id = s.split("|", 1)
        else:
            book_id = self._clean_id(s)
        if not item_id:
            chs = self._chapters(book_id)
            if chs:
                item_id = chs[0][0]
        item_id = self._clean_id(item_id)
        if len(str(item_id)) < 5:
            return {"parse": 0, "playUrl": "", "url": "", "msg": "该章节暂取不到音轨，换一集再试"}
        return {"parse": 0, "playUrl": "", "url":
                TTS_BASE + "/hg/audio?item=" + str(item_id) + "&v=" + self._voice_of(flag)}

    @staticmethod
    def _voice_of(flag):
        f = str(flag or "").strip()
        for v in VOICES:
            if v[0].lower() == f.lower():
                return v[0]
        for v in VOICES:
            if v[0] in f:
                return v[0]
        return VOICES[0][0]

    # ──────────────── 目录 / 音色 / 元数据 ────────────────

    def _chapters(self, book_id):
        if not book_id or len(book_id) < 10:
            return []
        c = self._dirs.get(book_id)
        if c and (time.time() - c[1]) < DIR_TTL:
            return c[0]
        out = []
        raw = self._web_get(WEB_DIR + book_id)
        if raw and len(raw) > 20:
            try:
                data = (json.loads(raw) or {}).get("data") or {}
                for vol in (data.get("chapterListWithVolume") or []):
                    for ch in (vol or []):
                        if not isinstance(ch, dict):
                            continue
                        iid = str(ch.get("itemId") or "")
                        title = str(ch.get("title") or "")
                        if len(iid) > 5:
                            out.append((iid, title or ("第%d章" % (len(out) + 1))))
                if not out:
                    for i, iid in enumerate(data.get("allItemIds") or []):
                        if len(str(iid)) > 5:
                            out.append((str(iid), "第%d章" % (i + 1)))
            except Exception:
                pass
        if out:
            self._dirs[book_id] = (out, time.time())
            if len(self._dirs) > 30:
                self._dirs.clear()
                self._dirs[book_id] = (out, time.time())
        return out

    def _tones(self, book_id):
        out = []
        try:
            raw = self._app_get("/reading/bookapi/audio/toneinfo/?book_id=" + str(book_id))
            if raw and len(raw) > 20:
                data = (json.loads(raw) or {}).get("data") or {}
                for t in (data.get("tts_tones") or [])[:8]:
                    if isinstance(t, dict):
                        out.append((str(t.get("id") or ""), str(t.get("title") or "音色")))
        except Exception:
            pass
        return [t for t in out if t[0]]

    def _web_meta(self, book_id):
        c = self._metas.get(book_id)
        if c and (time.time() - c[1]) < DIR_TTL:
            return c[0]
        name, pic, intro = "", "", ""
        html = self._web_get(WEB_PAGE + str(book_id))
        if html and len(html) > 100:
            m = re.search(r"<title>([^<]{2,120})</title>", html)
            if m:
                t = m.group(1)
                cut = t.find("完整版")
                if cut > 0:
                    t = t[:cut]
                name = t.replace("_番茄小说官网", "").strip()
            m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if m:
                pic = m.group(1)
            if not pic:
                m = re.search(r'"thumb_url":"([^"]{10,200})"', html)
                if m:
                    pic = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
            m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]{5,600})"', html)
            if m:
                intro = m.group(1)
        val = (name, pic, intro)
        self._metas[book_id] = (val, time.time())
        return val

    # ──────────────── 小工具 ────────────────

    @staticmethod
    def _clean_id(s):
        m = re.search(r"(\d{12,25})", str(s or ""))
        return m.group(1) if m else str(s or "").strip()

    @staticmethod
    def _num(s):
        """服务端这几个字段是 long，必须给数字，给字符串会 PARAM_INVALID"""
        s = str(s or "").strip()
        try:
            return int(s) if s.isdigit() else 0
        except Exception:
            return 0

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self._sess.close()
        except Exception:
            pass
