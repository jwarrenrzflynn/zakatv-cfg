#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Javmix.TV（javmix）TVBox Python 插件
====================================
站点：https://javmix.tv
引擎：WordPress + 自研主题，纯HTML站
播放：3个iframe嵌入源（iplayerhls/minochinos/streamtape），从packer JS提取
搜索：/search/{关键词}
访问：需socks5代理
"""
import re
import json
import time
import urllib.parse
import urllib.request
import ssl

# ==================== 配置 ====================
BASE = "https://javmix.tv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ==================== 全局状态 ====================
_cache = {}
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
             .replace("&quot;", '"').replace("&#039;", "'").replace("&#39;", "'")).strip()

def _clean(s):
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()

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
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        opener = _proxy_opener if _proxy_opener else urllib.request.build_opener()
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            text = data.decode("utf-8", errors="ignore")
            _cache[url] = (now, text)
            return text
    except Exception:
        return ""

# ==================== 解析 ====================
def parse_cards(html):
    cards = []
    if not html or len(html) < 100:
        return cards
    pattern = r'<a[^>]+href="' + re.escape(BASE) + r'/((?:xvideo|fc2ppv)/mx-[^"]+)"[^>]*>[\s\S]*?<img[^>]+src="([^"]+)"[^>]+alt="([^"]+)"'
    for m in re.finditer(pattern, html):
        vid = m.group(1)
        pic = m.group(2)
        name = _ent(m.group(3))
        if name:
            cards.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": ""})
    return cards

def parse_detail(html, vid):
    result = {"vod_id": vid, "vod_name": "", "vod_pic": "", "vod_actor": "",
              "vod_director": "", "vod_year": "", "vod_area": "日本",
              "vod_remarks": "", "vod_content": "", "vod_play_from": "", "vod_play_url": ""}
    if not html or len(html) < 100:
        return result
    m = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
    title = _ent(_clean(m.group(1))) if m else ""
    result["vod_name"] = title or ("Javmix-" + vid)
    number = actor = genre = maker = ""
    for m in re.finditer(r"【(品番|出演者|ジャンル|メーカー|レーベル)】([^【]+)", html):
        key, val = m.group(1), _clean(m.group(2)).strip()
        if "品番" in key: number = val
        elif "出演" in key: actor = val.replace(" ", ",")
        elif "ジャンル" in key: genre = val
        elif "メーカー" in key: maker = val
    dur = ""
    m = re.search(r'id="post-duration">([^<]+)<', html)
    if m: dur = m.group(1).strip()
    result["vod_remarks"] = number + ((" " + dur) if dur else "")
    result["vod_actor"] = actor
    result["vod_content"] = "品番：%s\n出演：%s\nジャンル：%s\nメーカー：%s" % (number, actor, genre, maker)
    m = re.search(r'og:image"\s+content="([^"]+)"', html)
    if m: result["vod_pic"] = m.group(1)
    sources = []
    for m in re.finditer(r'src="(https://(?:iplayerhls|minochinos|streamtape)\.com/[^"]+)"', html):
        src = m.group(1)
        if src not in sources: sources.append(src)
    if not sources:
        for m in re.finditer(r'([a-zA-Z0-9]{10,})\|(iplayerhls|minochinos|streamtape)', html):
            sid, domain = m.group(1), m.group(2)
            if domain == "iplayerhls": url = "https://iplayerhls.com/e/" + sid
            elif domain == "minochinos": url = "https://minochinos.com/v/" + sid
            else: url = "https://streamtape.com/e/" + sid
            if url not in sources: sources.append(url)
    if sources:
        names = ["iplayerhls", "minochinos", "streamtape"]
        from_list, url_list = [], []
        for i, src in enumerate(sources):
            sname = names[i] if i < len(names) else ("源%d" % (i+1))
            from_list.append(sname)
            url_list.append("%s$%s" % (sname, src))
        result["vod_play_from"] = "$$$".join(from_list)
        result["vod_play_url"] = "$$$".join(url_list)
    else:
        result["vod_play_from"] = "暂无"
        result["vod_play_url"] = "暂无$"
    return result

# ==================== TVBox Spider 类 ====================
class Spider:
    def init(self, extend=""):
        self.extend = extend or ""

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "home", "type_name": "首页"},
            {"type_id": "popular", "type_name": "热门"},
            {"type_id": "xvideo", "type_name": "有码"},
            {"type_id": "fc2ppv", "type_name": "FC2"},
        ]
        return json.dumps({"class": classes}, ensure_ascii=False)

    def homeVideoContent(self):
        return self.categoryContent("home", "1")

    def categoryContent(self, tid, pg, filter=False, extend=None):
        if tid == "home": path = "/"
        elif tid == "popular": path = "/popularity/"
        elif tid == "xvideo": path = "/xvideo/"
        elif tid == "fc2ppv": path = "/fc2ppv/"
        else: path = "/"
        try: page = int(pg)
        except: page = 1
        if page > 1: path += "page/%d/" % page
        html = _fetch(path)
        cards = parse_cards(html)
        if not cards:
            cards = [{"vod_id": "", "vod_name": "这一页没取到数据", "vod_pic": "", "vod_remarks": ""}]
        return json.dumps({"page": page, "pagecount": page+1, "limit": len(cards),
                           "total": len(cards)*10, "list": cards}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid:
            return json.dumps({"list": [{"vod_id": "", "vod_name": "无效影片 ID", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        html = _fetch("/" + vid)
        if not html:
            return json.dumps({"list": [{"vod_id": "", "vod_name": "详情页取失败", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        detail = parse_detail(html, vid)
        return json.dumps({"list": [detail]}, ensure_ascii=False)

    def searchContent(self, key, quick=False):
        if not key:
            return json.dumps({"list": []}, ensure_ascii=False)
        html = _fetch("/search/" + urllib.parse.quote(key))
        cards = parse_cards(html)
        if not cards:
            cards = [{"vod_id": "", "vod_name": "没搜到：「" + key + "」", "vod_pic": "", "vod_remarks": "换个关键词试试"}]
        return json.dumps({"list": cards}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        return json.dumps({"parse": 0, "url": id,
                           "playHeader": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

# ===== 自检 =====
if __name__ == "__main__":
    s = Spider()
    s.init()
    print("home:", s.homeContent()[:100])
