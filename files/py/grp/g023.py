# -*- coding: utf-8 -*-
"""
土豆视频（5866视频 / videoh5.86027a.xyz）· TVBox / 影视仓 / OK影视 / PickTV 四壳通用 Python 源
=================================================================================================
纯标准库（urllib），零第三方依赖 —— 四壳环境可直接跑。

挂法（type 3）：
    {"name":"🔞土豆视频┃原生","type":3,"api":"土豆-TVBox插件.py"}
extend 可选：{"host":"https://videoh5.xxxx.xyz","cid":"1","agent":""}
    host  = 换域名门牌（代码不用动）
    cid   = 商户号，实测 1 / 100 是两个不同片库切片（默认 1）
    agent = 渠道号，实测不影响片库内容（留空即可）

【站情 · 实地逆向，非推测】
  推广落地页 → 安卓包是 VM 壳（dex 只有 3 个类，真身以满熵塞在中段、由 native 运行时解密）
  静态扒不动 → 改切未加固的 iOS ipa，字符串表直接躺着 /api/... 与 H5 主机
  → H5 是 uni-app 打包的 Vue，axios baseURL = 同源 + /api，全部接口在明面上裸奔
  → 游客注册即出数据：不用手机号、不用付费、不用登录

【接口（全部实测）】
  POST /api/user/dunGustRegister  {"machine_code":"<32位hex>"}      -> data.token
  POST /api/user/getVideoUrl      {}                                -> data.video_url（封面+播放同域前缀）
  POST /api/video/category        {}                                -> [{id,name}] 20 个分类（GET 回 405）
  POST /api/video/v2/home         {"page":1,"page_size":N}          -> [{id,n,ch:[…]}] 分栏
  POST /api/video/v2/list         {"page":1,"page_size":20,"category_id":X}
  POST /api/video/v2/list         {"page":1,"page_size":20,"keyword":"X"}   搜索
  POST /api/video/v2/detail       {"id":X}                          -> pu=play_url / c=封面路径

  请求头：token / cid / timestamp(秒) / Accept-Language: tw / Origin + Referer: <host>/
  ★ cid 头必须带：不带或给 0 → 上游回「该渠道已暂停运营」；给不存在的商户号 → 「商户不存在」。

【字段缩写表（H5 里就是这套缩写，别按长名取，取不到）】
  c=封面路径  tm=时长(秒)  t=标题  n=名称  m=money  iv=is_vip  ib=is_buy  a=演员
  tl=标签表  ch=children  ob=orderby  pu=play_url  ic=is_collect  cid=category_id
  rwn=remaining_watch_num  fwt=free_watch_time  vl=vip_level  vwt=video_watch_type

【封面（★2026-09-26 修）】
  封面 = 播放前缀域名 + c，与 m3u8 同域；上游把图伪装成 .js，
  实测头 4 字节 ff d8 ff db（JPEG）/ 89 50 4e 47（PNG），Content-Type 却写着 application/javascript。
  ✗ 旧版把封面拼到 image.86027a.xyz → 该域上这些路径实测 404，列表整片空图。
  ✗ 只有站点自带图标（configs.agent_*_icon）才挂在 image 域名下，条目封面不在那儿。

【播放】
  最终地址 = getVideoUrl 下发的前缀 + pu，例：
    https://xas92c.<xn--域名>/20250815/HDt84dPq/index.m3u8
  带 Referer 回 H5 站。
  ⚠️ 该 CDN 只对国内出口友好，机房/海外出口握手时通时不通（同一条链重试才通），
     所以封面与播放的「真机能不能出画面」请在手机上过一遍；接口与拼装全部实测。
"""
import gzip
import json
import random
import threading
import time
import urllib.parse
import urllib.request

DEFAULT_HOST = 'https://videoh5.86027a.xyz'
DEFAULT_CID = '1'
DEFAULT_AGENT = ''
MOBILE_UA = ('Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
SITE_NAME = '土豆'
PAGE_LIMIT = 20
TOKEN_TTL = 6 * 3600          # 游客 token 复用 6 小时
VHOST_TTL = 3600              # 播放/封面前缀域名缓存 1 小时
HTTP_TIMEOUT = 25


class Spider:
    """土豆视频 —— 四壳通用 Spider（独立类，不继承 base.spider）"""

    def __init__(self):
        self.host = DEFAULT_HOST
        self.cid = DEFAULT_CID
        self.agent = DEFAULT_AGENT
        self.label = SITE_NAME
        self._lock = threading.RLock()
        self._token = ''
        self._token_ts = 0.0
        self._vhost = ''
        self._vhost_ts = 0.0
        self._pu = {}          # vod_id -> play_url（详情拿过就存，点播不用再查一次）

    # ============================================================ 四壳契约

    def getDependence(self):
        return []

    def init(self, extend=''):
        # extend 可能是空串 / URL / JSON 字符串 / dict
        if isinstance(extend, str):
            e = extend.strip()
            if e.startswith('{'):
                try:
                    extend = json.loads(e)
                except Exception:
                    extend = {}
            else:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}
        host = str(extend.get('host') or '').strip()
        if host.startswith('http'):
            self.host = host.rstrip('/')
        cid = str(extend.get('cid') or '').strip()
        if cid:
            self.cid = cid
        agent = str(extend.get('agent') or '').strip()
        if agent:
            self.agent = agent
        return None

    def getName(self):
        return self.label

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return '.m3u8' in u or '.mp4' in u or '.flv' in u

    def manualVideoCheck(self):
        return False

    def action(self, action=''):
        return {}

    def destroy(self):
        return None

    # ============================================================ 底层请求

    @staticmethod
    def _machine_code():
        return ''.join(random.choice('0123456789abcdef') for _ in range(32))

    def _open_raw(self, url, headers=None, data=None, timeout=HTTP_TIMEOUT):
        """返回 (bytes, content_type)；失败返回 (b'', '')"""
        req = urllib.request.Request(url, data=data, headers=headers or {},
                                     method='POST' if data is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                return raw, (resp.headers.get('Content-Type') or '')
        except Exception:
            return b'', ''

    def _open(self, url, headers=None, data=None, timeout=HTTP_TIMEOUT):
        raw, _ = self._open_raw(url, headers, data, timeout)
        return raw.decode('utf-8', 'replace') if raw else ''

    def _headers(self, with_token=True):
        h = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'tw',
            'User-Agent': MOBILE_UA,
            'cid': self.cid,                       # ★ 必须带，不带直接「渠道暂停运营」
            'timestamp': str(int(time.time())),
            'Origin': self.host,
            'Referer': self.host + '/',
        }
        if with_token and self._token:
            h['token'] = self._token
        return h

    @staticmethod
    def _json(txt):
        try:
            return json.loads(txt) if txt else {}
        except Exception:
            return {}

    def _ensure_token(self):
        with self._lock:
            if self._token and time.time() - self._token_ts < TOKEN_TTL:
                return self._token
        body = {'machine_code': self._machine_code()}
        if self.agent:
            body['agent'] = self.agent
        txt = self._open(self.host + '/api/user/dunGustRegister',
                         self._headers(with_token=False),
                         json.dumps(body).encode('utf-8'))
        d = (self._json(txt) or {}).get('data') or {}
        tk = str(d.get('token') or '') if isinstance(d, dict) else ''
        if len(tk) > 8:
            with self._lock:
                self._token = tk
                self._token_ts = time.time()
        return self._token

    def _post(self, path, obj=None):
        if not self._ensure_token():
            return {}
        txt = self._open(self.host + '/api/' + path, self._headers(),
                         json.dumps(obj or {}).encode('utf-8'))
        return self._json(txt)

    def _video_host(self):
        """封面与播放共用的 CDN 前缀（上游按出口下发，缓存 1 小时）。
        ★ 先在锁外做网络请求，再回锁里写 —— 免得持锁再去抢同一把锁搞成自锁。"""
        with self._lock:
            if self._vhost and time.time() - self._vhost_ts < VHOST_TTL:
                return self._vhost
        j = self._post('user/getVideoUrl', {})
        d = (j or {}).get('data') or {}
        v = str(d.get('video_url') or '').strip() if isinstance(d, dict) else ''
        if v:
            with self._lock:
                self._vhost = v.rstrip('/')
                self._vhost_ts = time.time()
        return self._vhost

    # ============================================================ 解析工具

    @staticmethod
    def _rows(j, key=None):
        """data 可能是数组，也可能包一层 {l:[…]} / {list:[…]}"""
        d = (j or {}).get('data')
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            if key and isinstance(d.get(key), list):
                return d.get(key)
            for k in ('l', 'list', 'data'):
                if isinstance(d.get(k), list):
                    return d.get(k)
        return []

    def _img(self, c):
        """封面 = 播放前缀 + c（同域；上游把图伪装成 .js，内容其实是 JPEG/PNG）。
        前缀没拿到就留空 —— 宁缺勿错，不甩一个注定 404 的图床链。"""
        c = str(c or '').strip()
        if not c:
            return ''
        if c.startswith('http'):
            return c
        base = self._video_host()
        if not base:
            return ''
        return base + (c if c.startswith('/') else '/' + c)

    @staticmethod
    def _dur(sec):
        try:
            sec = int(sec)
        except Exception:
            return ''
        if sec <= 0:
            return ''
        return '%02d:%02d' % (sec // 60, sec % 60)

    def _card(self, it):
        if not isinstance(it, dict):
            return None
        vid = str(it.get('id') or '').strip()
        if not vid:
            return None
        rem = []
        dur = self._dur(it.get('tm'))
        if dur:
            rem.append(dur)
        a = str(it.get('a') or it.get('actress') or '').strip()
        if a:
            rem.append(a)
        tl = str(it.get('tl') or it.get('tag_list') or '').strip()
        if tl:
            rem.append(tl)
        if int(it.get('iv') or 0) == 1:
            rem.append('VIP')
        elif int(it.get('ib') or 0) == 1:
            rem.append('付费')
        return {
            'vod_id': vid,
            'vod_name': str(it.get('t') or it.get('title') or '').strip(),
            'vod_pic': self._img(it.get('c') or it.get('cover')),
            'vod_remarks': ' · '.join(rem),
        }

    def _cards(self, arr):
        """列表 + 去重（同一 id 只留一条）"""
        out, seen = [], set()
        for it in (arr or []):
            v = self._card(it)
            if not v or v['vod_id'] in seen:
                continue
            seen.add(v['vod_id'])
            out.append(v)
        return out

    def _player(self, url):
        return {
            'parse': 0,
            'jx': 0,
            'playUrl': '',
            'url': url,
            'header': {
                'User-Agent': MOBILE_UA,
                'Referer': self.host + '/',
            },
            'format': 'application/x-mpegURL',
        }

    # ============================================================ 四壳 13 接口

    def homeContent(self, filter=None):
        cls = []
        j = self._post('video/category', {})        # ★ 实测是 POST，GET 回 405
        for c in self._rows(j):
            if not isinstance(c, dict):
                continue
            tid = str(c.get('id') or '').strip()
            name = str(c.get('name') or '').strip()
            if tid and name:
                cls.append({'type_id': tid, 'type_name': name})

        lst = []
        try:
            j2 = self._post('video/v2/home', {'page': 1, 'page_size': 30})
            rows = []
            for blk in self._rows(j2):
                if isinstance(blk, dict):
                    rows.extend(blk.get('ch') or [])
            lst = self._cards(rows)
        except Exception:
            lst = []

        if not lst and cls:
            try:
                j3 = self._post('video/v2/list', {'page': 1, 'page_size': 30,
                                                  'category_id': cls[0]['type_id']})
                lst = self._cards(self._rows(j3, 'l'))
            except Exception:
                lst = []

        return {'class': cls, 'filters': {}, 'list': lst[:90]}

    def homeVideoContent(self):
        try:
            j = self._post('video/v2/home', {'page': 1, 'page_size': 30})
            rows = []
            for blk in self._rows(j):
                if isinstance(blk, dict):
                    rows.extend(blk.get('ch') or [])
            return {'list': self._cards(rows)}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        tid = str(tid or '').strip()
        body = {'page': page, 'page_size': PAGE_LIMIT}
        try:
            body['category_id'] = int(tid)
        except Exception:
            body['category_id'] = tid
        rows = self._rows(self._post('video/v2/list', body), 'l')
        lst = self._cards(rows)
        return {
            'list': lst,
            'page': page,
            'pagecount': page if len(rows) < PAGE_LIMIT else 9999,
            'limit': PAGE_LIMIT,
            'total': 999999 if len(rows) >= PAGE_LIMIT else len(lst),
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ''
        else:
            vid = str(ids or '')
        vid = vid.strip()
        if not vid:
            return {'list': []}
        body = {'id': int(vid) if vid.isdigit() else vid}
        d = (self._post('video/v2/detail', body) or {}).get('data') or {}
        if not isinstance(d, dict):
            d = {}
        name = str(d.get('t') or d.get('title') or vid).strip()
        pic = self._img(d.get('c') or d.get('cover'))
        pu = str(d.get('pu') or d.get('play_url') or '').strip()
        tag = str(d.get('tl') or d.get('tag_list') or '').strip()
        dur = self._dur(d.get('tm'))
        if pu:
            self._pu[vid] = pu

        host = self._video_host() if pu else ''
        url = (host + pu) if (host and pu) else ''
        safe = name.replace('$', ' ').replace('#', ' ')

        v = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'type_name': tag,
            'vod_remarks': dur or ('VIP' if int(d.get('iv') or 0) == 1 else
                                   ('付费' if int(d.get('ib') or 0) == 1 else '')),
            'vod_content': '【站源】土豆视频（5866视频）· 游客直取，免登入\n'
                           '【分类】' + (tag or '-') + '\n'
                           '【说明】播放地址由站点按出口下发，请求带 Referer 取流',
            'vod_play_from': self.label,
            'vod_play_url': (safe + '$' + url) if url else ('暂无可播地址$'),
        }
        return {'list': [v]}

    def searchContent(self, key, quick=False, pg='1'):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        kw = str(key or '').strip()
        if not kw:
            return {'list': [], 'page': 1, 'pagecount': 1,
                    'limit': PAGE_LIMIT, 'total': 0}
        rows = self._rows(self._post('video/v2/list',
                                     {'page': page, 'page_size': PAGE_LIMIT,
                                      'keyword': kw}), 'l')
        lst = self._cards(rows)
        return {
            'list': lst,
            'page': page,
            'pagecount': page if len(rows) < PAGE_LIMIT else 9999,
            'limit': PAGE_LIMIT,
            'total': 999999 if len(rows) >= PAGE_LIMIT else len(lst),
        }

    def playerContent(self, flag, ids, vipFlags=None):
        if isinstance(ids, (list, tuple)):
            u = str(ids[0]) if ids else ''
        else:
            u = str(ids or '')
        u = u.strip()
        if u.startswith('http'):
            return self._player(u)
        vid = u
        pu = self._pu.get(vid)
        if not pu:
            body = {'id': int(vid) if vid.isdigit() else vid}
            d = (self._post('video/v2/detail', body) or {}).get('data') or {}
            if isinstance(d, dict):
                pu = str(d.get('pu') or d.get('play_url') or '').strip()
                if pu:
                    self._pu[vid] = pu
        if pu:
            host = self._video_host()
            if host:
                return self._player(host + pu)
        return self._player('')

    def localProxy(self, param):
        """四壳要求返回四项 [状态, MIME, body(bytes), header]。
        m3u8 走这里时把相对分片地址补成绝对地址，其余按原字节转发。"""
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        url = str(param.get('url') or '').strip()
        if not url:
            return [404, 'text/plain', b'Not Found', {}]
        raw, _ = self._open_raw(url, self._headers(with_token=False))
        if not raw:
            return [404, 'text/plain', b'Not Found', {}]

        if raw[:7] == b'#EXTM3U':
            base = url.rsplit('/', 1)[0] + '/'
            out = []
            for ln in raw.decode('utf-8', 'replace').splitlines():
                s = ln.strip()
                if s and not s.startswith('#') and not s.startswith('http'):
                    ln = urllib.parse.urljoin(base, s)
                out.append(ln)
            return [200, 'application/vnd.apple.mpegurl',
                    '\n'.join(out).encode('utf-8'),
                    {'Access-Control-Allow-Origin': '*'}]

        mime = 'application/octet-stream'
        if raw[:2] == b'\xff\xd8':
            mime = 'image/jpeg'
        elif raw[:4] == b'\x89PNG':
            mime = 'image/png'
        elif raw[:3] == b'GIF':
            mime = 'image/gif'
        elif len(raw) > 8 and raw[4:8] == b'ftyp':
            mime = 'video/mp4'
        elif raw[:3] == b'ID3':
            mime = 'audio/mpeg'
        return [200, mime, raw, {'Access-Control-Allow-Origin': '*'}]
