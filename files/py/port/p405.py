#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
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
        def getProxyUrl(self): return "http://127.0.0.1:9978/proxy?do=py"


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.defaultHost = "https://ptt01.com"
        self.siteUrl = self.defaultHost
        self.siteName = "三级片资源"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
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
        cached_site = self.getCache("ptt01_dynamic_site_url")
        if cached_site and cached_site.startswith("http"):
            self.siteUrl = cached_site.strip().rstrip("/")
        else:
            self._refresh_site_url()
        return True

    def getName(self):
        return "Zaka影院·动态发布自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def _refresh_site_url(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        for nav in self.navUrls:
            text = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            if not text:
                continue
            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unquoted = urllib.parse.unquote(decoded)
                    if "[" in unquoted and (self.siteName in unquoted or "稀缺资源" in unquoted):
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            if name == self.siteName or name == "稀缺资源":
                                cand_urls = []
                                main_url = item.get("url", "")
                                if main_url:
                                    cand_urls.append(main_url)
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)

                                for c_url in cand_urls:
                                    parsed = urllib.parse.urlparse(c_url)
                                    base = "%s://%s" % (parsed.scheme, parsed.netloc)
                                    chk = self._fetch(base + "/p/1", check_host=False)
                                    if chk.get("code") == 200:
                                        self.siteUrl = base
                                        self.setCache("ptt01_dynamic_site_url", base)
                                        return True
                except Exception:
                    continue

        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                if attempt == 0:
                    continue
                return {"code": e.code, "text": "", "err": str(e), "final_url": target_url}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": "timeout", "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🎬 电影", "type_id": "1"},
            {"type_name": "📺 电视剧", "type_id": "3"},
            {"type_name": "🌸 动漫", "type_id": "4"},
            {"type_name": "🎤 综艺", "type_id": "2"},
            {"type_name": "⚡ 短剧", "type_id": "66"},
            {"type_name": "⚽ 体育", "type_id": "53"}
        ]

        year_list = [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "2019", "v": "2019"},
            {"n": "2018", "v": "2018"},
            {"n": "2017", "v": "2017"},
            {"n": "2016", "v": "2016"}
        ]

        filters = {
            "1": [
                {
                    "key": "c",
                    "name": "类型",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "伦理", "v": "33"},
                        {"n": "动作", "v": "5"},
                        {"n": "喜剧", "v": "6"},
                        {"n": "爱情", "v": "7"},
                        {"n": "科幻", "v": "8"},
                        {"n": "恐怖", "v": "9"},
                        {"n": "犯罪", "v": "10"},
                        {"n": "战争", "v": "11"},
                        {"n": "动漫", "v": "12"},
                        {"n": "剧情", "v": "13"},
                        {"n": "纪录", "v": "30"},
                        {"n": "悬疑", "v": "34"},
                        {"n": "动画", "v": "35"},
                        {"n": "解说", "v": "32"},
                        {"n": "其他", "v": "48"}
                    ]
                },
                {
                    "key": "area_id",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "2"},
                        {"n": "香港", "v": "5"},
                        {"n": "台湾", "v": "4"},
                        {"n": "韩国", "v": "17"},
                        {"n": "日本", "v": "18"},
                        {"n": "欧美", "v": "6"},
                        {"n": "泰国", "v": "10"},
                        {"n": "印度", "v": "14"},
                        {"n": "其他", "v": "3"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ],
            "3": [
                {
                    "key": "c",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "19"},
                        {"n": "香港", "v": "20"},
                        {"n": "台湾", "v": "81"},
                        {"n": "日本", "v": "83"},
                        {"n": "韩国", "v": "82"},
                        {"n": "欧美", "v": "22"},
                        {"n": "泰国", "v": "92"},
                        {"n": "其他", "v": "23"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ],
            "4": [
                {
                    "key": "c",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "26"},
                        {"n": "日本", "v": "86"},
                        {"n": "韩国", "v": "87"},
                        {"n": "欧美", "v": "27"},
                        {"n": "其他", "v": "28"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ],
            "2": [
                {
                    "key": "c",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "15"},
                        {"n": "台湾", "v": "89"},
                        {"n": "香港", "v": "88"},
                        {"n": "日本", "v": "90"},
                        {"n": "韩国", "v": "91"},
                        {"n": "欧美", "v": "18"},
                        {"n": "其他", "v": "16"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ],
            "66": [
                {
                    "key": "c",
                    "name": "类型",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "爽剧", "v": "67"},
                        {"n": "言情", "v": "68"},
                        {"n": "穿越", "v": "70"},
                        {"n": "悬疑", "v": "71"},
                        {"n": "古装", "v": "73"},
                        {"n": "都市", "v": "80"},
                        {"n": "甜宠", "v": "84"},
                        {"n": "恋爱", "v": "85"},
                        {"n": "其他", "v": "74"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ],
            "53": [
                {
                    "key": "c",
                    "name": "项目",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "足球", "v": "54"},
                        {"n": "篮球", "v": "55"},
                        {"n": "游戏", "v": "59"},
                        {"n": "撞球", "v": "63"},
                        {"n": "网球", "v": "64"},
                        {"n": "其他", "v": "93"}
                    ]
                },
                {
                    "key": "year",
                    "name": "年代",
                    "value": year_list
                }
            ]
        }

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def _parse_card_list(self, html_text):
        cards = []
        seen = set()
        item_blocks = re.findall(r'(<div[^>]+class=["\'][^"\']*item[^"\']*["\'][\s\S]*?</div>\s*</div>\s*</div>)', html_text, re.I)
        if not item_blocks:
            item_blocks = re.findall(r'(<div[^>]+class=["\'][^"\']*card[^"\']*["\'][\s\S]*?</div>\s*</div>)', html_text, re.I)

        for block in item_blocks:
            m_href = re.search(r'href=["\'](/(\d+))["\']', block)
            if not m_href:
                continue
            path = m_href.group(1)
            if path in seen:
                continue

            title = ""
            m_alt = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block, re.I)
            if m_alt and m_alt.group(1).strip():
                title = m_alt.group(1).strip()

            if not title:
                m_title = re.search(r'title=["\']([^"\']+)["\']', block)
                if m_title and m_title.group(1).strip():
                    title = m_title.group(1).strip()

            if not title:
                m_text_link = re.search(r'<a[^>]+href=["\']/%s["\'][^>]*>([\s\S]*?)</a>' % m_href.group(2), block, re.I)
                if m_text_link:
                    cand_t = re.sub(r'<[^>]+>', '', m_text_link.group(1)).strip()
                    if cand_t:
                        title = cand_t

            if not title:
                title = "视频 %s" % m_href.group(2)

            img_src = ""
            m_img = re.search(r'(?:src|data-original|data-src)=["\']([^"\']+)["\']', block, re.I)
            if m_img:
                cand = m_img.group(1).strip()
                if not any(bad in cand.lower() for bad in ("logo", "avatar", "icon", ".svg", "data:image")):
                    img_src = ("https:" + cand) if cand.startswith("//") else ((self.siteUrl + cand) if cand.startswith("/") else cand)

            badge_parts = []
            m_left = re.search(r'class=["\'][^"\']*imagelabel-bottom-left[^"\']*["\'][^>]*>([\s\S]*?)</div>', block, re.I)
            if m_left:
                c_left = re.sub(r'<[^>]+>', '', m_left.group(1)).strip()
                if c_left:
                    badge_parts.append(c_left)

            m_right = re.search(r'class=["\'][^"\']*imagelabel-bottom-right[^"\']*["\'][^>]*>([\s\S]*?)</div>', block, re.I)
            if m_right:
                c_right = re.sub(r'<[^>]+>', '', m_right.group(1)).strip()
                if c_right:
                    badge_parts.append(c_right)

            if not badge_parts:
                badges = re.findall(r'<span[^>]+class=["\'][^"\']*badge[^"\']*["\'][^>]*>([^<]+)</span>', block, re.I)
                for bg in badges:
                    cl_b = bg.strip()
                    if cl_b and cl_b not in badge_parts and not cl_b.startswith("fa-"):
                        badge_parts.append(cl_b)

            source_remark = " ".join(badge_parts).strip()
            remarks = ("ZakaTV | %s" % source_remark) if source_remark else "ZakaTV"

            seen.add(path)
            cards.append({
                "vod_id": path,
                "vod_name": html_lib.unescape(title),
                "vod_pic": img_src,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 0.75}
            })
        return cards

    def categoryContent(self, tid, pg, filter, extend):
        clean_tid = str(tid).replace("/p/", "").strip("/")
        ext_dict = extend if isinstance(extend, dict) else {}

        c_val = str(ext_dict.get("c", "")).strip()
        area_id_val = str(ext_dict.get("area_id", "")).strip()
        year_val = str(ext_dict.get("year", "")).strip()
        page_val = str(pg) if str(pg).isdigit() else "1"

        if c_val:
            base_path = "/p/%s/c/%s" % (clean_tid, c_val)
        else:
            base_path = "/p/%s" % clean_tid

        query_params = []
        if area_id_val:
            query_params.append("area_id=%s" % area_id_val)
        if year_val:
            query_params.append("year=%s" % year_val)
        if int(page_val) > 1:
            query_params.append("page=%s" % page_val)

        if query_params:
            req_path = "%s?%s" % (base_path, "&".join(query_params))
        else:
            req_path = base_path

        res = self._fetch(req_path)
        cards = self._parse_card_list(res.get("text", ""))

        return {"page": int(page_val), "pagecount": 99, "limit": len(cards), "total": 9999, "list": cards}

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        vid_m = re.search(r'(\d+)', raw_id)
        if not vid_m:
            return {"list": []}
        vid = vid_m.group(1)

        play_home_path = "/%s" % vid
        detail_path = "/v/%s" % vid

        res_play = self._fetch(play_home_path)
        play_html = res_play.get("text", "")

        res_detail = self._fetch(detail_path)
        detail_html = res_detail.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', detail_html if detail_html else play_html, re.I)
        vod_name = title_m.group(1).split("-")[0].strip() if title_m else ("视频 %s" % vid)

        vod_pic = ""
        m_og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', play_html, re.I)
        if not m_og_img:
            m_og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', detail_html, re.I)
        if m_og_img:
            vod_pic = m_og_img.group(1).strip()
        if not vod_pic:
            m_img = re.search(r'<img[^>]+src=["\']([^"\']+/images/node/[^"\']+)["\']', detail_html if detail_html else play_html, re.I)
            if m_img:
                vod_pic = m_img.group(1).strip()

        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        elif vod_pic.startswith("/"):
            vod_pic = self.siteUrl + vod_pic

        vod_year = ""
        m_yr = re.search(r'<th>年代</th>\s*<td>([^<]+)</td>', detail_html, re.I)
        if m_yr:
            vod_year = m_yr.group(1).strip()

        vod_remarks = "ZakaTV"
        m_st = re.search(r'<th>状态</th>\s*<td>([^<]+)</td>', detail_html, re.I)
        if m_st:
            st_text = m_st.group(1).strip()
            vod_remarks = ("ZakaTV | %s %s" % (vod_year, st_text)).strip()
        elif vod_year:
            vod_remarks = "ZakaTV | %s" % vod_year

        actor_list = re.findall(r'<a[^>]+href=["\']/q/actors/[^"\']*["\'][^>]*>([^<]+)</a>', detail_html, re.I)
        vod_actor = (", ".join(actor_list)) if actor_list else self.brandActor

        dir_list = re.findall(r'<a[^>]+href=["\']/q/director/[^"\']*["\'][^>]*>([^<]+)</a>', detail_html, re.I)
        vod_director = (", ".join(dir_list)) if dir_list else self.brandDirector

        ep_numbers = []
        raw_seq_links = re.findall(r'<a[^>]+class=["\'][^"\']*seq[^"\']*["\'][^>]+href=["\'](/%s/(\d+)(?:/(\d+))?)["\'][^>]*>([^<]+)</a>' % vid, play_html + detail_html, re.I)
        for full_h, ep_num, line_cd, text_num in raw_seq_links:
            num = int(ep_num)
            if num not in ep_numbers:
                ep_numbers.append(num)

        if not ep_numbers:
            m_total = re.search(r'"total":\s*(\d+)', play_html + detail_html)
            if m_total:
                total_cnt = int(m_total.group(1))
                ep_numbers = list(range(1, total_cnt + 1))
            else:
                ep_numbers = [1]
        else:
            ep_numbers.sort()

        lines = []
        tab_list_match = re.search(r'<ul[^>]+class=["\'][^"\']*nav-tabs[^"\']*["\'][^>]*>([\s\S]*?)</ul>', play_html, re.I)
        if tab_list_match:
            raw_tab_links = re.findall(r'<a[^>]+href=["\'](/%s/\d+/(\d+))["\'][^>]*>([\s\S]*?)</a>' % vid, tab_list_match.group(1), re.I)
            for href, line_code, tab_name_raw in raw_tab_links:
                line_name = re.sub(r'<[^>]+>', '', tab_name_raw).strip()
                if line_name and not any(bad in line_name for bad in ("排序", "选集", "快捷键")):
                    lines.append({"name": line_name, "code": line_code})

        if not lines:
            line_pattern = re.findall(r'href=["\']/%s/1/(\d+)["\'][^>]*>([^<]+)</a>' % vid, play_html, re.I)
            for l_code, l_name in line_pattern:
                clean_n = l_name.strip()
                if clean_n:
                    lines.append({"name": clean_n, "code": l_code})

        play_from_items = []
        play_url_items = []

        if lines:
            for line_obj in lines:
                l_name = line_obj["name"]
                l_code = line_obj["code"]
                ep_list = []
                for ep in ep_numbers:
                    ep_url = "/%s/%d/%s" % (vid, ep, l_code)
                    ep_title = "第%d集" % ep if len(ep_numbers) > 1 else "正片"
                    ep_list.append("%s$%s" % (ep_title, ep_url))
                play_from_items.append("📺%s" % l_name)
                play_url_items.append("#".join(ep_list))
        else:
            ep_list = []
            for ep in ep_numbers:
                ep_url = "/%s/%d" % (vid, ep)
                ep_title = "第%d集" % ep if len(ep_numbers) > 1 else "正片"
                ep_list.append("%s$%s" % (ep_title, ep_url))
            play_from_items.append("📺Zaka专线")
            play_url_items.append("#".join(ep_list))

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_bg": vod_pic,
                "vod_background": vod_pic,
                "vod_banner": vod_pic,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_remarks": vod_remarks,
                "vod_content": "PTT01 官方直连专线 · 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_play_from": "$$$".join(play_from_items),
                "vod_play_url": "$$$".join(play_url_items)
            }]
        }

    def _clean_m3u8_text(self, target_m3u8_url, m3u8_text):
        parsed_target = urllib.parse.urlparse(target_m3u8_url)
        base_dir = target_m3u8_url.rsplit("/", 1)[0] + "/"
        domain_root = "%s://%s" % (parsed_target.scheme, parsed_target.netloc)

        ad_pattern = re.compile(
            r'(?:^\/\d{8}\/[a-f0-9]{16}\/seg_|\/mov\/AD\/|adjump|erlgnf\.com|seg_\d+\.jpg|\/202\d{5}\/[a-z0-9]+\/seg_)',
            re.I
        )

        lines = [line.strip() for line in m3u8_text.replace("\r", "").split("\n") if line.strip()]
        output_lines = []

        pending_extinf = None
        pending_discontinuity = False
        has_ad_removed = False

        for line in lines:
            upper_line = line.upper()

            if upper_line.startswith("#DISC-NOISE") or "PPVOD-AD-INJECTED" in upper_line:
                continue

            if upper_line.startswith("#EXT-X-KEY") and "METHOD=NONE" in upper_line:
                continue

            if upper_line.startswith("#EXT-X-KEY") and ad_pattern.search(line):
                continue

            if upper_line.startswith("#EXT-X-DISCONTINUITY"):
                pending_discontinuity = True
                continue

            if upper_line.startswith("#EXT-X-KEY"):
                def _fix_key_uri(match):
                    key_uri = match.group(1)
                    if not key_uri.startswith("http"):
                        key_uri = urllib.parse.urljoin(base_dir, key_uri)
                    return 'URI="%s"' % key_uri

                fixed_key_line = re.sub(r'URI=["\']([^"\']+)["\']', _fix_key_uri, line)

                if pending_discontinuity or has_ad_removed:
                    if output_lines and not output_lines[-1].upper().startswith("#EXT-X-DISCONTINUITY"):
                        output_lines.append("#EXT-X-DISCONTINUITY")
                    pending_discontinuity = False
                    has_ad_removed = False

                output_lines.append(fixed_key_line)
                continue

            if upper_line.startswith("#EXTINF"):
                pending_extinf = line
                continue

            if not line.startswith("#"):
                if ad_pattern.search(line):
                    pending_extinf = None
                    has_ad_removed = True
                else:
                    if pending_discontinuity or has_ad_removed:
                        if output_lines and not output_lines[-1].upper().startswith("#EXT-X-DISCONTINUITY"):
                            output_lines.append("#EXT-X-DISCONTINUITY")
                        pending_discontinuity = False
                        has_ad_removed = False

                    if pending_extinf:
                        output_lines.append(pending_extinf)
                        pending_extinf = None

                    full_ts_url = line
                    if not full_ts_url.startswith("http"):
                        if full_ts_url.startswith("/"):
                            full_ts_url = domain_root + full_ts_url
                        else:
                            full_ts_url = base_dir + full_ts_url

                    output_lines.append(full_ts_url)
                continue

            output_lines.append(line)

        return "\n".join(output_lines)

    def playerContent(self, flag, id, vipFlags):
        play_path = str(id).strip()
        target_m3u8 = ""

        if play_path.startswith("http") and ".m3u8" in play_path:
            target_m3u8 = play_path
        else:
            fetch_url = play_path
            res = self._fetch(fetch_url)
            html_text = res.get("text", "")

            m_src = re.search(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
            if m_src:
                target_m3u8 = m_src.group(1).strip()

            if not target_m3u8:
                m_content_url = re.search(r'"contentUrl":\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
                if m_content_url:
                    target_m3u8 = m_content_url.group(1).replace("\\/", "/")

            if not target_m3u8:
                m_direct = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html_text)
                if m_direct:
                    target_m3u8 = m_direct.group(0).replace("\\/", "/")

            if not target_m3u8:
                m_iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
                if m_iframe:
                    sub_url = m_iframe.group(1).strip()
                    if sub_url.startswith("//"):
                        sub_url = "https:" + sub_url
                    elif sub_url.startswith("/"):
                        sub_url = self.siteUrl + sub_url
                    res_ifr = self._fetch(sub_url, referer=self.siteUrl + fetch_url)
                    ifr_text = res_ifr.get("text", "")
                    m_ifr_m3u8 = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', ifr_text)
                    if m_ifr_m3u8:
                        target_m3u8 = m_ifr_m3u8.group(0).replace("\\/", "/")

        final_play_url = target_m3u8 if target_m3u8 else play_path

        if ".m3u8" in final_play_url.lower():
            try:
                base_proxy = self.getProxyUrl() if hasattr(self, "getProxyUrl") else "http://127.0.0.1:9978/proxy?do=py"
                b64_target = base64.urlsafe_b64encode(final_play_url.encode("utf-8")).decode("utf-8")
                sep = "&" if "?" in base_proxy else "?"
                final_play_url = "%s%surl=%s" % (base_proxy, sep, b64_target)
            except Exception:
                pass

        return {
            "parse": 0,
            "jx": 0,
            "url": final_play_url,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/"
            },
            "contentType": "application/vnd.apple.mpegurl" if ".m3u8" in final_play_url.lower() else "video/mp4",
            "format": "hls" if ".m3u8" in final_play_url.lower() else "mp4"
        }

    def localProxy(self, params):
        raw_b64 = ""
        if isinstance(params, dict):
            raw_b64 = params.get("url", "")
        elif isinstance(params, str):
            raw_b64 = params

        if not raw_b64:
            return [400, "text/plain; charset=utf-8", "Missing URL parameter"]

        try:
            target_url = base64.urlsafe_b64decode(raw_b64.encode("utf-8")).decode("utf-8")
        except Exception:
            target_url = urllib.parse.unquote(raw_b64)

        fetch_res = self._fetch(target_url, referer=target_url, check_host=False)
        m3u8_text = fetch_res.get("text", "")

        if not m3u8_text or "#EXTM3U" not in m3u8_text:
            return [fetch_res.get("code", 502), "text/plain; charset=utf-8", "Failed to fetch M3U8"]

        if "#EXT-X-STREAM-INF" in m3u8_text and "#EXTINF" not in m3u8_text:
            base_dir = target_url.rsplit("/", 1)[0] + "/"
            lines = [l.strip() for l in m3u8_text.split("\n") if l.strip()]
            for l in lines:
                if not l.startswith("#"):
                    sub_url = urllib.parse.urljoin(base_dir, l)
                    sub_fetch = self._fetch(sub_url, referer=target_url, check_host=False)
                    if sub_fetch.get("text") and "#EXTM3U" in sub_fetch.get("text"):
                        target_url = sub_url
                        m3u8_text = sub_fetch.get("text")
                    break

        cleaned_m3u8 = self._clean_m3u8_text(target_url, m3u8_text)
        return [200, "application/vnd.apple.mpegurl", cleaned_m3u8]

    def searchContent(self, key, quick, pg="1"): return {"list": []}
    def action(self, action): return {"msg": "ok"}
    def liveContent(self): return ""
    def destroy(self): pass
