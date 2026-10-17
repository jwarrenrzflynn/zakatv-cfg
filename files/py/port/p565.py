# -*- coding: utf-8 -*-
# FongMi TV Native Python Spider - Full Sub-Filters & Star Ratio
# Target: https://app-1.mahuax.cyou/

import html
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

RECT_178_STYLE = {"type": "rect", "ratio": 1.78}
RECT_075_STYLE = {"type": "rect", "ratio": 0.75}

CLASSES_CACHE = [
    {"type_id": "pornstars_all", "type_name": "🌟 色情明星"},
    {"type_id": "精品推荐", "type_name": "精品推荐"},
    {"type_id": "国产", "type_name": "国产"},
    {"type_id": "日本", "type_name": "日本"},
    {"type_id": "欧美", "type_name": "欧美"},
    {"type_id": "传媒", "type_name": "传媒"},
    {"type_id": "麻豆视频", "type_name": "麻豆视频"},
    {"type_id": "91制片厂", "type_name": "91制片厂"},
    {"type_id": "天美传媒", "type_name": "天美传媒"},
    {"type_id": "蜜桃传媒", "type_name": "蜜桃传媒"},
    {"type_id": "皇家华人", "type_name": "皇家华人"},
    {"type_id": "星空传媒", "type_name": "星空传媒"},
    {"type_id": "精东影业", "type_name": "精东影业"},
    {"type_id": "乐播传媒", "type_name": "乐播传媒"},
    {"type_id": "成人头条", "type_name": "成人头条"},
    {"type_id": "乌鸦传媒", "type_name": "乌鸦传媒"},
    {"type_id": "兔子先生", "type_name": "兔子先生"},
    {"type_id": "杏吧原创", "type_name": "杏吧原创"},
    {"type_id": "玩偶姐姐", "type_name": "玩偶姐姐"},
    {"type_id": "mini传媒", "type_name": "mini传媒"},
    {"type_id": "大象传媒", "type_name": "大象传媒"},
    {"type_id": "开心鬼传媒", "type_name": "开心鬼传媒"},
    {"type_id": "PsychoPorn", "type_name": "PsychoPorn"},
    {"type_id": "糖心Vlog", "type_name": "糖心Vlog"},
    {"type_id": "萝莉社", "type_name": "萝莉社"},
    {"type_id": "性视界", "type_name": "性视界"},
    {"type_id": "tag_深喉", "type_name": "🏷️ 标签: 深喉"},
    {"type_id": "tag_妈妈", "type_name": "🏷️ 标签: 妈妈"},
    {"type_id": "tag_69", "type_name": "🏷️ 标签: 69"},
    {"type_id": "tag_肉感", "type_name": "🏷️ 标签: 肉感"},
    {"type_id": "tag_淫语", "type_name": "🏷️ 标签: 淫语"},
    {"type_id": "tag_无毛", "type_name": "🏷️ 标签: 无毛"},
    {"type_id": "tag_龙凤胎", "type_name": "🏷️ 标签: 龙凤胎"},
    {"type_id": "tag_学生妹", "type_name": "🏷️ 标签: 学生妹"},
    {"type_id": "tag_德语", "type_name": "🏷️ 标签: 德语"},
    {"type_id": "tag_猛操", "type_name": "🏷️ 标签: 猛操"},
    {"type_id": "tag_白虎萌妹", "type_name": "🏷️ 标签: 白虎萌妹"},
    {"type_id": "tag_吃瓜黑料", "type_name": "🏷️ 标签: 吃瓜黑料"}
]

ORDER_FILTER_VALUES = [
    {"n": "最新更新", "v": ""},
    {"n": "最新点播", "v": "db"},
    {"n": "最多点击", "v": "h"},
    {"n": "最多弹幕", "v": "d"},
    {"n": "最新弹幕", "v": "dt"},
    {"n": "最多评论", "v": "p"},
    {"n": "最新评论", "v": "pt"},
    {"n": "最多收藏", "v": "s"},
    {"n": "最新收藏", "v": "st"},
    {"n": "最多点赞", "v": "z"},
    {"n": "最新点赞", "v": "zt"}
]

FILTERS_CACHE = {}
for c in CLASSES_CACHE:
    cid = c["type_id"]
    if cid != "pornstars_all":
        FILTERS_CACHE[cid] = [
            {
                "key": "rq",
                "name": "排序",
                "value": ORDER_FILTER_VALUES
            }
        ]

def dump_to_shared_folder(filename, content):
    target_paths = [
        "/sdcard/Pictures/%s" % filename,
        "/storage/emulated/0/Pictures/%s" % filename,
        "/sdcard/Download/%s" % filename,
        "/storage/emulated/0/Download/%s" % filename,
        filename
    ]
    for path in target_paths:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return path
        except Exception:
            continue
    return None

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.site_url = "https://app-1.mahuax.cyou"
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://app-1.mahuax.cyou/"
        }

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        return {
            "class": CLASSES_CACHE,
            "filters": FILTERS_CACHE,
            "style": RECT_178_STYLE
        }

    def homeVideoContent(self):
        return {"list": [], "style": RECT_178_STYLE}

    def _fetch_html(self, url):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=self.default_headers)
        try:
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                raw_bytes = resp.read()
                try:
                    return raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    return raw_bytes.decode("gbk", errors="ignore")
        except Exception:
            return ""

    def _parse_card_list(self, html_text):
        cards = []
        if not html_text:
            return cards

        item_blocks = re.findall(r'(<li[^>]*class=["\'][^"\']*section-content__item[^"\']*["\'][^>]*>.*?</li>)', html_text, re.I | re.S)

        for block in item_blocks:
            id_match = re.search(r'href=["\'][^"\']*play-(\d+)[^"\']*["\']', block)
            if not id_match:
                id_match = re.search(r'href=["\'][^"\']*id[=/](\d+)[^"\']*["\']', block)
            if not id_match:
                continue
            vid = id_match.group(1)

            title = ""
            title_match = re.search(r'aria-label=["\']([^"\']+)["\']', block)
            if title_match:
                title = title_match.group(1).strip()
            else:
                title_match2 = re.search(r'<h3[^>]*class=["\'][^"\']*text-truncate[^"\']*["\'][^>]*>(.*?)</h3>', block, re.I | re.S)
                if title_match2:
                    title = re.sub(r'<[^>]+>', '', title_match2.group(1)).strip()

            title = html.unescape(title)

            pic = ""
            pic_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', block)
            if pic_match:
                pic = pic_match.group(1).strip()
            if not pic or "images/logo.png" in pic:
                pic_match2 = re.search(r'data-src=["\']([^"\']+)["\']', block)
                if pic_match2:
                    pic = pic_match2.group(1).strip()

            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = urllib.parse.urljoin(self.site_url, pic)

            tag = "HD"
            tag_match = re.search(r'<i[^>]*class=["\'][^"\']*icon-top-right[^"\']*["\'][^>]*>(.*?)</i>', block, re.I | re.S)
            if tag_match:
                tag = re.sub(r'<[^>]+>', '', tag_match.group(1)).strip()

            remarks = "ZakaTV | %s" % (tag or "HD")

            cards.append({
                "vod_id": str(vid),
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": RECT_178_STYLE
            })
        return cards

    def _parse_pornstars_list(self, html_text):
        cards = []
        if not html_text:
            return cards

        clean_text = html_text
        clean_text = re.sub(r'<header.*?</header>', '', clean_text, flags=re.I | re.S)
        clean_text = re.sub(r'<nav.*?</nav>', '', clean_text, flags=re.I | re.S)
        clean_text = re.sub(r'<footer.*?</footer>', '', clean_text, flags=re.I | re.S)

        noise_keywords = [
            "首页", "arrowIcon", "arrow", "色情明星", "全部类型", "分享发布",
            "注册登录", "个人中心", "最近更新", "随机播放", "热门标签", "全部标签"
        ]

        star_blocks = re.findall(r'(<(?:li|div)[^>]*class=["\'][^"\']*(?:pornstar|star|actor|item|col)[^"\']*["\'][^>]*>.*?</(?:li|div)>)', clean_text, re.I | re.S)
        if not star_blocks:
            star_blocks = re.findall(r'(<a[^>]*href=["\'][^"\']*(?:pornstar|star|actor)[^"\']*["\'][^>]*>.*?</a>)', clean_text, re.I | re.S)

        seen_names = set()
        for block in star_blocks:
            name = ""
            name_match = re.search(r'(?:title|alt|aria-label)=["\']([^"\']+)["\']', block)
            if name_match:
                name = name_match.group(1).strip()
            if not name:
                sub_txt = re.findall(r'<(?:h[34]|span|p)[^>]*>(.*?)</(?:h[34]|span|p)>', block, re.I | re.S)
                for t in sub_txt:
                    c = re.sub(r'<[^>]+>', '', t).strip()
                    if c and len(c) <= 15:
                        name = c
                        break

            if not name:
                text_clean = re.sub(r'<[^>]+>', '', block).strip()
                if text_clean and len(text_clean) <= 15:
                    name = text_clean

            if not name or any(k in name for k in noise_keywords):
                continue
            if name in seen_names:
                continue

            pic = ""
            pic_match = re.search(r'(?:src|data-src)=["\']([^"\']+)["\']', block)
            if pic_match:
                pic = pic_match.group(1).strip()

            if not pic or "arrow" in pic.lower() or ".svg" in pic.lower() or "logo" in pic.lower():
                continue

            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = urllib.parse.urljoin(self.site_url, pic)

            seen_names.add(name)
            cards.append({
                "vod_id": "star_query__%s" % urllib.parse.quote(name),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "ZakaTV · 明星",
                "style": RECT_075_STYLE
            })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if pg else 1
        rq_val = extend.get("rq", "") if isinstance(extend, dict) else ""

        # 1. 色情明星：0.75 竖屏海报
        if tid == "pornstars_all":
            star_url = "%s/?pornstars=all" % self.site_url
            if page_num > 1:
                star_url = "%s/?pornstars=all&page=%d" % (self.site_url, page_num)
            html_text = self._fetch_html(star_url)
            cards = self._parse_pornstars_list(html_text)

            return {
                "page": page_num,
                "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
                "limit": len(cards),
                "total": 9999,
                "list": cards,
                "style": RECT_075_STYLE
            }

        # 2. 标签分类：1.78 宽屏，支持 rq 筛选
        if tid.startswith("tag_"):
            tag_name = tid.replace("tag_", "")
            query_map = {"tag": tag_name}
            if rq_val:
                query_map["rq"] = rq_val
            if page_num > 1:
                query_map["page"] = str(page_num)
            target_url = "%s/?%s" % (self.site_url, urllib.parse.urlencode(query_map))
            html_text = self._fetch_html(target_url)
            cards = self._parse_card_list(html_text)
            return {
                "page": page_num,
                "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
                "limit": len(cards),
                "total": 9999,
                "list": cards,
                "style": RECT_178_STYLE
            }

        # 3. 常规厂牌分类：1.78 宽屏，支持 rq 筛选
        query_map = {"fenlei": tid}
        if rq_val:
            query_map["rq"] = rq_val
        if page_num > 1:
            query_map["page"] = str(page_num)

        target_url = "%s/?%s" % (self.site_url, urllib.parse.urlencode(query_map))
        html_text = self._fetch_html(target_url)
        cards = self._parse_card_list(html_text)

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards,
            "style": RECT_178_STYLE
        }

    def detailContent(self, ids):
        vid = ids[0] if ids else ""

        # 明星专区二级瀑布流
        if vid.startswith("star_query__"):
            star_name = urllib.parse.unquote(vid.replace("star_query__", ""))
            star_search_url = "%s/?search=%s" % (self.site_url, urllib.parse.quote(star_name))
            html_text = self._fetch_html(star_search_url)
            star_cards = self._parse_card_list(html_text)

            play_routes = []
            for item in star_cards:
                play_routes.append("%s$%s" % (item["vod_name"][:15], "vid_%s" % item["vod_id"]))

            vod = {
                "vod_id": str(vid),
                "vod_name": "【明星专区】%s" % star_name,
                "vod_pic": "",
                "vod_type": "明星专区",
                "vod_year": "2026",
                "vod_area": "中国大陆",
                "vod_remarks": "ZakaTV",
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV",
                "vod_content": "【ZakaTV官方交流群: https://t.me/+3t5XRPPo9mlkZDRl】收录演员 %s 的全部作品，共计 %d 部。" % (star_name, len(star_cards)),
                "vod_play_from": "Zaka专线",
                "vod_play_url": "#".join(play_routes) if play_routes else "作品准备中$vid_0"
            }
            return {"list": [vod]}

        # 常规正片详情
        detail_url = "%s/?play-%s-1-.html" % (self.site_url, vid)
        html_text = self._fetch_html(detail_url)

        title = "麻花资源 ID: %s" % vid
        title_match = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
        if title_match:
            raw_t = title_match.group(1).split("-在线播放")[0]
            title = html.unescape(raw_t.strip())

        pic = ""
        pic_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text, re.I)
        if pic_match:
            pic = pic_match.group(1).strip()

        main_play_url = ""
        js_url_match = re.search(r'(?:url|videoUrl|src|path)\s*[:=]\s*["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', html_text, re.I)
        if js_url_match:
            main_play_url = js_url_match.group(1)

        if not main_play_url:
            video_src_match = re.search(r'<video[^>]+src=["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', html_text, re.I)
            if video_src_match:
                main_play_url = video_src_match.group(1)

        if not main_play_url:
            all_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_text)
            valid_m3u8 = [u for u in all_m3u8 if "adc" not in u and "ad." not in u]
            if valid_m3u8:
                main_play_url = valid_m3u8[0]

        play_target = main_play_url if main_play_url else "vid_%s" % vid

        vod = {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_type": "正片",
            "vod_year": "2026",
            "vod_area": "中国大陆",
            "vod_remarks": "ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": "【ZakaTV官方交流群: https://t.me/+3t5XRPPo9mlkZDRl】麻花传媒高清专线，秒开免插件畅享。",
            "vod_play_from": "Zaka专线",
            "vod_play_url": "正片$%s" % play_target
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        real_url = id
        if id.startswith("vid_"):
            vid = id.replace("vid_", "")
            detail_url = "%s/?play-%s-1-.html" % (self.site_url, vid)
            html_text = self._fetch_html(detail_url)
            m3u8_list = [u for u in re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_text) if "adc" not in u]
            if m3u8_list:
                real_url = m3u8_list[0]

        return {
            "parse": 0,
            "playUrl": "",
            "url": real_url,
            "header": self.default_headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_num = int(pg) if pg else 1
        query_map = {"search": key}
        if page_num > 1:
            query_map["page"] = str(page_num)

        search_url = "%s/?%s" % (self.site_url, urllib.parse.urlencode(query_map))
        html_text = self._fetch_html(search_url)
        cards = self._parse_card_list(html_text)

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards,
            "style": RECT_178_STYLE
        }

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def localProxy(self, params):
        return [200, "text/plain", "ok"]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass