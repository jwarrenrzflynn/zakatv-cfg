# coding=utf-8
"""
香蕉视频（H5 壳 / 渠道 bf111）· TVBox Python 插件 · 纯标准库
=====================================================================================
挂法：{"name":"🍌香蕉视频H5┃免登入","type":3,"api":"py_香蕉视频H5.py"}
      extend 可传 {"host":"换域名","cid":"1","agent":"bf111"}

【站情 · 实地逆向，全部实测】
  推广链路：eij41tt5yn.kbwvnu.cn/1790428886/xiangjiao1.html?channelCode=bf111
    → 302 到 azssyyx515.eh9jx.cn/ytsp_b.html（「香蕉视频」App 推广壳）
    → 壳真身在 /xiangjiao1/op.js：Dean Edwards packer（进制 36）
      + javascript-obfuscator 自定义 base64 表（小写字母表在前）—— 两层都拆开了，还原出
        apkUrl = https://mhfkxmlo-….cn-wulanchabu.fcapp.run/vmvrsylz/p8Y2S.html（直出 APK 9.5MB）
        iosUrl = itms-services://…xjsp_51_20260924193431.plist（直出 IPA 58MB）
        appKey = o3u1xcid
    → 安卓包装了加固（classes.dex 无明文域名）；改切 iOS ipa（未加固）：
      Info.plist CFBundleExecutable=FWomsjqC，ChannelConfig.plist cid=26 / display_name=香蕉 /
      URL Scheme=o3u1xcid（与 op.js 的 appKey 对上）；strings 主二进制直接躺着
      https://videoh5.86027a.xyz/api
    → 该 H5 是 uni-app 打包的 Vue（标题「小视频」），axios baseURL = 同源 + /api
    → 全部接口在 https://videoh5.86027a.xyz/api/... 上裸奔，游客注册即出数据

【接口（全部实测）】
  POST /api/user/dunGustRegister {source,dun_token,agent,pid,machine_code,…} -> data.token
  POST /api/user/getVideoUrl     {}                            -> data.video_url（封面+播放同域前缀）
  POST /api/video/category       {}                            -> [{id,name}] 20 个分类（GET 回 405）
  POST /api/video/v2/home        {page,page_size}              -> [{id,n,ch:[…]}] 首页分栏
  POST /api/video/v2/list        {page,page_size,category_id}  -> {l:[…]}
  POST /api/video/v2/list        {page,page_size,keyword}      搜索
  POST /api/video/v2/detail      {id}                          -> pu=play_url / c=cover / t / tl

  ★ 必带请求头 cid（整数商户号，默认 1）。不带/带 0 → 「该渠道已暂停运营」；
    带不存在的商户号（本壳 plist 写的 26）→ 「非法请求，商户不存在」。实测 1 与 100 有效。
  ★ POST 必须 application/x-www-form-urlencoded。发 JSON 会静默拿不到参数。
  ★ 实测 agent(=channelCode bf111) 不影响内容，只有 cid 影响片库切片。

【字段缩写表（H5 里那张映射，别按长名去取，取不到）】
  c=cover  tm=time(秒)  t=title  n=name  m=money  iv=is_vip  ib=is_buy  a=actress
  tl=tag_list  ch=children  ob=orderby  pu=play_url  ic=is_collect  cid=category_id
  rwn=remaining_watch_num  fwt=free_watch_time  vl=vip_level  vwt=video_watch_type

【播放 / 封面】
  最终地址 = video_url + play_url
  例： https://xas92c.xn--tlqu4rt97b3jfmwiqta.com/20260412/4TAS8BmX/index.m3u8
  ★ 封面也在这台视频 CDN 上：video_url + c（实测直出 JPEG，magic ffd8ffe0）；
    image.86027a.xyz 上没有这些图（那里只放 /public/… 的头像与图标）。
  ★ 该 CDN 出口对国内放行，机房/海外出口时通时不通（实测同一条链重试第 3 次才通）——
    不是源的问题。
"""
import gzip
import io
import json
import random
import threading
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

DEFAULT_HOST = 'https://videoh5.86027a.xyz'
IMG_HOST = 'https://image.86027a.xyz'
DEFAULT_UA = ('Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
SITE_NAME = '香蕉视频'
DEFAULT_CID = '1'
DEFAULT_AGENT = 'bf111'
PAGE_LIMIT = 20
TOKEN_TTL = 6 * 3600          # 游客 token 复用 6 小时
VHOST_TTL = 3600              # 播放/封面前缀域名缓存 1 小时


class Spider(_Spider):

    def __init__(self):
        self.host = DEFAULT_HOST
        self.label = SITE_NAME
        self.cid = DEFAULT_CID
        self.agent = DEFAULT_AGENT
        self._token = ''
        self._token_ts = 0.0
        self._vhost = ''
        self._vhost_ts = 0.0
        self._pu = {}            # vod_id -> play_url 路径
        # ★ 必须用可重入锁：_video_host 持锁后会再调 _post -> _ensure_token 抢同一把锁，
        #   普通 Lock 就是自锁（实测 detail 挂死 120s+ 不动）
        self._lock = threading.RLock()

    # ------------------------------------------------------------ 基建

    def init(self, extend=''):
        try:
            e = (extend or '').strip() if isinstance(extend, str) else ''
            if e.startswith('{'):
                o = json.loads(e)
                h = str(o.get('host') or o.get('site') or '').strip()
                if len(h) > 6:
                    if not h.startswith('http'):
                        h = 'https://' + h
                    self.host = h.rstrip('/')
                n = str(o.get('name') or '').strip()
                if n:
                    self.label = n
                c = str(o.get('cid') or '').strip()
                if c:
                    self.cid = c
                if 'agent' in o or 'channelCode' in o:
                    self.agent = str(o.get('agent') or o.get('channelCode') or '')
            elif e.startswith('http'):
                self.host = e.rstrip('/')
        except Exception:
            pass
        return self

    def getName(self):
        return self.label

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def manualVideoCheck(self):
        return False

    def _log(self, msg):
        try:
            print('[' + SITE_NAME + '] ' + str(msg)[:200])
        except Exception:
            pass

    @staticmethod
    def _machine_code():
        return ''.join(random.choice('0123456789abcdef') for _ in range(32))

    def _open(self, url, data=None, headers=None, timeout=15):
        req = urllib.request.Request(url, data=data, headers=headers or {},
                                     method='POST' if data is not None else 'GET')
        try:
            req.add_header('Accept-Encoding', 'gzip')
        except Exception:
            pass
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = (r.headers.get('Content-Encoding') or '').lower()
        if 'gzip' in enc:
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except Exception:
                pass
        return raw.decode('utf-8', 'replace')

    def _base_headers(self, with_token=True):
        h = {
            # ★ 上游只吃 form-urlencoded，发 JSON 会被当空参数
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/plain, */*',
            'cid': self.cid,
            'timestamp': str(int(time.time())),
            'Accept-Language': 'tw',
            'User-Agent': DEFAULT_UA,
            'Origin': self.host,
            'Referer': self.host + '/',
        }
        if with_token and self._token:
            h['token'] = self._token
        return h

    @staticmethod
    def _qs(obj):
        return urllib.parse.urlencode(obj or {}, doseq=True)

    def _ensure_token(self):
        with self._lock:
            if self._token and time.time() - self._token_ts < TOKEN_TTL:
                return self._token
            try:
                body = self._qs({
                    'source': 'h5',
                    'dun_token': '',
                    'agent': self.agent,
                    'pid': '',
                    'machine_code': self._machine_code(),
                    'mobile_name': 'iPhone',
                    'mobile_version': '17.0',
                    'app_version': '1.0',
                }).encode('utf-8')
                txt = self._open(self.host + '/api/user/dunGustRegister', body,
                                 self._base_headers(with_token=False))
                d = (json.loads(txt) or {}).get('data') or {}
                tk = str(d.get('token') or '') if isinstance(d, dict) else ''
                if len(tk) > 8:
                    self._token = tk
                    self._token_ts = time.time()
                else:
                    self._log('register miss: %s' % txt[:120])
            except Exception as ex:
                self._log('register err: %s' % str(ex)[:120])
            return self._token

    def _post(self, path, obj=None):
        if not self._ensure_token():
            return {}
        try:
            body = self._qs(obj or {}).encode('utf-8')
            txt = self._open(self.host + '/api/' + path, body, self._base_headers())
            return json.loads(txt) or {}
        except Exception as ex:
            self._log('post %s: %s' % (path, str(ex)[:120]))
            return {}

    def _video_host(self):
        with self._lock:
            if self._vhost and time.time() - self._vhost_ts < VHOST_TTL:
                return self._vhost
            j = self._post('user/getVideoUrl', {})
            v = str((j.get('data') or {}).get('video_url') or '').strip()
            if len(v) > 8:
                self._vhost = v.rstrip('/')
                self._vhost_ts = time.time()
            return self._vhost

    # ------------------------------------------------------------ 解析

    @staticmethod
    def _rows(j, key=None):
        """data 可能是数组，也可能是 {l:[...]} / {list:[...]} 包一层"""
        d = (j or {}).get('data')
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            if key and isinstance(d.get(key), list):
                return d[key]
            for k in ('l', 'list', 'ch'):
                if isinstance(d.get(k), list):
                    return d[k]
        return []

    def _cover(self, c):
        """封面在视频 CDN 上（video_url + c），拿不到再退回图床"""
        c = str(c or '').strip()
        if not c:
            return ''
        if c.startswith('http'):
            return c
        p = c if c.startswith('/') else '/' + c
        vh = self._video_host()
        return (vh + p) if len(vh) > 8 else (IMG_HOST + p)

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
        d = self._dur(it.get('tm'))
        if d:
            rem.append(d)
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
            'vod_pic': self._cover(it.get('c') or it.get('cover')),
            'vod_remarks': ' · '.join(rem),
        }

    def _cards(self, arr):
        out = []
        for it in (arr or []):
            c = self._card(it)
            if c and c['vod_name']:
                out.append(c)
        return out

    def _player(self, url):
        return {
            'parse': 0,
            'jx': 0,
            'url': url,
            'header': json.dumps({'User-Agent': DEFAULT_UA, 'Referer': self.host + '/'}),
            'format': 'application/x-mpegURL',
            'contentType': 'application/x-mpegURL',
        }

    # ------------------------------------------------------------ 接口

    def homeContent(self, filter=False):
        cls = []
        j = self._post('video/category', {})   # ★ 实测是 POST，GET 回 405
        for c in self._rows(j):
            if not isinstance(c, dict):
                continue
            cid = str(c.get('id') or '').strip()
            name = str(c.get('name') or '').strip()
            if cid and name:
                cls.append({'type_name': name, 'type_id': cid})

        lst = []
        try:
            j2 = self._post('video/v2/home', {'page': 1, 'page_size': 6})
            for blk in self._rows(j2):
                if isinstance(blk, dict):
                    lst.extend(self._cards(blk.get('ch')))
        except Exception as ex:
            self._log('home: %s' % str(ex)[:120])

        if not lst and cls:
            try:
                j3 = self._post('video/v2/list',
                                {'page': 1, 'page_size': 30, 'category_id': cls[0]['type_id']})
                lst = self._cards(self._rows(j3, 'l'))
            except Exception:
                pass

        return {'class': cls, 'list': lst}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        j = self._post('video/v2/list',
                       {'page': page, 'page_size': PAGE_LIMIT, 'category_id': tid})
        lst = self._cards(self._rows(j, 'l'))
        return {
            'page': page,
            'pagecount': page if len(lst) < PAGE_LIMIT else 9999,
            'limit': PAGE_LIMIT,
            'total': 999999,
            'list': lst,
        }

    def detailContent(self, ids):
        vid = str((ids or [''])[0])
        j = self._post('video/v2/detail', {'id': vid})
        d = (j or {}).get('data')
        if not isinstance(d, dict):
            d = {}
        name = str(d.get('t') or d.get('title') or vid).strip()
        pic = self._cover(d.get('c'))
        pu = str(d.get('pu') or d.get('play_url') or '').strip()
        tl = str(d.get('tl') or d.get('tag_list') or '').strip()
        tm = self._dur(d.get('tm'))
        if pu:
            self._pu[vid] = pu
        url = (self._video_host() + pu) if pu else ''

        v = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'type_name': tl,
            'vod_remarks': tm or ('VIP' if int(d.get('iv') or 0) == 1
                                  else ('付费' if int(d.get('ib') or 0) == 1 else '')),
            'vod_content': name + (('\n分类：' + tl) if tl else ''),
            'vod_play_from': SITE_NAME,
            'vod_play_url': (name.replace('$', ' ') + '$' + url) if url else '暂无可播地址$',
        }
        return {'list': [v]}

    def searchContent(self, key, quick=False, pg='1'):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        j = self._post('video/v2/list',
                       {'page': page, 'page_size': PAGE_LIMIT, 'keyword': key})
        return {'list': self._cards(self._rows(j, 'l'))}

    def playerContent(self, flag, id, vipFlags=None):
        vid = str(id or '')
        if vid.startswith('http'):
            return self._player(vid)
        pu = self._pu.get(vid, '')
        if not pu:
            j = self._post('video/v2/detail', {'id': vid})
            d = (j or {}).get('data')
            if isinstance(d, dict):
                pu = str(d.get('pu') or d.get('play_url') or '').strip()
                if pu:
                    self._pu[vid] = pu
        return self._player((self._video_host() + pu) if pu else '')

    def localProxy(self, param):
        return None
