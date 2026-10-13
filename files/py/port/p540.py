# -*- coding: utf-8 -*-
import sys
import os
import re
import json
import gzip
import zlib
import ssl
import html as html_parser
import urllib.request
import urllib.parse

try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        pass

class Spider(Spider):
    def __init__(self):
        self.site_url = "https://4k-av.com"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }

    def init(self, extend=""):
        pass

    def _fetch(self, url, headers=None):
        req_headers = dict(self.header)
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        resp = opener.open(req, timeout=15)
        raw = resp.read()
        final_url = resp.geturl()
        status_code = resp.getcode()
        resp_headers = dict(resp.headers)

        encoding = resp_headers.get("Content-Encoding", "").lower()
        if "gzip" in encoding:
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        elif "deflate" in encoding:
            try:
                raw = zlib.decompress(raw)
            except Exception:
                pass

        try:
            html_text = raw.decode("utf-8")
        except Exception:
            try:
                html_text = raw.decode("gbk", errors="ignore")
            except Exception:
                html_text = raw.decode("latin1", errors="ignore")

        return status_code, final_url, resp_headers, html_text

    def _clean_text(self, text):
        if not text:
            return ""
        text = html_parser.unescape(text)
        text = re.sub(r'<[^>]+>', '', text)
        return text.replace("\r", "").replace("\n", "").replace("\t", "").strip()

    def _extract_image(self, block_html, href=""):
        patterns = [
            r'data-src=["\']([^"\']+)["\']',
            r'data-original=["\']([^"\']+)["\']',
            r'data-lazy=["\']([^"\']+)["\']',
            r'<img[^>]*src=["\']([^"\']+)["\']',
            r'background(?:-image)?:\s*url\(["\']?([^"\'\)]+)["\']?\)'
        ]
        for pat in patterns:
            m = re.search(pat, block_html, re.I)
            if m:
                img_url = m.group(1).strip()
                if img_url and not img_url.startswith("data:image"):
                    if img_url.startswith("//"):
                        return "https:" + img_url
                    elif img_url.startswith("/"):
                        return self.site_url + img_url
                    return img_url
        if href and href.startswith(("/tv/", "/movie/")):
            clean_href = href.rstrip("/")
            return "%s%s/poster_nail.jpg" % (self.site_url, clean_href)
        return ""

    def homeContent(self, filter):
        tag_list = [
            ("tag_dongzuo", "动作"),
            ("tag_juqing", "剧情"),
            ("tag_maoxian", "冒险"),
            ("tag_xiju", "喜剧"),
            ("tag_guocanju", "国产剧"),
            ("tag_kongbu", "恐怖"),
            ("tag_zhanzheng", "战争"),
            ("tag_kehuan", "科幻"),
            ("tag_donghua", "动画"),
            ("tag_hanju", "韩剧"),
            ("tag_fanzui", "犯罪"),
            ("tag_jilupian", "纪录片"),
            ("tv", "电视剧"),
            ("movie", "电影")
        ]

        classes = []
        for tid, name in tag_list:
            classes.append({
                "type_id": tid,
                "type_name": name
            })

        return {
            "class": classes,
            "filters": {}
        }

    def homeVideoContent(self):
        return {"list": []}

    def _get_target_path(self, tid):
        tag_map = {
            "tag_dongzuo": "/tag/%E5%8A%A8%E4%BD%9C/",
            "tag_juqing": "/tag/%E5%89%A7%E6%83%85/",
            "tag_maoxian": "/tag/%E5%86%92%E9%99%A9/",
            "tag_xiju": "/tag/%E5%96%9C%E5%89%A7/",
            "tag_guocanju": "/tag/%E5%9B%BD%E4%BA%A7%E5%89%A7/",
            "tag_kongbu": "/tag/%E6%81%90%E6%80%96/",
            "tag_zhanzheng": "/tag/%E6%88%98%E4%BA%89/",
            "tag_kehuan": "/tag/%E7%A7%91%E5%B9%BB/",
            "tag_donghua": "/tag/%E5%8A%A8%E7%94%BB/",
            "tag_hanju": "/tag/%E9%9F%A9%E5%89%A7/",
            "tag_fanzui": "/tag/%E7%8A%AF%E7%BD%AA/",
            "tag_jilupian": "/tag/%E7%BA%AA%E5%BD%95%E7%89%87/",
            "tv": "/tv/",
            "movie": "/movie/"
        }
        return tag_map.get(tid, "/tv/")

    def categoryContent(self, tid, pg, filter, extend):
        p = int(pg)
        base_path = self._get_target_path(tid)

        if p <= 1:
            url = "%s%s" % (self.site_url, base_path)
        else:
            clean_base = base_path.rstrip("/")
            url = "%s%s/page-%s.html" % (self.site_url, clean_base, p)

        try:
            code, final_url, headers, html = self._fetch(url)
        except Exception:
            return {"list": [], "page": p, "pagecount": p, "limit": 20, "total": 0}

        recomm_idx = html.find('id="recomm"')
        scope = html[recomm_idx:] if recomm_idx != -1 else html

        card_dict = {}
        ordered_hrefs = []

        link_blocks = re.findall(r'(<a[^>]*href=["\']((?:/tv/|/movie/)[^"\']+)["\'][^>]*>(.*?)</a>)', scope, re.S | re.I)

        for full_tag, href, inner in link_blocks:
            if href in ["/tv/", "/movie/", "/av/"] or re.search(r'page-\d+\.html', href):
                continue

            if href not in card_dict:
                card_dict[href] = {
                    "vod_id": href,
                    "vod_name": "",
                    "vod_pic": "",
                    "vod_remarks": "ZakaTV"
                }
                ordered_hrefs.append(href)

            pic = self._extract_image(inner, href)
            if pic and not card_dict[href]["vod_pic"]:
                card_dict[href]["vod_pic"] = pic

            title_match = re.search(r'<img[^>]*alt=["\']([^"\']+)["\']', inner)
            if not title_match:
                title_match = re.search(r'title=["\']([^"\']+)["\']', full_tag)

            if title_match and not card_dict[href]["vod_name"]:
                candidate_name = self._clean_text(title_match.group(1))
                candidate_name = re.sub(r'\s*(?:电影海报|电视剧海报|海报)$', '', candidate_name).strip()
                if candidate_name:
                    card_dict[href]["vod_name"] = candidate_name

            h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', inner, re.S | re.I)
            if h2_match and not card_dict[href]["vod_name"]:
                card_dict[href]["vod_name"] = self._clean_text(h2_match.group(1))

        items = []
        for href in ordered_hrefs:
            item = card_dict[href]
            if not item["vod_name"]:
                slug = href.strip("/").split("/")[-1]
                slug_parts = slug.split("-", 1)
                item["vod_name"] = slug_parts[1] if len(slug_parts) > 1 else slug

            if not item["vod_pic"]:
                item["vod_pic"] = "%s%s/poster_nail.jpg" % (self.site_url, href.rstrip("/"))

            items.append(item)

        has_next = ("page-%s.html" % (p + 1)) in html
        pagecount = (p + 1) if has_next else p

        return {
            "list": items,
            "page": p,
            "pagecount": pagecount,
            "limit": len(items),
            "total": 9999
        }

    def detailContent(self, ids):
        vod_id = ids[0]
        url = self.site_url + vod_id if vod_id.startswith("/") else vod_id

        try:
            code, final_url, headers, html = self._fetch(url)
        except Exception:
            return {"list": []}

        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
        vod_name = self._clean_text(h1_match.group(1)) if h1_match else ""

        img_match = re.search(r'<div[^>]*id=["\'](?:poster|cover|pic)["\'][^>]*>(.*?)</div>', html, re.S | re.I)
        vod_pic = self._extract_image(img_match.group(1) if img_match else html[:3000], vod_id)
        if not vod_pic:
            vod_pic = "%s%s/poster_nail.jpg" % (self.site_url, vod_id.rstrip("/"))

        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
        vod_content = desc_match.group(1).strip() if desc_match else ""

        prefix_notice = "📺ZakaTV提醒：本频道完全免费，交流群：https://t.me/+3t5XRPPo9mlkZDRl\n"
        vod_content = prefix_notice + (vod_content if vod_content else "暂无剧情介绍")

        current_slug = vod_id.strip("/").split("/")[-1]
        base_series = re.sub(r'-(?:s\d+)?(?:e\d+|ep\d+).*$', '', current_slug, flags=re.I)

        episodes = []
        episode_blocks = re.findall(r'<a[^>]*href=["\']((?:/tv/|/movie/)[^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I)

        for ep_href, ep_name in episode_blocks:
            clean_name = self._clean_text(ep_name).replace("▶", "").strip()
            is_valid_ep_title = bool(re.search(r'^(?:S\d+)?E\d+|第\s*\d+\s*集|\d+$', clean_name, re.I))
            is_pure_series_match = bool(base_series and base_series in ep_href)

            if is_pure_series_match and is_valid_ep_title:
                ep_item = "%s$%s" % (clean_name, ep_href)
                if ep_item not in episodes:
                    episodes.append(ep_item)

        has_current_url = any(vod_id in ep for ep in episodes)
        if not has_current_url:
            current_ep_label = "第1集"
            ep_match = re.search(r'(?:s(\d+))?e(?:p)?(\d+)', current_slug, re.I)
            if ep_match:
                s_num = ep_match.group(1)
                e_num = int(ep_match.group(2))
                if s_num:
                    current_ep_label = "S%02dE%02d" % (int(s_num), e_num)
                else:
                    current_ep_label = "EP%02d" % e_num
            episodes.insert(0, "%s$%s" % (current_ep_label, vod_id))

        if not episodes:
            episodes.append("正片$%s" % vod_id)

        play_url = "#".join(episodes)

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "type_name": "超清4K",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": vod_content,
            "vod_play_from": "4K直连",
            "vod_play_url": play_url
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = self.site_url + id if id.startswith("/") else id
        play_url = ""

        try:
            code, final_url, headers, html = self._fetch(url)
            source_match = re.search(r'<source[^>]*src=["\']([^"\']+\.m3u8)["\']', html, re.I)
            if source_match:
                play_url = source_match.group(1).strip()
            else:
                m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8)["\']', html, re.I)
                if m3u8_match:
                    play_url = m3u8_match.group(1).strip()
        except Exception:
            pass

        if play_url.startswith("/"):
            play_url = self.site_url + play_url

        play_headers = {
            "User-Agent": self.header["User-Agent"],
            "Referer": url
        }

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": play_headers
        }

    def searchContent(self, key, quick, pg="1"):
        p = int(pg)
        if p > 1:
            return {"list": []}

        encoded_key = urllib.parse.quote(key)
        url = "%s/s?y=%s" % (self.site_url, encoded_key)

        try:
            code, final_url, headers, html = self._fetch(url)
        except Exception:
            return {"list": []}

        card_dict = {}
        ordered_hrefs = []
        link_blocks = re.findall(r'(<a[^>]*href=["\']((?:/tv/|/movie/)[^"\']+)["\'][^>]*>(.*?)</a>)', html, re.S | re.I)

        for full_tag, href, inner in link_blocks:
            if href in ["/tv/", "/movie/", "/av/"]:
                continue

            if href not in card_dict:
                card_dict[href] = {
                    "vod_id": href,
                    "vod_name": "",
                    "vod_pic": "",
                    "vod_remarks": "ZakaTV"
                }
                ordered_hrefs.append(href)

            pic = self._extract_image(inner, href)
            if pic and not card_dict[href]["vod_pic"]:
                card_dict[href]["vod_pic"] = pic

            title_match = re.search(r'<img[^>]*alt=["\']([^"\']+)["\']', inner)
            if not title_match:
                title_match = re.search(r'title=["\']([^"\']+)["\']', full_tag)

            if title_match and not card_dict[href]["vod_name"]:
                candidate_name = self._clean_text(title_match.group(1))
                candidate_name = re.sub(r'\s*(?:电影海报|电视剧海报|海报)$', '', candidate_name).strip()
                if candidate_name:
                    card_dict[href]["vod_name"] = candidate_name

            h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', inner, re.S | re.I)
            if h2_match and not card_dict[href]["vod_name"]:
                card_dict[href]["vod_name"] = self._clean_text(h2_match.group(1))

        items = []
        for href in ordered_hrefs:
            item = card_dict[href]
            if not item["vod_name"]:
                slug = href.strip("/").split("/")[-1]
                slug_parts = slug.split("-", 1)
                item["vod_name"] = slug_parts[1] if len(slug_parts) > 1 else slug

            if not item["vod_pic"]:
                item["vod_pic"] = "%s%s/poster_nail.jpg" % (self.site_url, href.rstrip("/"))

            items.append(item)

        return {"list": items}

    def action(self, action):
        return None

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return None

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass