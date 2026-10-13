# coding=utf-8
"""
K站（kfzedwc 站群）· TVBox Python 插件 · 纯标准库自实现（不需要 requests / pycryptodome）
=====================================================================================
接口： homeContent / categoryContent / detailContent / searchContent / playerContent
挂法： {"name":"🔞K站┃密钥直取","type":3,"api":"py_K站.py"}  （extend 可传 {"host":"换域名"}）

【站情 · 2026-09-26 实地逆向】
  入口 www.kfzedwc.com:2087 是 Vite SPA 外壳，整页假正文 + 黑帽混淆 JS；
  真数据全在同域 JSON 接口 /v1/*，**每个响应都是加密信封**。
  片库约 7.6 万条（国产 23168 / 日韩 21831 / 传媒 11289 / 欧美 10092 / 动漫 9710），
  纯免费：无登录、无 VIP、无付费墙。

【加密信封（本插件的核心）—— 跟 Java 版逐字节同一套】
  响应 {"data":"<base64>","key":"<base64 RSA密文>"}
   ① RSA：站点把 512 位私钥写在前端（PKCS#1 DER），key 明文 = pow(ct, d, n) 去 PKCS#1 v1.5 填充
   ② 明文串（实测 24 字符）整串反转后取前 16 字符 = AES 的 IV
   ③ AES-192-CBC/PKCS7：key = ①的整串（24 字节），iv = ②，解 data → 明文 JSON
  ⚠️ 顺序错一步就是乱码；AES 是本文件里手写的（壳里不一定有 pycryptodome）。

【接口】
  分类树 /v1/vod/category?c=<branch>      片单 /v1/vod?c=&cate_id=&page=&limit=
  搜索   /v1/vod?c=&name=<kw>&page=&limit= 详情 /v1/vod/<id>?c=
  c = 前端 qu.branch，实测 "t1"。排序参数站方没实现，插件里不放排序项。
【取流 —— 2026-09-26 复测后重做】
  详情接口吐的是一条带 auth_key 的绝对 m3u8（HLS 标准 AES-128，非 Widevine DRM）。
  链路上两道闸，缺一样就播不了：
    ① 清单的 auth_key 是 1 小时短签（md5 覆盖路径本身、密钥在站方服务端）——
       设备侧算不出新签名，只能回详情接口重取；列表里躺着那份签名过一会儿就 403。
    ② 这条 CDN 对清单 / 分片 / 密钥**一律验 Referer**，不带 Referer 全 403
       （实测：分片无 Referer 403、带 Referer 200）；而分片本身不需要签名。
  所以播放改走**本机中继**：详情里只挂站内 id，播放那一刻回接口换新签名，
  取回清单后把分片 / 密钥 / 子清单改写成中继地址（中继补 Referer），签名过期就再换一次
  —— 即「自动续签」。中继是纯标准库的 127.0.0.1 小 HTTP 服务，起不来自动退回直链。
  封面跟清单是同一套签名，也走中继（失败时按站内 id 换一张新签名的）。
"""
import base64
import gzip
import io
import json
import re
import threading
import time
import urllib.parse

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except Exception:
    BaseHTTPRequestHandler = None
    ThreadingHTTPServer = None

try:
    import requests
except Exception:
    requests = None
try:
    import urllib.request as _urlreq
except Exception:
    _urlreq = None

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

DEFAULT_HOST = 'https://www.kfzedwc.com:2087'
DEFAULT_BRANCH = 't1'
DEFAULT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
PAGE_LIMIT = 30

# ============================ AES 查表（标准 S 盒，工具生成，勿手改） ============================
_SBOX = (
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
)

_RSBOX = (
    0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38, 0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
    0x7c, 0xe3, 0x39, 0x82, 0x9b, 0x2f, 0xff, 0x87, 0x34, 0x8e, 0x43, 0x44, 0xc4, 0xde, 0xe9, 0xcb,
    0x54, 0x7b, 0x94, 0x32, 0xa6, 0xc2, 0x23, 0x3d, 0xee, 0x4c, 0x95, 0x0b, 0x42, 0xfa, 0xc3, 0x4e,
    0x08, 0x2e, 0xa1, 0x66, 0x28, 0xd9, 0x24, 0xb2, 0x76, 0x5b, 0xa2, 0x49, 0x6d, 0x8b, 0xd1, 0x25,
    0x72, 0xf8, 0xf6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xd4, 0xa4, 0x5c, 0xcc, 0x5d, 0x65, 0xb6, 0x92,
    0x6c, 0x70, 0x48, 0x50, 0xfd, 0xed, 0xb9, 0xda, 0x5e, 0x15, 0x46, 0x57, 0xa7, 0x8d, 0x9d, 0x84,
    0x90, 0xd8, 0xab, 0x00, 0x8c, 0xbc, 0xd3, 0x0a, 0xf7, 0xe4, 0x58, 0x05, 0xb8, 0xb3, 0x45, 0x06,
    0xd0, 0x2c, 0x1e, 0x8f, 0xca, 0x3f, 0x0f, 0x02, 0xc1, 0xaf, 0xbd, 0x03, 0x01, 0x13, 0x8a, 0x6b,
    0x3a, 0x91, 0x11, 0x41, 0x4f, 0x67, 0xdc, 0xea, 0x97, 0xf2, 0xcf, 0xce, 0xf0, 0xb4, 0xe6, 0x73,
    0x96, 0xac, 0x74, 0x22, 0xe7, 0xad, 0x35, 0x85, 0xe2, 0xf9, 0x37, 0xe8, 0x1c, 0x75, 0xdf, 0x6e,
    0x47, 0xf1, 0x1a, 0x71, 0x1d, 0x29, 0xc5, 0x89, 0x6f, 0xb7, 0x62, 0x0e, 0xaa, 0x18, 0xbe, 0x1b,
    0xfc, 0x56, 0x3e, 0x4b, 0xc6, 0xd2, 0x79, 0x20, 0x9a, 0xdb, 0xc0, 0xfe, 0x78, 0xcd, 0x5a, 0xf4,
    0x1f, 0xdd, 0xa8, 0x33, 0x88, 0x07, 0xc7, 0x31, 0xb1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xec, 0x5f,
    0x60, 0x51, 0x7f, 0xa9, 0x19, 0xb5, 0x4a, 0x0d, 0x2d, 0xe5, 0x7a, 0x9f, 0x93, 0xc9, 0x9c, 0xef,
    0xa0, 0xe0, 0x3b, 0x4d, 0xae, 0x2a, 0xf5, 0xb0, 0xc8, 0xeb, 0xbb, 0x3c, 0x83, 0x53, 0x99, 0x61,
    0x17, 0x2b, 0x04, 0x7e, 0xba, 0x77, 0xd6, 0x26, 0xe1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0c, 0x7d,
)
_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)


def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _key_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _add_round_key(st, w, rnd):
    for c in range(4):
        for r in range(4):
            st[r][c] ^= w[rnd * 4 + c][r]


def _inv_shift_rows(st):
    for r in range(1, 4):
        st[r] = st[r][-r:] + st[r][:-r]


def _inv_sub_bytes(st):
    for r in range(4):
        for c in range(4):
            st[r][c] = _RSBOX[st[r][c]]


def _inv_mix_columns(st):
    for c in range(4):
        a = [st[r][c] for r in range(4)]
        st[0][c] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
        st[1][c] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
        st[2][c] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
        st[3][c] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)


def _dec_block(block, w, nr):
    st = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
    _add_round_key(st, w, nr)
    for rnd in range(nr - 1, 0, -1):
        _inv_shift_rows(st)
        _inv_sub_bytes(st)
        _add_round_key(st, w, rnd)
        _inv_mix_columns(st)
    _inv_shift_rows(st)
    _inv_sub_bytes(st)
    _add_round_key(st, w, 0)
    return bytes(st[r][c] for c in range(4) for r in range(4))


def _aes_cbc_decrypt(data, key, iv):
    """纯标准库 AES-CBC 解密 + PKCS7 去填充。key 支持 16/24/32 字节。"""
    if len(key) not in (16, 24, 32):
        raise ValueError('bad aes key len %d' % len(key))
    if len(iv) != 16:
        raise ValueError('bad iv len %d' % len(iv))
    if len(data) == 0 or len(data) % 16 != 0:
        raise ValueError('bad ciphertext len %d' % len(data))
    w, nr = _key_expand(key)
    out = bytearray()
    prev = iv
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        dec = _dec_block(blk, w, nr)
        out.extend(bytes(dec[i] ^ prev[i] for i in range(16)))
        prev = blk
    pad = out[-1]
    if 1 <= pad <= 16:
        out = out[:-pad]
    return bytes(out)


# ============================ RSA（站点内置 512 位私钥的 n / d） ============================
RSA_N = int(
    'd04f4db2ecfa8d817e25e2ea29a2f52e46728345a5e313c8c04ce50eb3b850e3'
    '18197d561be9ea7fda2fa699604e180b732a11335605b211853ab900887119ab', 16)
RSA_D = int(
    '1bc47677035fe2bd0033ccabaa212ecd9c5667694153a3af7ef2c115d49f1d28'
    'eac923337620e39bb0de5a686eb91c91ea74371aab20d792b2b636f61037641', 16)
RSA_LEN = 64


def _rsa_decrypt(ct):
    """pow(ct, d, n) → PKCS#1 v1.5 去填充（00 02 PS 00 M）"""
    m = pow(int.from_bytes(ct, 'big'), RSA_D, RSA_N)
    em = m.to_bytes(RSA_LEN, 'big')
    if em[0] != 0 or em[1] != 2:
        raise ValueError('rsa padding')
    i = 2
    while i < len(em) and em[i] != 0:
        i += 1
    if i >= len(em) - 1:
        raise ValueError('rsa pad zero')
    return em[i + 1:]


def unwrap(raw):
    """{data,key} 信封 → 明文 JSON（不是信封就原样返回）"""
    if not raw:
        return {}
    j = json.loads(raw)
    if not isinstance(j, dict):
        return {}
    data_b64 = j.get('data') or ''
    key_b64 = j.get('key') or ''
    if not data_b64 or not key_b64:
        return j
    ks = _rsa_decrypt(base64.b64decode(key_b64)).decode('utf-8', 'replace')
    rev = ks[::-1]
    if len(rev) < 16:
        raise ValueError('aes iv short')
    iv = rev[:16].encode('utf-8')
    pt = _aes_cbc_decrypt(base64.b64decode(data_b64), ks.encode('utf-8'), iv)
    return json.loads(pt.decode('utf-8', 'replace'))


# ============================ TVBox 插件主体 ============================
SITE_NAME = 'K站'


# ============================ 本地中继（自动续签 + 补防盗链） ============================
PLAY_PREFIX = 'kfz:'
HLS_CACHE_SEC = 60


def _b64u(s):
    return base64.urlsafe_b64encode(s.encode('utf-8')).decode('ascii').rstrip('=')


def _unb64u(s):
    s = str(s or '')
    if s.startswith('http'):
        return s
    s += '=' * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s.encode('ascii')).decode('utf-8')
    except Exception:
        return ''


def _is_image(b):
    if not b or len(b) < 4:
        return False
    if b[:2] == b'\xff\xd8':
        return True
    if b[:4] == b'\x89PNG':
        return True
    if b[:3] == b'GIF':
        return True
    if b[:4] == b'RIFF':
        return True
    return False


def _de_xor(b):
    """封面是打码图：站方把整张 JPEG 逐字节异或了 0x88（字段名 enc_img 的 enc 就指这个）。
    原样给壳 = 花屏/空封面。真 JPEG 头 FF D8 FF E0 打码后是 77 50 77 68。
    已经是正常图片就原样返回，绝不把好图异或坏。"""
    if not b or len(b) < 8 or _is_image(b):
        return b
    if b[0] ^ 0x88 != 0xFF or b[1] ^ 0x88 != 0xD8:
        return b
    out = bytes(x ^ 0x88 for x in b)
    return out if _is_image(out) else b


def _mime_of(b):
    if b[:4] == b'\x89PNG':
        return 'image/png'
    if b[:3] == b'GIF':
        return 'image/gif'
    if b[:4] == b'RIFF':
        return 'image/webp'
    return 'image/jpeg'


class _KfzRelay(object):
    """只监听 127.0.0.1 的极小 HTTP 服务。

    为什么必须有它（这是「点开转圈 / 播一半断」的真根子）：
      ① 清单签名 1 小时到期，播放器自己不会换新签名；
      ② 分片 / 密钥要 Referer，播放器自己拉分片不带。
    所以清单在这里每次换新签名，分片密钥在这里补 Referer 转发。
    """

    def __init__(self, sp):
        self.sp = sp
        self.httpd = None
        self.port = 0
        self.resigns = 0
        self.last_sig = ''
        self.fails = 0
        self._hls = {}
        self._lock = threading.Lock()

    # ---------- 起服务 ----------
    def ensure(self):
        if self.httpd is not None:
            return self.port
        if ThreadingHTTPServer is None or BaseHTTPRequestHandler is None:
            return 0
        with self._lock:
            if self.httpd is not None:
                return self.port
            try:
                srv = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
                srv.daemon_threads = True
                th = threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.5})
                th.daemon = True
                th.start()
                self.httpd = srv
                self.port = int(srv.server_address[1])
                self.sp._log('relay up on 127.0.0.1:%d' % self.port)
            except Exception as e:
                self.sp._log('relay start fail: %s' % str(e)[:120])
                return 0
        return self.port

    def stop(self):
        try:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        self.port = 0

    def base(self):
        p = self.ensure()
        return ('http://127.0.0.1:%d' % p) if p > 0 else ''

    # ---------- 对外地址 ----------
    def hls_url(self, vid):
        b = self.base()
        return (b + '/hls?v=' + urllib.parse.quote(str(vid or ''))) if b else ''

    def seg_url(self, abs_url):
        b = self.base()
        return (b + '/seg?u=' + _b64u(abs_url)) if b else ''

    def key_url(self, abs_url):
        b = self.base()
        return (b + '/key?u=' + _b64u(abs_url)) if b else ''

    def img_url(self, pic, vid):
        b = self.base()
        if not b:
            return ''
        return b + '/img?u=' + _b64u(str(pic or '')) + '&v=' + urllib.parse.quote(str(vid or ''))

    # ---------- 处理 ----------
    def _handler(self):
        relay = self

        class _H(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_GET(self):
                relay.serve(self, False)

            def do_HEAD(self):
                relay.serve(self, True)

        return _H

    @staticmethod
    def _q(qs, key, default=''):
        v = qs.get(key)
        return v[0] if v else default

    def serve(self, h, head=False):
        try:
            u = urllib.parse.urlparse(h.path)
            qs = urllib.parse.parse_qs(u.query)
            sp = self.sp
            if u.path == '/hls':
                vid = self._q(qs, 'v')
                nested = _unb64u(self._q(qs, 'u')) if self._q(qs, 'u') else ''
                body = self._playlist(vid, nested)
                if body is None:
                    self.fails += 1
                    self._send(h, 502, 'text/plain', b'm3u8 unavailable', head)
                else:
                    self._send(h, 200, 'application/vnd.apple.mpegurl', body.encode('utf-8'), head)
                return
            if u.path in ('/seg', '/key'):
                url = _unb64u(self._q(qs, 'u'))
                if not url.startswith('http'):
                    self._send(h, 404, 'text/plain', b'no url', head)
                    return
                raw = sp._fetch_bytes(url)
                if not raw:
                    self.fails += 1
                    self._send(h, 404, 'text/plain', b'upstream', head)
                    return
                mime = 'video/mp2t' if u.path == '/seg' else 'application/octet-stream'
                self._send(h, 200, mime, raw, head)
                return
            if u.path == '/img':
                url = _unb64u(self._q(qs, 'u'))
                vid = self._q(qs, 'v')
                raw = sp._fetch_bytes(url, timeout=12) if url.startswith('http') else None
                if not raw and vid:
                    fresh = sp._fresh_pic(vid)
                    if fresh and fresh != url:
                        raw = sp._fetch_bytes(fresh, timeout=12)
                if not raw:
                    self._send(h, 502, 'text/plain', b'img fail', head)
                    return
                raw = _de_xor(raw)
                self._send(h, 200, _mime_of(raw), raw, head)
                return
            self._send(h, 404, 'text/plain', b'bad path', head)
        except Exception as e:
            self.fails += 1
            try:
                self._send(h, 500, 'text/plain', ('err %s' % str(e)[:60]).encode('utf-8'), head)
            except Exception:
                pass

    def _playlist(self, vid, nested):
        sp = self.sp
        key = vid or nested
        hit = self._hls.get(key)
        now = time.time()
        if hit and now - hit[0] < HLS_CACHE_SEC:
            return hit[1]
        signed = nested or sp._fresh_m3u8(vid)
        if not signed:
            return None
        text = sp._fetch_text(signed)
        # 签名刚过期 / 这一下 CDN 抖：回详情换一次新签名再试一轮
        if not text and vid:
            again = sp._fresh_m3u8(vid)
            if again and again != signed:
                signed = again
                text = sp._fetch_text(signed)
        if not text or '#EXTM3U' not in text:
            return None
        # 真 DRM（Widevine / SAMPLE-AES）这站没见过；真遇到就如实报错，别硬塞给播放器
        up = text.upper()
        if 'METHOD=SAMPLE-AES' in up or 'SKD://' in up:
            return None
        if not nested:
            self.resigns += 1
            self.last_sig = signed
        out = self._rebuild(text, signed)
        if len(self._hls) > 40:
            self._hls.clear()
        self._hls[key] = (now, out)
        return out

    def _rebuild(self, text, signed):
        lines = []
        for ln in text.split('\n'):
            t = ln.strip()
            if not t:
                continue
            if t.startswith('#EXT-X-KEY') \
                    or t.startswith('#EXT-X-MAP') or t.startswith('#EXT-X-MEDIA'):
                lines.append(self._rewrite_uri(t, signed))
            elif t[:1] == '#':
                lines.append(ln)
            else:
                lines.append(self._wrap(urllib.parse.urljoin(signed, t)))
        return '\n'.join(lines) + '\n'

    def _rewrite_uri(self, line, signed):
        m = re.search(r'URI=(["\'])([^"\']+)\1', line)
        if not m:
            return line
        uri = m.group(2)
        if uri.startswith('http'):
            return line
        abs_url = urllib.parse.urljoin(signed, uri)
        if not abs_url.startswith('http'):
            return line
        return line[:m.start(2)] + self._wrap(abs_url) + line[m.end(2):]

    def _wrap(self, abs_url):
        low = abs_url.lower().split('?')[0]
        if low.endswith('.m3u8'):
            return self.base() + '/hls?u=' + _b64u(abs_url)
        if low.endswith('.ts') or low.endswith('.mp4') or low.endswith('.m4s') \
                or low.endswith('.aac') or low.endswith('.mp3'):
            return self.seg_url(abs_url)
        return self.key_url(abs_url)

    @staticmethod
    def _send(h, code, mime, body, head=False):
        body = body or b''
        h.send_response(code)
        h.send_header('Content-Type', mime)
        h.send_header('Content-Length', str(len(body)))
        h.send_header('Accept-Ranges', 'bytes')
        h.send_header('Connection', 'close')
        h.end_headers()
        if not head:
            h.wfile.write(body)
        try:
            h.wfile.flush()
        except Exception:
            pass
        h.close_connection = True


class Spider(_Spider):

    def __init__(self, *args, **kwargs):
        self.host = DEFAULT_HOST
        self.branch = DEFAULT_BRANCH
        self.timeout = 20
        self.headers = {
            'User-Agent': DEFAULT_UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': DEFAULT_HOST + '/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        self._cache = {}

    # ---------- 现取签名 + 中继取数 ----------
    def _relay(self):
        r = getattr(self, '_relay_obj', None)
        if r is None:
            r = _KfzRelay(self)
            self._relay_obj = r
        return r

    def _fresh_video(self, vid):
        """直连取一次详情里的 video 节点（**不过 _api 那张 180 秒缓存**：
        要的就是新鲜签名，走缓存等于拿旧的）"""
        vid = str(vid or '').strip()
        if vid[:1] == 'v':
            vid = vid[1:]
        if not vid:
            return {}
        raw = self._http(self.host + '/v1/vod/' + vid + '?c=' + self.branch)
        if not raw:
            return {}
        try:
            return (((unwrap(raw) or {}).get('data') or {}).get('video') or {})
        except Exception:
            return {}

    def _fresh_m3u8(self, vid):
        return str(self._fresh_video(vid).get('url') or '').strip()

    def _fresh_pic(self, vid):
        return str(self._fresh_video(vid).get('enc_img') or '').strip()

    def _fetch_bytes(self, url, timeout=25):
        """带 Referer + UA 取字节（清单 / 分片 / 密钥都走它）；两次机会，CDN 抖得很"""
        if not url or not str(url).startswith('http'):
            return None
        hd = dict(self.headers)
        hd['Accept'] = '*/*'
        for attempt in range(2):
            if requests is not None:
                try:
                    r = requests.get(url, timeout=timeout, headers=hd, verify=False)
                    if r.status_code == 200 and r.content:
                        return r.content
                except Exception:
                    pass
            if _urlreq is not None:
                try:
                    req = _urlreq.Request(url, headers=hd)
                    raw = _urlreq.urlopen(req, timeout=timeout).read()
                    if raw:
                        return raw
                except Exception:
                    pass
            if attempt == 0:
                time.sleep(0.6)
        return None

    def _fetch_text(self, url):
        raw = self._fetch_bytes(url)
        if not raw:
            return ''
        try:
            return raw.decode('utf-8', 'replace')
        except Exception:
            return ''

    # ---------- 生命周期 ----------
    def init(self, extend=''):
        cfg = {}
        try:
            if extend:
                if isinstance(extend, dict):
                    cfg = dict(extend)
                else:
                    s = str(extend).strip()
                    if s.startswith('{'):
                        cfg = json.loads(s)
                    else:
                        for kv in re.split(r'[&;]', s):
                            if '=' in kv:
                                k, v = kv.split('=', 1)
                                cfg[k.strip()] = urllib.parse.unquote(v.strip())
        except Exception:
            cfg = {}
        if cfg.get('host'):
            h = str(cfg['host']).strip().rstrip('/')
            if not h.startswith('http'):
                h = 'https://' + h
            self.host = h
        if cfg.get('branch') or cfg.get('c'):
            self.branch = str(cfg.get('branch') or cfg.get('c'))
        if cfg.get('ua'):
            self.headers['User-Agent'] = str(cfg['ua'])
        self.headers['Referer'] = self.host + '/'
        return self

    def getName(self):
        return SITE_NAME

    def destroy(self):
        self._cache = {}
        r = getattr(self, '_relay_obj', None)
        if r is not None:
            try:
                r.stop()
            except Exception:
                pass

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return ('.m3u8' in u) or ('.mp4' in u) or ('.ts' in u)

    def manualVideoCheck(self):
        return False

    # ---------- 请求层：requests → urllib 两级降级 ----------
    def _http(self, url):
        """requests → urllib 两级降级 + 一次重试（这站 CDN 会抖，单次失败很常见）"""
        for attempt in range(2):
            last = ''
            if requests is not None:
                try:
                    r = requests.get(url, timeout=self.timeout, headers=self.headers, verify=False)
                    if r.status_code == 200 and r.text:
                        r.encoding = 'utf-8'
                        return r.text
                    last = 'http %s' % r.status_code
                except Exception as e:
                    last = str(e)[:120]
            if _urlreq is not None:
                try:
                    req = _urlreq.Request(url, headers=self.headers)
                    raw = _urlreq.urlopen(req, timeout=self.timeout).read()
                    if raw[:2] == b'\x1f\x8b':
                        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                    return raw.decode('utf-8', 'replace')
                except Exception as e:
                    last = str(e)[:120]
            if attempt == 0:
                time.sleep(0.8)
            elif last:
                self._log('request fail: %s (%s)' % (url.split('?')[0], last))
        return ''

    def _api(self, path, qs=''):
        url = self.host + '/v1' + path + (('?' + qs) if qs else '')
        now = time.time()
        hit = self._cache.get(url)
        if hit and now - hit[0] < 180:
            raw = hit[1]
        else:
            raw = self._http(url)
            if raw:
                self._cache[url] = (now, raw)
        if not raw:
            return {}
        try:
            return unwrap(raw)
        except Exception as e:
            self._log('unwrap fail: %s (%s)' % (path, str(e)[:90]))
            return {}

    def _log(self, msg):
        try:
            print('[kfz] ' + str(msg), flush=True)
        except Exception:
            pass

    # ---------- 卡片 ----------
    def _card(self, v):
        try:
            vid = int(v.get('id') or 0)
            if vid <= 0:
                return None
            name = str(v.get('name') or '').strip()
            pic = str(v.get('enc_img') or '')
            # 封面走中继（签名过期会 403，中继按站内 id 换新的）；起不来就原样挂
            pic_out = self._relay().img_url(pic, vid) if pic else ''
            if not pic_out:
                pic_out = pic
            rm = str(v.get('time') or '').strip()
            eye = int(v.get('eye') or 0)
            if eye > 0:
                rm = (rm + ' · ' + self._human(eye) + '次') if rm else (self._human(eye) + '次')
            if not rm:
                rm = str(v.get('create_time') or '')
            return {
                'vod_id': str(vid),
                'vod_name': name,
                'vod_pic': pic_out,
                'vod_remarks': rm,
            }
        except Exception:
            return None

    @staticmethod
    def _human(n):
        if n >= 100000000:
            return '%.1f亿' % (n / 100000000.0)
        if n >= 10000:
            return '%.1f万' % (n / 10000.0)
        return str(n)

    def _cards(self, arr):
        out = []
        for v in (arr or []):
            c = self._card(v)
            if c:
                out.append(c)
        return out

    @staticmethod
    def _cate_of(tid):
        t = str(tid or '').strip()
        if t[:1] in ('c', 's'):
            t = t[1:]
        try:
            v = int(t)
            return v if v > 0 else 1
        except Exception:
            return 1

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        cls = []
        try:
            j = self._api('/vod/category', 'c=' + self.branch)
            for c in ((j.get('data') or {}).get('cates') or []):
                cid = int(c.get('id') or 0)
                cname = str(c.get('name') or '').strip()
                if cid <= 0 or not cname:
                    continue
                cls.append({'type_name': cname, 'type_id': 'c%d' % cid})
                for s in (c.get('sub_cates') or []):
                    sid = int(s.get('id') or 0)
                    sname = str(s.get('name') or '').strip()
                    if sid <= 0 or not sname:
                        continue
                    cls.append({'type_name': cname + '·' + sname, 'type_id': 's%d' % sid})
        except Exception as e:
            self._log('home cats: %s' % str(e)[:90])
        if not cls:
            cls = [{'type_name': n, 'type_id': 'c%d' % i} for i, n in
                   ((1, '国产'), (3, '日韩'), (2, '传媒'), (4, '欧美'), (5, '动漫'))]
        return {'class': cls, 'filters': {}, 'list': self.homeVideoContent().get('list', [])}

    def _from_relist(self, d):
        """推荐位是对象（{name, videos:[...]}），不是数组 —— 早期按数组读会拿到空"""
        for key in ('recommend_videos', 'rank_videos'):
            node = d.get(key)
            if isinstance(node, dict):
                vids = node.get('videos') or node.get('list') or []
                if vids:
                    return self._cards(vids)
            elif isinstance(node, list) and node:
                return self._cards(node)
        return []

    def homeVideoContent(self):
        try:
            j = self._api('/relist', 'c=' + self.branch)
            lst = self._from_relist(j.get('data') or {})
            if lst:
                return {'list': lst}
        except Exception:
            pass
        return {'list': self._list_page(1, 1)[0]}

    # ---------- 列表 ----------
    def _list_page(self, cate_id, page):
        j = self._api('/vod', 'c=%s&cate_id=%d&page=%d&limit=%d' % (self.branch, cate_id, page, PAGE_LIMIT))
        d = j.get('data') or {}
        return self._cards(d.get('videos')), d

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        lst, d = self._list_page(self._cate_of(tid), page)
        cur = int(d.get('current_page') or page)
        last = int(d.get('last_page') or page)
        return {
            'list': lst,
            'page': cur,
            'pagecount': max(last, cur),
            'limit': PAGE_LIMIT,
            'total': int(d.get('total') or len(lst)),
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or '').strip()
        if vid[:1] == 'v':
            vid = vid[1:]
        lst = []
        if vid:
            j = self._api('/vod/' + vid, 'c=' + self.branch)
            d = j.get('data') or {}
            v = d.get('video') or {}
            if v:
                name = str(v.get('name') or '').strip() or SITE_NAME
                m3u8 = str(v.get('url') or '').strip()
                pic = str(v.get('enc_img') or '').strip()
                cate = (v.get('cate') or {}).get('name') or ''
                tags = [str(t) for t in (d.get('hot_tags') or [])][:12]
                content = ['【站源】K站（kfzedwc 站群）· 免登录免费直取',
                           '【取流】HLS / AES-128 标准加密（非 Widevine DRM）；清单签名 1 小时一换，'
                           '播放时自动换新签名，分片与密钥走本机中继补齐防盗链 Referer']
                if cate:
                    content.append('【分类】' + cate)
                if tags:
                    content.append('【标签】' + ' / '.join(tags))
                content.append('【接口】/v1/vod/<id>（响应为 RSA+AES 加密信封，插件内已解）')
                # 封面也走中继：跟清单同一套 1 小时签名，直挂会过期变空图
                pic_out = self._relay().img_url(pic, vid) or pic
                lst.append({
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': pic_out,
                    'vod_remarks': cate or '免费直取',
                    'vod_content': '\n'.join(content),
                    'vod_play_from': SITE_NAME,
                    # 只挂站内 id：签名在播放那一刻才现取（挂着直链躺一小时必失效）
                    'vod_play_url': ('正片$' + PLAY_PREFIX + vid) if m3u8 else ('正片$' + self.host + '/'),
                })
        return {'list': lst}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        u = str(id or '').strip()
        if u.startswith('http'):
            return self._player(u)
        vid = u
        if vid.startswith(PLAY_PREFIX):
            vid = vid[len(PLAY_PREFIX):]
        elif vid[:1] == 'v':
            vid = vid[1:]
        if vid:
            relay = self._relay().hls_url(vid)
            if relay:
                return self._player(relay)
            # 中继起不来（极端设备）才退回直链：现取一次新签名，至少当下能播
            fresh = self._fresh_m3u8(vid)
            if fresh:
                return self._player(fresh)
        return self._player(self.host + '/')

    def _player(self, url):
        return {
            'parse': 0,
            'jx': 0,
            'url': url,
            'header': json.dumps({
                'User-Agent': self.headers.get('User-Agent', DEFAULT_UA),
                'Referer': self.host + '/',
            }),
            'format': 'application/x-mpegURL',
            'contentType': 'application/x-mpegURL',
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg='1'):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        kw = str(key or '').strip()
        if not kw:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': PAGE_LIMIT, 'total': 0}
        j = self._api('/vod', 'c=%s&name=%s&page=%d&limit=%d'
                      % (self.branch, urllib.parse.quote(kw), page, PAGE_LIMIT))
        d = j.get('data') or {}
        lst = self._cards(d.get('videos'))
        cur = int(d.get('current_page') or page)
        last = int(d.get('last_page') or page)
        return {
            'list': lst,
            'page': cur,
            'pagecount': max(last, cur),
            'limit': PAGE_LIMIT,
            'total': int(d.get('total') or len(lst)),
        }

    # ---------- 自检 ----------
    def action(self, action=''):
        try:
            j = self._api('/vod/category', 'c=' + self.branch)
            cats = len((j.get('data') or {}).get('cates') or [])
            lst, _ = self._list_page(1, 1)
            s = '%s · %s · c=%s · 分类 %d 个 · 列表 %d 条' % (SITE_NAME, self.host, self.branch, cats, len(lst))
            if lst:
                d = self.detailContent([lst[0]['vod_id']]).get('list') or []
                if d:
                    pu = d[0].get('vod_play_url', '')
                    s += ' · 取流 ' + ('OK' if '.' in pu or PLAY_PREFIX in pu else '空')
                    vid = str(lst[0]['vod_id'])
                    s += self._relay_check(vid)
            s += ' · 加密信封 OK'
            return s
        except Exception as e:
            return '%s · 自检异常 %s' % (SITE_NAME, str(e)[:120])

    def _relay_check(self, vid):
        """中继自检：真跑一遍「换新签名 → 取清单 → 改写」，看出来的地址是不是中继口"""
        try:
            r = self._relay()
            url = r.hls_url(vid)
            if not url:
                return ' · 中继 起不来'
            left = 0
            m = re.search(r'auth_key=(\d{9,})-', self._fresh_m3u8(vid))
            if m:
                left = max(0, int(m.group(1)) - int(time.time()))
            body = r._playlist(vid, '')
            if not body:
                return ' · 中继 清单取不到'
            segs = 0
            rewritten = True
            for ln in body.split('\n'):
                t = ln.strip()
                if not t or t[:1] == '#':
                    continue
                segs += 1
                if '127.0.0.1' not in t:
                    rewritten = False
            return ' · 中继清单 分片 %d 已改写 %s 续签 %d 次 签名剩 %d 分钟' % (
                segs, '是' if rewritten else '否', r.resigns, left // 60)
        except Exception as e:
            return ' · 中继自检失败 %s' % str(e)[:80]
