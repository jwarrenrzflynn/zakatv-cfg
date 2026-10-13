#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JAV吧（jav8.vip）TVBox Python 插件
====================================
站点：https://jav8.vip
引擎：Bulma CSS + 自研后端，纯HTML站
模式：磁力 → 115自动离线 → 直链播放
分类：/latest /top-videos /updated /soon /rank/30-days /rank/7-days
搜索：/?s=关键词（WordPress风格）
详情：/v/{id}，8条磁链，无在线播放
访问：需socks5代理
"""
import re
import json
import time
import os
import urllib.parse
import urllib.request
import ssl

# ==================== 配置 ====================
BASE = "https://jav8.vip"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PAGE_SIZE = 34

# 115配置
SAVE_JSON = "/storage/emulated/0/tmp/115/115_login.json"
OFFLINE_API = "https://clouddownload.115.com/lixianssp/"
LIXIAN_WEB = "https://115.com/web/lixian/?ct=lixian&ac=task_lists&page=1&row=115"
FILES_API = "https://webapi.115.com/files"
DOWNURL_API = "https://proapi.115.com/android/2.0/ufile/download"
ANDROID_UA = "Mozilla/5.0 115disk/36.2.28 115Browser/36.2.28 115wangpan_android/36.2.28"

# ==================== 全局状态 ====================
_cache = {}
_cookie115 = ""
_url_cache = {}
URL_TTL = 3600  # 1小时

# 代理opener（沙箱内需socks5代理访问jav8）
_proxy_opener = None
try:
    _proxy = urllib.request.ProxyHandler({
        "https": "socks5://127.0.0.1:10809",
        "http": "socks5://127.0.0.1:10809"
    })
    _proxy_opener = urllib.request.build_opener(_proxy)
except Exception:
    _proxy_opener = None

# ==================== 工具 ====================
def _ent(s):
    if not s:
        return ""
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'").replace("&#039;", "'")).strip()

def _clean_html(s):
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()

# ==================== HTTP ====================
def _fetch(url, timeout=15):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = BASE + url
    now = time.time()
    if url in _cache and now - _cache[url][0] < 300:
        return _cache[url][1]
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        opener = _proxy_opener if _proxy_opener else urllib.request.build_opener()
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            text = data.decode("utf-8", errors="ignore")
            _cache[url] = (now, text)
            return text
    except Exception as e:
        return ""

def _post(url, data, headers=None, timeout=20):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        h = {"User-Agent": ANDROID_UA, "Accept": "application/json, text/plain, */*",
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        if headers:
            h.update(headers)
        if _cookie115:
            h["Cookie"] = _cookie115
        body = urllib.parse.urlencode(data).encode("utf-8") if isinstance(data, dict) else data
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _get115(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
             "Referer": "https://115.com/"}
        if _cookie115:
            h["Cookie"] = _cookie115
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

# ==================== 115离线 ====================
def load115():
    global _cookie115
    try:
        for path in [SAVE_JSON, os.path.join(os.path.dirname(SAVE_JSON), "115_login.json")]:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                c = data.get("cookie", "")
                if c and "UID=" in c:
                    _cookie115 = c.strip()
                    return
    except Exception:
        pass

def logged115():
    return bool(_cookie115 and "UID=" in _cookie115)

def norm_hash(s):
    if not s:
        return ""
    m = re.search(r"([a-fA-F0-9]{40})", s)
    return m.group(1).lower() if m else ""

def magnet_uri(h, name=""):
    if not h or len(h) != 40:
        return ""
    dn = urllib.parse.quote(name) if name else ""
    return "magnet:?xt=urn:btih:%s%s" % (h, ("&dn=" + dn) if dn else "")

def submit_magnet(magnet, wp_path_id="0"):
    try:
        data = {"ac": "add_task_url", "url": magnet, "wp_path_id": wp_path_id,
                "app": "android", "app_ver": "36.2.28"}
        r = _post(OFFLINE_API, data)
        if r:
            obj = json.loads(r)
            ih = obj.get("info_hash", "")
            if not ih:
                d = obj.get("data", {})
                ih = d.get("info_hash", "") if isinstance(d, dict) else ""
            if ih:
                return ih.lower()
    except Exception:
        pass
    return norm_hash(magnet)

def web_task(info_hash):
    if not info_hash or len(info_hash) != 40:
        return None
    try:
        for page in [1, 2]:
            url = LIXIAN_WEB.replace("page=1", "page=%d" % page)
            r = _get115(url)
            if not r:
                continue
            obj = json.loads(r)
            tasks = obj.get("tasks", [])
            for t in tasks:
                if info_hash.lower() == t.get("info_hash", "").lower():
                    return t
    except Exception:
        pass
    return None

def task_percent(info_hash):
    t = web_task(info_hash)
    if not t:
        return 0
    for k in ["percentDone", "percent_done", "display_percent", "percent", "progress"]:
        v = t.get(k, "")
        if v:
            try:
                return int(float(str(v).replace("%", "").strip()))
            except Exception:
                pass
    return 0

def list_files(cid):
    try:
        url = "%s?cid=%s" % (FILES_API, cid)
        r = _get115(url)
        if not r:
            return []
        obj = json.loads(r)
        return obj.get("data", [])
    except Exception:
        return []

def pick_video(files, hint=""):
    videos = [f for f in files if isinstance(f, dict) and
              re.search(r"\.(mp4|mkv|avi|wmv|flv|mov|ts|m4v)$", f.get("n", ""), re.I)]
    if not videos:
        return None
    videos.sort(key=lambda f: f.get("s", 0), reverse=True)
    return videos[0]

def play115(pickcode):
    try:
        data = {"pickcode": pickcode}
        r = _post(DOWNURL_API, data)
        if not r:
            return None
        obj = json.loads(r)
        if obj.get("state") or obj.get("status"):
            d = obj.get("data", {})
            if isinstance(d, dict):
                url = d.get("url", {}).get("url", "") if isinstance(d.get("url"), dict) else d.get("url", "")
                if url:
                    return [url, "https://115.com/", ANDROID_UA]
    except Exception:
        pass
    return None

def try_direct(info_hash, hint=""):
    t = web_task(info_hash)
    if not t:
        return None
    fid = t.get("file_id", "")
    if not fid:
        d = t.get("data", {})
        fid = d.get("file_id", "") if isinstance(d, dict) else ""
    if not fid:
        return None
    files = list_files(fid)
    best = pick_video(files, hint)
    if not best:
        return None
    pc = best.get("pc", "") or best.get("pick_code", "")
    if not pc:
        return None
    return play115(pc)

def wait_playable(info_hash, hint="", seconds=22):
    deadline = time.time() + seconds
    while time.time() < deadline:
        d = try_direct(info_hash, hint)
        if d and d[0]:
            return d
        time.sleep(2.5)
    return None

# ==================== 解析 ====================
def parse_cards(html):
    cards = []
    if not html:
        return cards
    for m in re.finditer(r'<a[^>]+href="/v/(\d+)"[^>]*>([\s\S]*?)</a>', html):
        vid = m.group(1)
        block = m.group(2)
        title = ""
        tm = re.search(r'title="([^"]+)"', block)
        if tm:
            title = _ent(tm.group(1))
        if not title:
            tm = re.search(r'<img[^>]+alt="([^"]+)"', block)
            if tm:
                title = _ent(tm.group(1))
        pic = ""
        pm = re.search(r'<img[^>]+src="([^"]+)"', block)
        if pm:
            pic = pm.group(1)
        if title:
            cards.append({"vod_id": vid, "vod_name": title, "vod_pic": pic, "vod_remarks": ""})
    return cards

def parse_detail(html, vid):
    result = {"vod_id": vid, "vod_name": "", "vod_pic": "", "vod_actor": "",
              "vod_director": "", "vod_year": "", "vod_area": "日本",
              "vod_remarks": "", "vod_content": "", "vod_play_from": "", "vod_play_url": ""}
    if not html:
        return result
    # 标题
    title_jp = ""
    title_zh = ""
    m = re.search(r'<h1[^>]*class="[^"]*text-jp[^"]*"[^>]*>([\s\S]*?)</h1>', html)
    if m:
        title_jp = _clean_html(m.group(1))
    m = re.search(r'<h1[^>]*class="[^"]*text-zh[^"]*"[^>]*>([\s\S]*?)</h1>', html)
    if m:
        title_zh = _clean_html(m.group(1))
    result["vod_name"] = title_zh or title_jp or ("JAV8-" + vid)
    # 番号
    number = ""
    m = re.search(r'番号</dt>\s*<dd[^>]*>([\s\S]*?)</dd>', html)
    if m:
        number = _clean_html(m.group(1))
    if not number:
        m = re.search(r'<dd[^>]*>([A-Z]{2,5}-\d{2,5})</dd>', html)
        if m:
            number = m.group(1)
    result["vod_remarks"] = number
    # 女优
    actor = ""
    m = re.search(r'(演員|演员|女優|女优)</dt>\s*<dd[^>]*>([\s\S]*?)</dd>', html)
    if m:
        actor = _clean_html(m.group(2))
        actor = re.sub(r"\s+", ",", actor)
    result["vod_actor"] = actor
    # 封面
    result["vod_pic"] = "https://img.j-cdn.com/work/l/%s.jpg" % vid
    # 磁链
    magnets = []
    for m in re.finditer(r'<a[^>]*id="magnet-[^"]*"[^>]*href="(magnet:\?xt=urn:btih:([a-fA-F0-9]{40})[^"]*)"', html):
        magnet = m.group(1).replace("&amp;", "&")
        h = m.group(2).lower()
        dn = number
        dnm = re.search(r'dn=([^&]+)', magnet)
        if dnm:
            try:
                dn = urllib.parse.unquote(dnm.group(1))
            except Exception:
                pass
        magnets.append((h, magnet, dn))
    # 自动预提交第一条
    if logged115() and magnets:
        try:
            h0 = magnets[0][0]
            if h0 not in _url_cache:
                submit_magnet(magnets[0][1])
        except Exception:
            pass
    # 播放列表
    play = []
    for i, (h, magnet, dn) in enumerate(magnets[:20]):
        label = "%d.%s" % (i + 1, dn or ("磁力" + str(i + 1)))
        play.append("%s$j8m_%s" % (label, h))
    result["vod_play_from"] = "磁力→115自动离线" if logged115() else "磁力（未登录115）"
    result["vod_play_url"] = "#".join(play) if play else "没有可用磁力$"
    # 简介
    body = "番号：%s\n共 %d 条磁力。\n点任意一条：自动提交 115 离线 → 等落盘 → 直接播原画。\n" % (number or "未知", len(magnets))
    if not logged115():
        body += "⚠️ 还没登录 115：去「115网盘｜扫码离线」扫一次码，回来就能自动离线+秒播。\n"
    body += "\n" + title_jp
    result["vod_content"] = body
    return result

# ==================== TVBox Spider 类 ====================
class Spider:
    def init(self, extend=""):
        self.extend = extend or ""
        load115()

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "home", "type_name": "首页"},
            {"type_id": "latest", "type_name": "最新"},
            {"type_id": "top", "type_name": "热门"},
            {"type_id": "updated", "type_name": "更新"},
            {"type_id": "soon", "type_name": "即将上映"},
            {"type_id": "rank30", "type_name": "30天排行"},
            {"type_id": "rank7", "type_name": "7天排行"},
        ]
        return json.dumps({"class": classes}, ensure_ascii=False)

    def homeVideoContent(self):
        return self.categoryContent("home", "1")

    def categoryContent(self, tid, pg, filter=False, extend=None):
        paths = {"home": "/", "latest": "/latest", "top": "/top-videos", "updated": "/updated",
                 "soon": "/soon", "rank30": "/rank/30-days", "rank7": "/rank/7-days"}
        path = paths.get(tid, "/")
        page = int(pg) if pg and pg.isdigit() else 1
        if page > 1:
            path += ("&" if "?" in path else "?") + "page=" + str(page)
        html = _fetch(path)
        cards = parse_cards(html)
        if not cards:
            cards = [{"vod_id": "", "vod_name": "这一页没取到数据", "vod_pic": "", "vod_remarks": ""}]
        return json.dumps({"page": page, "pagecount": page + 1 if cards else page,
                           "limit": len(cards), "total": len(cards), "list": cards}, ensure_ascii=False)

    def detailContent(self, ids):
        load115()
        vid = ids[0] if ids else ""
        if not vid or not vid.isdigit():
            return json.dumps({"list": [{"vod_id": "", "vod_name": "无效影片 ID", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        html = _fetch("/v/" + vid)
        if not html:
            return json.dumps({"list": [{"vod_id": "", "vod_name": "详情页取失败", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        detail = parse_detail(html, vid)
        return json.dumps({"list": [detail]}, ensure_ascii=False)

    def searchContent(self, key, quick=False):
        if not key:
            return json.dumps({"list": []}, ensure_ascii=False)
        ih = norm_hash(key)
        if key.lower().startswith("magnet:") or len(ih) == 40:
            magnet = key if key.lower().startswith("magnet:") else magnet_uri(ih)
            if logged115():
                submit_magnet(magnet)
                return json.dumps({"list": [{"vod_id": "off@" + ih, "vod_name": "磁力离线已提交",
                                             "vod_pic": "", "vod_remarks": "点进去看落盘进度"}]}, ensure_ascii=False)
            else:
                return json.dumps({"list": [{"vod_id": "", "vod_name": "先扫码登录 115",
                                             "vod_pic": "", "vod_remarks": "去「115网盘｜扫码离线」扫一次"}]}, ensure_ascii=False)
        html = _fetch("/?s=" + urllib.parse.quote(key))
        cards = parse_cards(html)
        if not cards:
            cards = [{"vod_id": "", "vod_name": "没搜到：「" + key + "」",
                      "vod_pic": "", "vod_remarks": "换个番号试试；也可以直接贴 magnet 丢给 115 离线"}]
        return json.dumps({"list": cards}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        load115()
        pid = id or ""
        if pid.startswith("115pc@"):
            d = play115(pid[6:])
            if d and d[0]:
                return json.dumps({"parse": 0, "url": d[0], "playHeader": json.dumps({"User-Agent": d[2]})}, ensure_ascii=False)
            return json.dumps({"parse": 0, "url": "", "msg": "115取直链失败"}, ensure_ascii=False)
        ih = ""
        magnet = ""
        if pid.startswith("j8m_"):
            ih = pid[4:].lower()
            if len(ih) == 40:
                magnet = magnet_uri(ih)
        elif pid.lower().startswith("magnet:"):
            magnet = pid
            ih = norm_hash(pid)
        else:
            ih = norm_hash(pid)
            if len(ih) == 40:
                magnet = magnet_uri(ih)
        if len(ih) != 40:
            return json.dumps({"parse": 0, "url": ""}, ensure_ascii=False)
        if not logged115():
            return json.dumps({"parse": 0, "url": magnet,
                               "msg": "还没登录 115：去「115网盘｜扫码离线」扫码登录一次，回来点播放就是秒开"}, ensure_ascii=False)
        if ih in _url_cache and time.time() - _url_cache[ih][1] < URL_TTL:
            return json.dumps({"parse": 0, "url": _url_cache[ih][0],
                               "playHeader": json.dumps({"User-Agent": ANDROID_UA})}, ensure_ascii=False)
        d = try_direct(ih, magnet)
        if not d or not d[0]:
            submit_magnet(magnet)
            d = wait_playable(ih, magnet, 22)
        if d and d[0]:
            _url_cache[ih] = (d[0], time.time())
            return json.dumps({"parse": 0, "url": d[0],
                               "playHeader": json.dumps({"User-Agent": d[2]})}, ensure_ascii=False)
        pct = task_percent(ih)
        tip = ("这个种子正在存到 115（已 %d%%），过 1~2 分钟再点一次就是秒开。" % pct) if pct > 0 \
            else "这个种子刚提交离线，115 还在拉资源，过 1~2 分钟再点一次试试。"
        return json.dumps({"parse": 0, "url": "", "msg": tip}, ensure_ascii=False)

# ===== 自检 =====
if __name__ == "__main__":
    s = Spider()
    s.init()
    print("home:", s.homeContent()[:100])
