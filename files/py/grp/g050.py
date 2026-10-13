#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
我为人人影院（wwrr）TVBox Python 插件
====================================
站点：https://5yvo7p.7vk8w0-qv9u.shop
引擎：苹果CMSV10 + 自研前端（xpc-card）
进入：先访问 /home/enter.html?to=%2F 获取 enter_site_ok cookie
搜索/播放：需登录会员
"""
import re
import json
import time
import urllib.request
import urllib.error

# ==================== 配置 ====================
BASE = "https://5yvo7p.7vk8w0-qv9u.shop"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
ENTER_PATH = "/home/enter.html?to=%2F"

# ==================== 全局状态 ====================
_cookie = ""
_cookie_time = 0
COOKIE_TTL = 12 * 3600
_cache = {}

# ==================== 工具 ====================
def _ent(s):
    if not s:
        return ""
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#039;", "'")).strip()

def _ensure_cookie():
    global _cookie, _cookie_time
    now = time.time()
    if _cookie and now - _cookie_time < COOKIE_TTL:
        return
    try:
        req = urllib.request.Request(BASE + ENTER_PATH, headers={
            "User-Agent": UA,
            "Referer": BASE + "/?entered=1",
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            resp = e
        cookies = resp.headers.get_all("Set-Cookie") or []
        for c in cookies:
            if "enter_site_ok" in c:
                _cookie = c.split(";")[0]
                _cookie_time = now
                break
        resp.close()
    except Exception:
        pass

def _fetch(path, timeout=15):
    _ensure_cookie()
    url = path if path.startswith("http") else BASE + path
    now = time.time()
    if url in _cache and now - _cache[url][0] < 300:
        return _cache[url][1]
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": _cookie,
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    for m in re.finditer(r'<a[^>]+href="/play/(\d+)\.html"[^>]*>([\s\S]{0,600}?)</a>', html):
        vid = m.group(1)
        block = m.group(2)
        pic = ""
        ms = re.search(r'<img[^>]+src="([^"]+)"', block)
        if ms: pic = ms.group(1)
        name = ""
        ma = re.search(r'<img[^>]+alt="([^"]+)"', block)
        if ma: name = _ent(ma.group(1))
        if name:
            cards.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": ""})
    return cards

# ==================== TVBox Spider 类 ====================
class Spider:
    def init(self, extend=""):
        self.extend = extend or ""

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "1", "type_name": "国产强片"},
            {"type_id": "4", "type_name": "日韩无码"},
            {"type_id": "6", "type_name": "欧美"},
            {"type_id": "7", "type_name": "动漫"},
            {"type_id": "8", "type_name": "三级"},
            {"type_id": "9", "type_name": "写真"},
            {"type_id": "10", "type_name": "其他"},
        ]
        return json.dumps({"class": classes}, ensure_ascii=False)

    def homeVideoContent(self):
        return self.categoryContent("1", "1")

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try: page = int(pg)
        except: page = 1
        path = "/home/%s.html" % tid
        if page > 1:
            path = "/home/%s-%d.html" % (tid, page)
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
        html = _fetch("/play/%s.html" % vid)
        if not html:
            return json.dumps({"list": [{"vod_id": "", "vod_name": "详情页取失败", "vod_pic": "", "vod_remarks": ""}]}, ensure_ascii=False)
        title = ""
        m = re.search(r"<title>([^<]+)</title>", html)
        if m:
            title = m.group(1).replace(" - 我为人人影院", "").strip()
        if not title:
            title = "我为人人-" + vid
        pic = ""
        mp = re.search(r"background-image:url\(([^)]+)\)", html)
        if mp: pic = mp.group(1)
        is_vip = bool(re.search(r"会员专享|暂不支持试看|获取影视会员", html))
        detail = {
            "vod_id": vid, "vod_name": title, "vod_pic": pic,
            "vod_actor": "", "vod_director": "", "vod_year": "", "vod_area": "",
            "vod_remarks": "",
            "vod_content": "本视频为会员专享，暂不支持试看。请登录会员后观看。" if is_vip else title,
            "vod_play_from": "会员专享" if is_vip else "播放",
            "vod_play_url": "会员专享$" if is_vip else "播放$",
        }
        return json.dumps({"list": [detail]}, ensure_ascii=False)

    def searchContent(self, key, quick=False):
        if not key:
            return json.dumps({"list": []}, ensure_ascii=False)
        return json.dumps({"list": [{"vod_id": "", "vod_name": "搜索需登录会员",
                                     "vod_pic": "", "vod_remarks": "本站搜索功能需登录会员后使用"}]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        return json.dumps({"parse": 0, "url": "", "msg": "本视频为会员专享，暂不支持试看"}, ensure_ascii=False)

# ===== 自检 =====
if __name__ == "__main__":
    s = Spider()
    s.init()
    print("home:", s.homeContent()[:100])
    print("cat:", s.categoryContent("1", "1")[:100])
