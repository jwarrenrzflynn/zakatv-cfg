#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import hashlib
import time
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "毒舌影视"
        self.host_m = "https://m.xnhrsb.com"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"

        self.ua_mobile = "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "app2.zstv47")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _api_raw(self, url, data=None, extra_headers=None):
        headers = {
            "User-Agent": self.ua_mobile,
            "Referer": self.host_m + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        if extra_headers:
            headers.update(extra_headers)

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json;charset=UTF-8"
            elif isinstance(data, (str, bytes)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        try:
            req = urllib.request.Request(url, data=req_data, headers=headers)
            with self.opener.open(req, timeout=10) as resp:
                code = resp.getcode()
                raw = resp.read()
                hdrs = dict(resp.headers)
                enc = hdrs.get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("latin1", errors="ignore")
                return {"code": code, "text": text, "headers": hdrs, "err": ""}
        except urllib.error.HTTPError as e:
            raw = ""
            hdrs = dict(e.headers) if hasattr(e, "headers") else {}
            try:
                err_b = e.read()
                if err_b.startswith(b"\x1f\x8b"):
                    err_b = gzip.decompress(err_b)
                raw = err_b.decode("utf-8", errors="ignore")
            except Exception:
                pass
            return {"code": e.code, "text": raw, "headers": hdrs, "err": str(e)}
        except Exception as e:
            return {"code": -1, "text": "", "headers": {}, "err": str(e)}

    def _solve_pow(self, challenge, difficulty=4):
        target_prefix = "0" * int(difficulty)
        for nonce in range(2000000):
            cand = "%s%d" % (challenge, nonce)
            digest = hashlib.sha256(cand.encode("utf-8")).hexdigest()
            if digest.startswith(target_prefix):
                return {"nonce": nonce, "hash": digest}
        return None

    def _fetch_safe(self, target_url):
        if not target_url.startswith("http"):
            target_url = self.host_m + ("/" + target_url.lstrip("/"))

        res = self._api_raw(target_url)
        if res.get("code") == 408 or "Bot detection" in res.get("text", "") or "安全绿色" in res.get("text", ""):
            self._api_raw(self.host_m + "/")
            init_res = self._api_raw(self.host_m + "/__xcdn/captcha/api/init")
            try:
                init_data = json.loads(init_res.get("text", ""))
                c = init_data.get("challenge", "")
                d = init_data.get("difficulty", 4)
                pow_res = self._solve_pow(c, d)
                if pow_res:
                    v_url = self.host_m + "/__xcdn/captcha/api/verify"
                    self._api_raw(v_url, data={"challenge": c, "nonce": pow_res["nonce"]}, extra_headers={
                        "X-CDN-VERIFY-NONCE": str(pow_res["nonce"]),
                        "X-CDN-VERIFY-RESULT": pow_res["hash"]
                    })
                    res = self._api_raw(target_url)
            except Exception:
                pass
        return res

    def homeContent(self, filter):
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "电视剧", "type_id": "2"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "短剧", "type_id": "5"},
            {"type_name": "豆瓣Top250", "type_id": "duoban"}
        ]

        if not filter:
            return {"class": classes}

        years = [{"n": "全部", "v": ""}]
        for y in range(2026, 2003, -1):
            years.append({"n": str(y), "v": str(y)})

        letters = [{"n": "全部", "v": ""}]
        for code in range(ord('A'), ord('Z') + 1):
            letters.append({"n": chr(code), "v": chr(code)})
        letters.append({"n": "0~9", "v": "0-9"})

        sorts = [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"}
        ]

        filter_movie = [
            {
                "key": "class",
                "name": "影片类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "恐怖", "v": "恐怖"},
                    {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"},
                    {"n": "警匪", "v": "警匪"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"},
                    {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"}, {"n": "悬疑", "v": "悬疑"},
                    {"n": "惊悚", "v": "惊悚"}, {"n": "经典", "v": "经典"}, {"n": "青春", "v": "青春"}, {"n": "文艺", "v": "文艺"},
                    {"n": "微电影", "v": "微电影"}, {"n": "古装", "v": "古装"}, {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"},
                    {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"}, {"n": "网络电影", "v": "网络电影"}
                ]
            },
            {"key": "year", "name": "年份", "value": years},
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"},
                    {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"},
                    {"n": "韩国", "v": "韩国"}, {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                    {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"}, {"n": "其他", "v": "其他"}
                ]
            },
            {
                "key": "lang",
                "name": "语言",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"},
                    {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "法语", "v": "法语"},
                    {"n": "德语", "v": "德语"}, {"n": "其它", "v": "其它"}
                ]
            },
            {"key": "letter", "name": "字母", "value": letters},
            {"key": "by", "name": "排序", "value": sorts}
        ]

        filter_tv = [
            {
                "key": "class",
                "name": "影片类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"}, {"n": "青春偶像", "v": "青春偶像"},
                    {"n": "喜剧", "v": "喜剧"}, {"n": "家庭", "v": "家庭"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动作", "v": "动作"},
                    {"n": "奇幻", "v": "奇幻"}, {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"}, {"n": "经典", "v": "经典"},
                    {"n": "乡村", "v": "乡村"}, {"n": "情景", "v": "情景"}, {"n": "商战", "v": "商战"}, {"n": "网剧", "v": "网剧"},
                    {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "年份", "value": years},
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "韩国", "v": "韩国"}, {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"}, {"n": "日本", "v": "日本"}, {"n": "美国", "v": "美国"}, {"n": "泰国", "v": "泰国"},
                    {"n": "英国", "v": "英国"}, {"n": "新加坡", "v": "新加坡"}, {"n": "其他", "v": "其他"}
                ]
            },
            {
                "key": "lang",
                "name": "语言",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"},
                    {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}
                ]
            },
            {"key": "letter", "name": "字母", "value": letters},
            {"key": "by", "name": "排序", "value": sorts}
        ]

        filter_va = [
            {
                "key": "class",
                "name": "影片类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "选秀", "v": "选秀"}, {"n": "情感", "v": "情感"}, {"n": "访谈", "v": "访谈"},
                    {"n": "播报", "v": "播报"}, {"n": "旅游", "v": "旅游"}, {"n": "音乐", "v": "音乐"}, {"n": "美食", "v": "美食"},
                    {"n": "纪实", "v": "纪实"}, {"n": "曲艺", "v": "曲艺"}, {"n": "生活", "v": "生活"}, {"n": "游戏互动", "v": "游戏互动"},
                    {"n": "财经", "v": "财经"}, {"n": "求职", "v": "求职"}
                ]
            },
            {"key": "year", "name": "年份", "value": years},
            {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "港台", "v": "港台"}, {"n": "日韩", "v": "日韩"}, {"n": "欧美", "v": "欧美"}]},
            {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}]},
            {"key": "letter", "name": "字母", "value": letters},
            {"key": "by", "name": "排序", "value": sorts}
        ]

        filter_ct = [
            {
                "key": "class",
                "name": "影片类型",
                "value": [
                    {"n": "全部", "v": ""}, {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"}, {"n": "热血", "v": "热血"},
                    {"n": "推理", "v": "推理"}, {"n": "搞笑", "v": "搞笑"}, {"n": "冒险", "v": "冒险"}, {"n": "萝莉", "v": "萝莉"},
                    {"n": "校园", "v": "校园"}, {"n": "动作", "v": "动作"}, {"n": "机战", "v": "机战"}, {"n": "运动", "v": "运动"},
                    {"n": "战争", "v": "战争"}, {"n": "少年", "v": "少年"}, {"n": "少女", "v": "少女"}, {"n": "社会", "v": "社会"},
                    {"n": "原创", "v": "原创"}, {"n": "亲子", "v": "亲子"}, {"n": "益智", "v": "益智"}, {"n": "励志", "v": "励志"},
                    {"n": "其他", "v": "其他"}
                ]
            },
            {"key": "year", "name": "年份", "value": years},
            {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "国产", "v": "国产"}, {"n": "日本", "v": "日本"}, {"n": "欧美", "v": "欧美"}, {"n": "其他", "v": "其他"}]},
            {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}]},
            {"key": "letter", "name": "字母", "value": letters},
            {"key": "by", "name": "排序", "value": sorts}
        ]

        filter_dj = [
            {
                "key": "class",
                "name": "影片类型",
                "value": [{"n": "全部", "v": ""}, {"n": "短剧", "v": "短剧"}]
            },
            {
                "key": "year",
                "name": "年份",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"}
                ]
            },
            {
                "key": "area",
                "name": "地区",
                "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}]
            },
            {
                "key": "lang",
                "name": "语言",
                "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}]
            },
            {"key": "letter", "name": "字母", "value": letters},
            {"key": "by", "name": "排序", "value": sorts}
        ]

        filters = {
            "1": filter_movie,
            "2": filter_tv,
            "3": filter_va,
            "4": filter_ct,
            "5": filter_dj,
            "duoban": [{"key": "class", "name": "影片类型", "value": [{"n": "全部", "v": ""}, {"n": "动作片", "v": "动作片"}, {"n": "喜剧片", "v": "喜剧片"}, {"n": "爱情片", "v": "爱情片"}, {"n": "科幻片", "v": "科幻片"}, {"n": "恐怖片", "v": "恐怖片"}, {"n": "剧情片", "v": "剧情片"}, {"n": "战争片", "v": "战争片"}, {"n": "纪录片", "v": "纪录片"}, {"n": "悬疑片", "v": "悬疑片"}, {"n": "犯罪片", "v": "犯罪片"}]}]
        }

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        slug = str(tid).strip("/")

        ext = extend if isinstance(extend, dict) else {}
        c_class = ext.get("class", "")
        c_area = ext.get("area", "")
        c_lang = ext.get("lang", "")
        c_year = ext.get("year", "")
        c_letter = ext.get("letter", "")
        c_by = ext.get("by", "")
        cur_pg = str(pg or "1")

        parts = [
            slug,
            "",
            "",
            quote(c_class) if c_class else "",
            quote(c_area) if c_area else "",
            quote(c_lang) if c_lang else "",
            quote(c_year) if c_year else "",
            quote(c_letter) if c_letter else "",
            quote(c_by) if c_by else "",
            cur_pg if cur_pg != "1" else "",
            "",
            ""
        ]
        sub_path = "-".join(parts) + ".html"
        url = "%s/dsshiyisw/%s" % (self.host_m, sub_path)

        res = self._fetch_safe(url)
        html = res.get("text", "")

        vod_list = []
        main_content = html
        if '<div class="mrb"' in html:
            main_content = html.split('<div class="mrb"')[1]
            if '<div class="page"' in main_content:
                main_content = main_content.split('<div class="page"')[0]

        blocks = re.findall(r'<li[^>]*>([\s\S]*?)</li>', main_content, re.I)
        for b in blocks:
            href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', b, re.I)
            pic_m = re.search(r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']', b, re.I)
            name_m = re.search(r'<(?:span|h3|h2|p)[^>]*class=["\'](?:dytit|name|title)["\'][^>]*>([\s\S]*?)</', b, re.I)
            remark_m = re.search(r'<span[^>]*class=["\']hdinfo["\'][^>]*>([\s\S]*?)</span>', b, re.I)

            if href_m and pic_m and name_m:
                raw_href = href_m.group(1).strip()
                if raw_href in ("/", "#", self.host_m, self.host_m + "/") or "dsshiyisw" in raw_href or "javascript" in raw_href:
                    continue

                clean_title = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
                if not clean_title or clean_title == "未命名视频":
                    continue

                raw_pic = pic_m.group(1).strip()
                clean_pic = "https:" + raw_pic if raw_pic.startswith("//") else (self.host_m + raw_pic if raw_pic.startswith("/") else raw_pic)
                clean_remark = re.sub(r'<[^>]+>', '', remark_m.group(1)).strip() if remark_m else ""

                vod_list.append({
                    "vod_id": raw_href,
                    "vod_name": clean_title,
                    "vod_pic": clean_pic,
                    "vod_remarks": format_remarks("ZakaTV", clean_remark),
                    "style": {"type": "rect", "ratio": 0.75}
                })

        return {
            "page": int(cur_pg),
            "pagecount": 9999,
            "limit": len(vod_list),
            "total": 999999,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = raw_id
        if not target_url.startswith("http"):
            target_url = self.host_m + ("/" + target_url.lstrip("/"))

        res = self._fetch_safe(target_url)
        html = res.get("text", "")

        title_m = re.search(r'<h1>([\s\S]*?)</h1>', html, re.I)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "高清正片"

        pic_m = re.search(r'<div[^>]*class=["\']dyimg["\'][^>]*>[\s\S]*?<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
        pic = ""
        if pic_m:
            raw_p = pic_m.group(1).strip()
            pic = "https:" + raw_p if raw_p.startswith("//") else (self.host_m + raw_p if raw_p.startswith("/") else raw_p)

        desc_m = re.search(r'<div[^>]*class=["\']yp_context["\'][^>]*>([\s\S]*?)</div>', html, re.I)
        raw_desc = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip() if desc_m else "暂无剧情简介"
        content = "【🔥 官方交流群: %s】\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n%s" % (self.tgGroup, raw_desc)

        boxes = re.findall(r'<div[^>]*class=["\']mi_paly_box["\'][^>]*>([\s\S]*?)</div>\s*</div>\s*</div>', html, re.I)
        if not boxes:
            boxes = re.findall(r'<div[^>]*class=["\']mi_paly_box["\'][^>]*>([\s\S]*?)(?=<div[^>]*class=["\']mi_paly_box["\']|$)', html, re.I)

        clean_tabs = []
        play_tracks = []

        for box in boxes:
            t_m = re.search(r'<div[^>]*class=["\']ypxingq_t["\'][^>]*>([\s\S]*?)</div>', box, re.I)
            raw_t = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else ""
            line_name = raw_t.replace("-在线播放", "").strip() or "Zaka专线"

            a_items = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', box, re.I)
            ep_list = []
            for href, ep_name in a_items:
                clean_name = re.sub(r'<[^>]+>', '', ep_name).strip()
                if "app2.zstv47" in href or "APP" in clean_name or "下载" in clean_name:
                    continue
                if "/dsshiyipy/" not in href and "play" not in href:
                    continue
                full_href = href if href.startswith("http") else (self.host_m + ("/" + href.lstrip("/")))
                ep_list.append("%s$%s" % (clean_name, full_href))

            if ep_list:
                clean_tabs.append(line_name)
                play_tracks.append("#".join(ep_list))

        if not play_tracks:
            clean_tabs = ["Zaka专线"]
            play_tracks = ["正片$%s" % target_url]

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": "ZakaTV",
            "vod_content": content,
            "vod_play_from": "$$$".join(clean_tabs),
            "vod_play_url": "$$$".join(play_tracks)
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_url = str(id).strip()
        if not play_url.startswith("http"):
            play_url = self.host_m + ("/" + play_url.lstrip("/"))

        res = self._fetch_safe(play_url)
        html = res.get("text", "")

        m = re.search(r'"url"\s*:\s*"([^"]+)"', html)
        if m:
            raw_target = m.group(1).replace("\\/", "/")
            if ".m3u8" in raw_target or ".mp4" in raw_target:
                return {
                    "parse": 0,
                    "url": raw_target,
                    "header": {
                        "User-Agent": self.ua_mobile,
                        "Referer": play_url
                    }
                }

        ifr_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
        if ifr_m:
            cand_ifr = ifr_m.group(1).strip()
            if cand_ifr.startswith("//"):
                cand_ifr = "https:" + cand_ifr
            elif cand_ifr.startswith("/"):
                cand_ifr = self.host_m + cand_ifr

            return {
                "parse": 1,
                "playUrl": "",
                "url": cand_ifr,
                "header": {
                    "User-Agent": self.ua_mobile,
                    "Referer": play_url
                }
            }

        return {
            "parse": 1,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.ua_mobile,
                "Referer": self.host_m + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        cur_pg = str(pg or "1")
        url = "%s/dsshiyisc/%s----------%s---.html" % (self.host_m, quote(key), cur_pg)
        res = self._fetch_safe(url)
        html = res.get("text", "")

        vod_list = []
        main_content = html
        if '<div class="mrb"' in html:
            main_content = html.split('<div class="mrb"')[1]
            if '<div class="page"' in main_content:
                main_content = main_content.split('<div class="page"')[0]

        blocks = re.findall(r'<li[^>]*>([\s\S]*?)</li>', main_content, re.I)
        for b in blocks:
            href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', b, re.I)
            pic_m = re.search(r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']', b, re.I)
            name_m = re.search(r'<(?:span|h3|h2|p)[^>]*class=["\'](?:dytit|name|title)["\'][^>]*>([\s\S]*?)</', b, re.I)
            remark_m = re.search(r'<span[^>]*class=["\']hdinfo["\'][^>]*>([\s\S]*?)</span>', b, re.I)

            if href_m and pic_m and name_m:
                raw_href = href_m.group(1).strip()
                if raw_href in ("/", "#", self.host_m, self.host_m + "/") or "dsshiyisw" in raw_href or "javascript" in raw_href:
                    continue

                clean_title = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
                if not clean_title or clean_title == "未命名视频":
                    continue

                raw_pic = pic_m.group(1).strip()
                clean_pic = "https:" + raw_pic if raw_pic.startswith("//") else (self.host_m + raw_pic if raw_pic.startswith("/") else raw_pic)
                clean_remark = re.sub(r'<[^>]+>', '', remark_m.group(1)).strip() if remark_m else ""

                vod_list.append({
                    "vod_id": raw_href,
                    "vod_name": clean_title,
                    "vod_pic": clean_pic,
                    "vod_remarks": format_remarks("ZakaTV", clean_remark),
                    "style": {"type": "rect", "ratio": 0.75}
                })

        return {
            "page": int(cur_pg),
            "pagecount": 9999,
            "limit": len(vod_list),
            "total": 999999,
            "list": vod_list
        }

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]