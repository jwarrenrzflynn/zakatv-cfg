# -*- coding: utf-8 -*-
import sys
import re
import json
import requests
import html as html_module
import urllib.parse
from urllib.parse import quote, unquote, urljoin, urlparse

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def __init__(self): pass

class Spider(BaseSpider):
    DEFAULT_HOST = "https://www.ddys24.com"
    DEFAULT_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    CLASSES = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "42", "type_name": "豆瓣Top250"}
    ]

    COMMON_YEARS = [
        {"n": "全部", "v": ""}, {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"},
        {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"},
        {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"},
        {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"},
        {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"},
        {"n": "2010", "v": "2010"}
    ]

    COMMON_LANGS = [
        {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
        {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
        {"n": "日语", "v": "日语"}, {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"},
        {"n": "其它", "v": "其它"}
    ]

    COMMON_LETTERS = [{"n": "全部", "v": ""}] + [{"n": chr(i), "v": chr(i)} for i in range(65, 91)] + [{"n": "0-9", "v": "0-9"}]

    COMMON_BY = [
        {"n": "按时间", "v": "time"},
        {"n": "按人气", "v": "hits"},
        {"n": "按评分", "v": "score"}
    ]

    FILTERS = {
        "1": [
            {
                "key": "sub_tid",
                "name": "按类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "动作片", "v": "5"}, {"n": "喜剧片", "v": "6"},
                    {"n": "爱情片", "v": "7"}, {"n": "科幻片", "v": "8"}, {"n": "恐怖片", "v": "9"},
                    {"n": "剧情片", "v": "10"}, {"n": "战争片", "v": "11"}, {"n": "纪录片", "v": "22"},
                    {"n": "动画片", "v": "33"}
                ]
            },
            {
                "key": "class",
                "name": "按剧情",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
                    {"n": "恐怖", "v": "恐怖"}, {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"},
                    {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"},
                    {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"},
                    {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"},
                    {"n": "悬疑", "v": "悬疑"}, {"n": "惊悚", "v": "惊悚"}, {"n": "经典", "v": "经典"},
                    {"n": "青春", "v": "青春"}, {"n": "文艺", "v": "文艺"}, {"n": "微电影", "v": "微电影"},
                    {"n": "古装", "v": "古装"}, {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"},
                    {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"}, {"n": "网络电影", "v": "网络电影"}
                ]
            },
            {
                "key": "area",
                "name": "按地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"},
                    {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
                    {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                    {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
                    {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "按年份", "value": COMMON_YEARS},
            {"key": "lang", "name": "按语言", "value": COMMON_LANGS},
            {"key": "letter", "name": "按字母", "value": COMMON_LETTERS},
            {"key": "by", "name": "排序", "value": COMMON_BY}
        ],
        "2": [
            {
                "key": "sub_tid",
                "name": "按类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "抖音短剧", "v": "43"}, {"n": "电视剧", "v": "13"},
                    {"n": "美剧", "v": "16"}, {"n": "港剧", "v": "14"}, {"n": "韩剧", "v": "15"},
                    {"n": "泰剧", "v": "19"}, {"n": "海外剧", "v": "18"}, {"n": "日剧", "v": "17"}
                ]
            },
            {
                "key": "class",
                "name": "按剧情",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"},
                    {"n": "青春偶像", "v": "青春偶像"}, {"n": "喜剧", "v": "喜剧"}, {"n": "家庭", "v": "家庭"},
                    {"n": "犯罪", "v": "犯罪"}, {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"},
                    {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"}, {"n": "经典", "v": "经典"},
                    {"n": "乡村", "v": "乡村"}, {"n": "情景", "v": "情景"}, {"n": "商战", "v": "商战"},
                    {"n": "网剧", "v": "网剧"}, {"n": "其他", "v": "其他"}
                ]
            },
            {
                "key": "area",
                "name": "按地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "韩国", "v": "韩国"},
                    {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "日本", "v": "日本"},
                    {"n": "美国", "v": "美国"}, {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"},
                    {"n": "新加坡", "v": "新加坡"}, {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "按年份", "value": COMMON_YEARS},
            {"key": "lang", "name": "按语言", "value": COMMON_LANGS},
            {"key": "letter", "name": "按字母", "value": COMMON_LETTERS},
            {"key": "by", "name": "排序", "value": COMMON_BY}
        ],
        "3": [
            {
                "key": "sub_tid",
                "name": "按类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "内地综艺", "v": "23"}, {"n": "港台综艺", "v": "24"},
                    {"n": "日韩综艺", "v": "25"}, {"n": "欧美综艺", "v": "26"}
                ]
            },
            {
                "key": "plot",
                "name": "按剧情",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "选秀", "v": "选秀"}, {"n": "情感", "v": "情感"},
                    {"n": "访谈", "v": "访谈"}, {"n": "播报", "v": "播报"}, {"n": "旅游", "v": "旅游"},
                    {"n": "音乐", "v": "音乐"}, {"n": "美食", "v": "美食"}, {"n": "纪实", "v": "纪实"},
                    {"n": "曲艺", "v": "曲艺"}, {"n": "生活", "v": "生活"}, {"n": "游戏互动", "v": "游戏互动"},
                    {"n": "财经", "v": "财经"}, {"n": "求职", "v": "求职"}
                ]
            },
            {
                "key": "area",
                "name": "按地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "港台", "v": "港台"},
                    {"n": "日韩", "v": "日韩"}, {"n": "欧美", "v": "欧美"}
                ]
            },
            {"key": "year", "name": "按年份", "value": COMMON_YEARS},
            {"key": "lang", "name": "按语言", "value": COMMON_LANGS},
            {"key": "letter", "name": "按字母", "value": COMMON_LETTERS},
            {"key": "by", "name": "排序", "value": COMMON_BY}
        ],
        "4": [
            {
                "key": "sub_tid",
                "name": "按类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "国漫", "v": "28"}, {"n": "日韩动漫", "v": "30"},
                    {"n": "欧美动漫", "v": "31"}, {"n": "海外动漫", "v": "32"}
                ]
            },
            {
                "key": "class",
                "name": "按剧情",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"},
                    {"n": "热血", "v": "热血"}, {"n": "推理", "v": "推理"}, {"n": "搞笑", "v": "搞笑"},
                    {"n": "冒险", "v": "冒险"}, {"n": "萝莉", "v": "萝莉"}, {"n": "校园", "v": "校园"},
                    {"n": "动作", "v": "动作"}, {"n": "机战", "v": "机战"}, {"n": "运动", "v": "运动"},
                    {"n": "战争", "v": "战争"}, {"n": "少年", "v": "少年"}, {"n": "少女", "v": "少女"},
                    {"n": "社会", "v": "社会"}, {"n": "原创", "v": "原创"}, {"n": "亲子", "v": "亲子"},
                    {"n": "益智", "v": "益智"}, {"n": "励志", "v": "励志"}, {"n": "其他", "v": "其他"}
                ]
            },
            {
                "key": "area",
                "name": "按地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "国产", "v": "国产"}, {"n": "日本", "v": "日本"},
                    {"n": "欧美", "v": "欧美"}, {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "按年份", "value": COMMON_YEARS},
            {"key": "lang", "name": "按语言", "value": COMMON_LANGS},
            {"key": "letter", "name": "按字母", "value": COMMON_LETTERS},
            {"key": "by", "name": "排序", "value": COMMON_BY}
        ],
        "42": [
            {
                "key": "area",
                "name": "按地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"},
                    {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
                    {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                    {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
                    {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "按年份", "value": COMMON_YEARS},
            {"key": "lang", "name": "按语言", "value": COMMON_LANGS},
            {"key": "letter", "name": "按字母", "value": COMMON_LETTERS},
            {"key": "by", "name": "排序", "value": COMMON_BY}
        ]
    }

    def __init__(self):
        super().__init__()
        self.host = self.DEFAULT_HOST
        self.ua = self.DEFAULT_UA
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache"
        }
        self.session.headers.update(self.headers)

    def init(self, extend=""):
        return True

    def getName(self):
        return "ZakaTV·低端"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|avi|mkv|mov|ts)(\?|$)', url or "", re.I))

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        return {
            "class": list(self.CLASSES),
            "filters": self.FILTERS if filter else {}
        }

    def homeVideoContent(self):
        html = self.get(self.host + "/")
        return {"list": self.parseList(html)[:80]}

    def categoryContent(self, tid, pg, filter, extend):
        page = str(pg or "1")
        ext = extend or {}
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}

        target_tid = str(ext.get("sub_tid") or tid or "1").strip()

        area_val = str(ext.get("area", "")).strip()
        by_val = str(ext.get("by", "")).strip()
        class_val = str(ext.get("class", "")).strip()
        lang_val = str(ext.get("lang", "")).strip()
        letter_val = str(ext.get("letter", "")).strip()
        year_val = str(ext.get("year", "")).strip()

        has_filter = bool(area_val or by_val or class_val or lang_val or letter_val or year_val or ext.get("sub_tid"))

        if has_filter or page != "1":
            slots = [
                target_tid,
                area_val,
                by_val,
                class_val,
                lang_val,
                letter_val,
                "",
                "",
                page,
                "",
                "",
                year_val
            ]
            route_path = "-".join(slots)
            target_url = f"{self.host}/ddvodshow/{route_path}.html"
        else:
            target_url = f"{self.host}/ddvodtype/{target_tid}.html"

        html = self.get(target_url)
        videos = self.parseList(html)

        return {
            "page": int(page),
            "pagecount": 999 if len(videos) >= 20 else int(page),
            "limit": len(videos),
            "total": 999999,
            "list": videos
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(raw_id or "").strip()
        url = vid if vid.startswith("http") else f"{self.host}/ddvoddetail/{vid}.html"
        html = self.get(url)

        name = self.clean(self.match(html, r'<h1[^>]*class=["\']title["\'][^>]*>(.*?)</h1>') or self.match(html, r'<title>《?([^《》_]+?)》?'))
        pic = self.fix(self.match(html, r'data-original=["\']([^"\']+)') or self.match(html, r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)'))
        remarks = self.clean(self.match(html, r'<span class=["\']pic-text[^"\']*["\'][^>]*>(.*?)</span>'))
        desc = self.clean(self.match(html, r'<span class=["\']detail-content["\'][^>]*>(.*?)</span>') or self.match(html, r'<span class=["\']detail-sketch["\'][^>]*>(.*?)</span>') or self.match(html, r'<meta name=["\']description["\'] content=["\']([^"\']+)'))
        actor = self.clean(self.match(html, r'主演：</span>([\s\S]*?)</p>'))
        director = self.clean(self.match(html, r'导演：</span>([\s\S]*?)</p>'))
        area = self.clean(self.match(html, r'地区：</span>([\s\S]*?)<span'))
        year = self.clean(self.match(html, r'年份：</span>([\s\S]*?)</p>'))

        play_from = []
        play_url = []
        blocks = re.findall(r'<div class="stui-pannel-ddy1102-cbox b playlist mb">([\s\S]*?)</div>\s*</div>\s*</div>', html)
        if not blocks:
            blocks = re.findall(r'<ul class="stui-content_ddy1102-cplaylist clearfix">([\s\S]*?)</ul>', html)
        if not blocks:
            blocks = re.findall(r'<ul class=["\'][^"\']*playlist[^"\']*["\']>([\s\S]*?)</ul>', html)

        for i, block in enumerate(blocks):
            eps = []
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/ddvodplay/[^"\']+)["\'][^>]*>(.*?)</a>', block):
                u = self.fix(m.group(1))
                t = self.clean(m.group(2)) or "播放"
                if u:
                    eps.append(f"{t}${u}")
            if eps:
                line = self.clean(self.match(block, r'<h3 class=["\']title["\'][^>]*>(.*?)</h3>')) or f"Zaka极速线路{i + 1}"
                play_from.append(line)
                play_url.append("#".join(eps))

        if not play_url:
            eps = []
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/ddvodplay/' + str(vid) + r'-[^"\']+)["\'][^>]*>(.*?)</a>', html):
                u = self.fix(m.group(1))
                t = self.clean(m.group(2)) or "播放"
                if u:
                    eps.append(f"{t}${u}")
            if eps:
                play_from.append("Zaka备用线路")
                play_url.append("#".join(eps))

        full_desc = (
            "【🔥 官方TG群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, desc)

        escaped_desc = full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": name or "未知影片",
                "vod_pic": pic,
                "vod_remarks": remarks or "ZakaTV",
                "vod_year": year,
                "vod_area": area,
                "vod_actor": self.brandActor if not actor else f"{self.brandActor} / {actor}",
                "vod_director": self.brandDirector if not director else f"{self.brandDirector} / {director}",
                "vod_content": escaped_desc,
                "vod_play_from": "$$$".join(play_from) if play_from else "Zaka默认线路",
                "vod_play_url": "$$$".join(play_url) if play_url else f"立即播放${url}"
            }]
        }

    def searchContent(self, key, quick, pg="1"):
        k = quote(str(key or "").strip())
        urls = [
            f"{self.host}/ddvodsearch/{k}-------------.html",
            f"{self.host}/ddvodsearch/-------------.html?wd={k}",
            f"{self.host}/index.php/vod/search.html?wd={k}"
        ]
        html = ""
        for u in urls:
            html = self.get(u)
            if "ddvoddetail" in html:
                break
        return {"list": self.parseList(html), "page": int(pg)}

    def playerContent(self, flag, id, vipFlags=None):
        play_page_url = str(id or "").strip()
        if not play_page_url.startswith("http"):
            play_page_url = self.fix(play_page_url)

        headers = {
            "User-Agent": self.ua,
            "Referer": play_page_url
        }

        if self.isVideoFormat(play_page_url):
            return {
                "parse": 0,
                "playUrl": "",
                "url": play_page_url,
                "header": headers
            }

        html = self.get(play_page_url)
        real_media_url = ""

        match = re.search(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', html)
        if match:
            try:
                config = json.loads(match.group(1))
                media_url = config.get("url", "")
                if media_url:
                    real_media_url = media_url.replace("\\/", "/").strip()
            except Exception:
                pass

        if not real_media_url:
            m = re.search(r'["\'](https?://[^"\'<>\s]+?\.(?:m3u8|mp4)[^"\'<>\s]*?)["\']', html, re.I)
            if m:
                real_media_url = m.group(1).replace("\\/", "/").strip()

        if real_media_url:
            return {
                "parse": 0,
                "playUrl": "",
                "url": real_media_url,
                "header": {
                    "User-Agent": self.ua,
                    "Referer": self.host + "/"
                }
            }

        return {
            "parse": 1,
            "url": play_page_url,
            "header": self.headers
        }

    def localProxy(self, param):
        return [404, "text/plain", "", ""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def get(self, url):
        if not url:
            return ""
        targets = [url]
        if url.startswith("https://"):
            targets.append("http://" + url[len("https://"):])

        for target in targets:
            try:
                safe_url = urllib.parse.quote(target, safe=':/?&=%-')
                r = self.session.get(safe_url, timeout=12, verify=False, allow_redirects=True)
                if r.status_code == 200:
                    r.encoding = r.apparent_encoding or "utf-8"
                    return r.text
            except Exception:
                continue
        return ""

    def match(self, text, rule):
        m = re.search(rule, text or "", re.S)
        return m.group(1) if m else ""

    def clean(self, text):
        return re.sub(r"\s+", " ", re.sub(r"<.*?>", "", text or "")).replace("&nbsp;", " ").replace("&amp;", "&").strip()

    def fix(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return url

    def parseList(self, html):
        res = []
        seen = set()
        if not html:
            return res

        for m in re.finditer(r'<a\b([^>]*href=["\']([^"\']*?/ddvoddetail/(\d+)\.html)["\'][^>]*)>(.*?)</a>', html, re.S | re.I):
            a_attrs, href, vid, body = m.group(1), m.group(2), m.group(3), m.group(4)
            if vid in seen:
                continue

            title = self.clean(self.match(a_attrs, r'title=["\']([^"\']+)'))
            if not title:
                title = self.clean(self.match(body, r'class=["\'][^"\']*pic-text[^"\']*["\'][^>]*>(.*?)</'))
            if not title:
                title = self.clean(body)

            if not title or len(title) > 60:
                continue

            seen.add(vid)

            pic = self.match(a_attrs, r'data-original=["\']([^"\']+)')
            if not pic:
                pic = self.match(body, r'data-original=["\']([^"\']+)')
            if not pic:
                pic = self.match(body, r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)')

            remarks = self.clean(self.match(body, r'class=["\'][^"\']*pic-text[^"\']*["\'][^>]*>(.*?)</'))

            res.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self.fix(pic),
                "vod_remarks": remarks or "ZakaTV",
                "style": {"type": "rect", "ratio": 0.75}
            })

        return res