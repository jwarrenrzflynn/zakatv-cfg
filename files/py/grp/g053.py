#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蜜桃网（mitao）TVBox Python 插件
================================
站点：https://assure.mdhuzuio.cc
引擎：Typecho博客 + 海角主题，DPlayer播放器
详情：/archives/{id}/，data-config JSON含m3u8
搜索：/search/{关键词}/
"""
import re
import json
import time
import urllib.parse
import urllib.request
import ssl

# ==================== 配置 ====================
BASE = "https://assure.mdhuzuio.cc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ==================== 全局状态 ====================
_cache = {}

# ==================== 工具 ====================
def _ent(s):
    if not s:
        return ""
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#039;", "'")).strip()

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
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
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
    id_title = {}
    ids = []
    for m in re.finditer(r'<a[^>]+href="/archives/(\d+)/"[^>]*title="([^"]+)"', html):
        vid = m.group(1)
        if vid not in id_title:
            id_title[vid] = _ent(m.group(2))
            ids.append(vid)
    id_pic = {}
    idx = 0
    for m in re.finditer(r'<a[^>]+href="/archives/\d+/"[^>]*>[\s\S]{0,500}?<img[^>]+src="([^"]+)"', html):
        if idx < len(ids):
            id_pic[ids[idx]] = m.group(1)
            idx += 1
    for vid in ids:
        name = id_title.get(vid, "")
        if name:
            cards.append({"vod_id": vid, "vod_name": name,
                          "vod_pic": id_pic.get(vid, ""), "vod_remarks": ""})
    return cards

# ==================== TVBox Spider 类 ====================
class Spider:
    def init(self, extend=""):
        self.extend = extend or ""

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "home", "type_name": "首页"},
            {"type_id": "hot", "type_name": "热门"},
            {"type_id": "new", "type_name": "最新"},
        ]
        return json.dumps({"class": classes}, ensure_ascii=False)

    def homeVideoContent(self):
        return self.categoryContent("home", "1")

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = int(pg)
        except:
            page = 1
        if tid == "hot":
            path = "/order/hot/"
        else:
            path = "/"
        if page > 1:
            path = "/page/%d/" % page
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
        html = _fetch("/archives/%s/" % vid)
        if not html:
            return json.dumps({"list": [{"vod_id": "", "vod_name": "详情页取失败", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        title = ""
        m = re.search(r"<title>([^<]+)</title>", html)
        if m:
            title = m.group(1).replace(" | 蜜桃网", "").strip()
        if not title:
            title = "蜜桃网-" + vid
        play_url = ""
        m = re.search(r"data-config='([^']+)'", html)
        if m:
            config = m.group(1)
            mv = re.search(r'"video"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', config)
            if mv:
                play_url = mv.group(1).replace("\\/", "/")
        pic = ""
        mp = re.search(r'og:image"\s+content="([^"]+)"', html)
        if mp:
            pic = mp.group(1)
        detail = {
            "vod_id": vid, "vod_name": title, "vod_pic": pic,
            "vod_actor": "", "vod_director": "", "vod_year": "", "vod_area": "",
            "vod_remarks": "", "vod_content": title,
            "vod_play_from": "播放",
            "vod_play_url": "播放$" + (play_url if play_url else "暂无播放地址"),
        }
        return json.dumps({"list": [detail]}, ensure_ascii=False)

    def searchContent(self, key, quick=False):
        if not key:
            return json.dumps({"list": []}, ensure_ascii=False)
        html = _fetch("/search/" + urllib.parse.quote(key) + "/")
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
    print("cat:", s.categoryContent("home", "1")[:100])
