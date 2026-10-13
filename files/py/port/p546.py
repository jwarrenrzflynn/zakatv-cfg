import sys
import json
import ssl
import gzip
import zlib
import re
import urllib.request
import urllib.parse
import html

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):
    def __init__(self):
        self.site_url = "https://xn--e6qr77e9twiuh.mzplasmabiotch.ink"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }

    def init(self, extend=""):
        pass

    def _fetch(self, url, headers=None):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                raw = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                final_url = resp.geturl()
                status_code = resp.getcode()
                if "gzip" in encoding:
                    raw = gzip.decompress(raw)
                elif "deflate" in encoding:
                    raw = zlib.decompress(raw)
                text = ""
                for charset in ["utf-8", "gbk", "gb2312", "iso-8859-1"]:
                    try:
                        text = raw.decode(charset)
                        break
                    except Exception:
                        continue
                return status_code, final_url, text
        except Exception as e:
            return 0, url, str(e)

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_id": "42", "type_name": "国产精品"},
            {"type_id": "34", "type_name": "中文字幕"},
            {"type_id": "32", "type_name": "日本女优"},
            {"type_id": "38", "type_name": "欧美视频"},
            {"type_id": "44", "type_name": "明星换脸"},
            {"type_id": "46", "type_name": "萝莉少女"},
            {"type_id": "48", "type_name": "网红主播"},
            {"type_id": "52", "type_name": "传媒拍摄"},
            {"type_id": "54", "type_name": "三级伦理"},
            {"type_id": "56", "type_name": "网暴黑料"},
            {"type_id": "58", "type_name": "激情动漫"},
            {"type_id": "60", "type_name": "全景视角"},
            {"type_id": "62", "type_name": "解说类"},
            {"type_id": "22", "type_name": "女同性爱"},
            {"type_id": "28", "type_name": "人妖视频"},
            {"type_id": "30", "type_name": "捆绑调教"}
        ]
        result["class"] = classes
        result["filters"] = {}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _parse_vod_list(self, html_data):
        cards = []
        if not html_data:
            return cards

        blocks = re.findall(r'<div[^>]*class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>(.*?)</div>\s*</div>\s*</div>', html_data, re.I | re.S)
        if not blocks:
            blocks = re.findall(r'<div[^>]*class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>(.*?)</a>\s*</div>', html_data, re.I | re.S)
        if not blocks:
            blocks = re.findall(r'<div[^>]*class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>(.*?)</div>', html_data, re.I | re.S)

        seen_ids = set()
        for block in blocks:
            v_m = re.search(r'href=["\']([^"\']*/vod/play/id/\d+[^"\']*)["\']', block, re.I)
            if not v_m:
                continue
            clean_href = v_m.group(1).strip()
            if clean_href in seen_ids:
                continue

            title = ""
            t_m = re.search(r'<strong[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>(.*?)</strong>', block, re.I | re.S)
            if t_m:
                title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip()

            if not title:
                t_m2 = re.search(r'<(?:a|div|span|h\d)[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>(.*?)</(?:a|div|span|h\d)>', block, re.I | re.S)
                if t_m2:
                    t_cand = re.sub(r'<[^>]+>', '', t_m2.group(1)).strip()
                    if not re.match(r'^\d{1,2}:\d{2}(?::\d{2})?$', t_cand):
                        title = t_cand

            if not title:
                title_attrs = re.findall(r'title=["\']([^"\']+)["\']', block, re.I)
                for t in title_attrs:
                    t_clean = t.strip()
                    if len(t_clean) > len(title) and not re.match(r'^\d{1,2}:\d{2}(?::\d{2})?$', t_clean):
                        title = t_clean

            if not title:
                continue

            pic = ""
            p_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
            if p_m:
                pic = p_m.group(1).strip()
                if not pic.startswith("http"):
                    pic = urllib.parse.urljoin(self.site_url, pic)

            remarks_raw = ""
            d_m = re.search(r'<div[^>]*class=["\'][^"\']*duration[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
            if d_m:
                remarks_raw = re.sub(r'<[^>]+>', '', d_m.group(1)).strip()

            if remarks_raw:
                remarks = "ZakaTV | %s" % remarks_raw
            else:
                remarks = "ZakaTV"

            seen_ids.add(clean_href)
            cards.append({
                "vod_id": clean_href,
                "vod_name": html.unescape(title),
                "vod_pic": pic,
                "vod_remarks": remarks,
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV",
                "style": {"type": "rect", "ratio": 1.78}
            })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        actual_tid = tid
        pg_int = int(pg) if str(pg).isdigit() else 1

        if pg_int <= 1:
            req_url = "%s/index.php/vod/type/id/%s.html" % (self.site_url, actual_tid)
        else:
            req_url = "%s/index.php/vod/type/id/%s/page/%s.html" % (self.site_url, actual_tid, pg_int)

        code, final_url, html_data = self._fetch(req_url)
        cards = self._parse_vod_list(html_data)

        return {
            "list": cards,
            "page": pg_int,
            "pagecount": pg_int + 1 if len(cards) >= 12 else pg_int,
            "limit": len(cards),
            "total": 9999
        }

    def _extract_play_url(self, html_text):
        url_match = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html_text)
        if url_match:
            return url_match.group(1).replace(r'\/', '/')

        m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
        for m in m3u8_matches:
            if "sample" not in m and "test" not in m:
                return m

        player_match = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', html_text, re.I | re.S)
        if player_match:
            try:
                p_json = json.loads(player_match.group(1))
                if p_json.get("url"):
                    return p_json.get("url")
            except Exception:
                pass

        return ""

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        detail_url = urllib.parse.urljoin(self.site_url, vod_id)
        code, final_url, html_data = self._fetch(detail_url)

        title = ""
        player_name_m = re.search(r'"vod_name"\s*:\s*"([^"]+)"', html_data)
        if player_name_m:
            raw_vname = player_name_m.group(1)
            try:
                title = json.loads('"%s"' % raw_vname).strip()
            except Exception:
                title = raw_vname.strip()

        if not title:
            title_tag_m = re.search(r'<title>(.*?)</title>', html_data, re.I | re.S)
            if title_tag_m:
                t_raw = re.sub(r'<[^>]+>', '', title_tag_m.group(1)).strip()
                t_raw = re.split(r'[-_|]', t_raw)[0].strip()
                if t_raw and len(t_raw) >= 2:
                    title = t_raw

        if not title:
            h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_data, re.I | re.S)
            if h1_m:
                title = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()

        pic = ""
        p_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_data, re.I)
        if p_m:
            pic = p_m.group(1).strip()
        else:
            p_m2 = re.search(r'<img[^>]+class=["\'][^"\']*thumb[^"\']*["\'][^>]*src=["\']([^"\']+)["\']', html_data, re.I)
            if p_m2:
                pic = p_m2.group(1).strip()
        if pic and not pic.startswith("http"):
            pic = urllib.parse.urljoin(self.site_url, pic)

        direct_play_url = self._extract_play_url(html_data)

        play_sources = ["Zaka专线"]
        play_urls = ["正片$" + (direct_play_url if direct_play_url else detail_url)]

        clean_title = html.unescape(title) if title else "ZakaTV"

        vod = {
            "vod_id": vod_id,
            "vod_name": clean_title,
            "vod_pic": pic,
            "type_name": "Zaka精选",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": "📺官方交流群: https://t.me/+3t5XRPPo9mlkZDRl | 请勿相信视频内任何广告！",
            "vod_play_from": "$$$".join(play_sources),
            "vod_play_url": "$$$".join(play_urls)
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_url = id
        if not play_url.endswith(".m3u8") and not play_url.endswith(".mp4"):
            code, final_url, html_data = self._fetch(play_url if play_url.startswith("http") else urllib.parse.urljoin(self.site_url, play_url))
            real_url = self._extract_play_url(html_data)
            if real_url:
                play_url = real_url

        headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/"
        }
        return {
            "parse": 0,
            "url": play_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        pg_int = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(key)
        if pg_int <= 1:
            search_url = "%s/index.php/vod/search/wd/%s.html" % (self.site_url, encoded_key)
        else:
            search_url = "%s/index.php/vod/search/page/%s/wd/%s.html" % (self.site_url, pg_int, encoded_key)

        code, final_url, html_data = self._fetch(search_url)
        cards = self._parse_vod_list(html_data)

        return {
            "list": cards,
            "page": pg_int,
            "pagecount": pg_int + 1 if len(cards) >= 12 else pg_int,
            "limit": len(cards),
            "total": 9999
        }

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def localProxy(self, params):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass