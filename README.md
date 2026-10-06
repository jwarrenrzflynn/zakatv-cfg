# ZakaTV 配置备用线

> CF 主站限流 / 故障时，客户端改从本仓库拉配置。**这条线完全自洽，不依赖 CF。**

## 一、订阅地址（三选一）

| 口径 | 地址 |
|---|---|
| ① 国内加速代理（推荐） | `https://ghfast.top/https://raw.githubusercontent.com/jwarrenrzflynn/zakatv-cfg/main/ZakaTV.json` |
| ② 官方直连 | `https://raw.githubusercontent.com/jwarrenrzflynn/zakatv-cfg/main/ZakaTV.raw.json` |
| ③ jsDelivr CDN | `https://cdn.jsdelivr.net/gh/jwarrenrzflynn/zakatv-cfg@main/ZakaTV.jsdelivr.json` |

> 三条地址对应三个**不同文件**，不是同一个文件换前缀——每条线里的爬虫包地址跟它自己走的通道一致，
> 避免"走 jsDelivr 拉配置、包却要绕 ghfast"这种半吊子状态。

> 换线后记得在壳里**清缓存再重载配置**。

## 二、为什么叫"自洽"

主站配置里的爬虫包指向 `tv.ystv.top/files/ai-zhineng.png`——只搬 json 不搬包，
CF 一挂客户端还是废。所以本仓库做了两件事：

1. **爬虫包入仓**：`files/ai-zhineng.jar`，与主站逐字节相同（md5 `3e08e2edbb704a2d5fc81e21971a9594`）。
2. **引用整体改写**：备用配置里的 `spider` 以及所有指向站方 `/files/` 的资源，全部换成 git 地址。

结果：CF 全站 429 的时候，备用线照样能拉配置、能下包。

## 三、文件说明

```
ZakaTV.json            备用主配置（ghfast 代理口径，推荐）
ZakaTV.raw.json        备用主配置（raw.githubusercontent 直连口径）
ZakaTV.jsdelivr.json   备用主配置（jsDelivr CDN 口径）
ZakaTV.origin.json     站方原始配置，仅作对照，资源仍指向 CF
files/ai-zhineng.jar   爬虫包原件（与主站同字节）
files/ai-zhineng.png   同字节，保留站方原文件名形态
manifest.json          指纹清单：各文件 md5 / 站点数 / 同步时间 / 数据来源
订阅地址.txt            上面三条地址，直接粘
sync/bot.py            同步机器人
```

## 四、同步机器人

定时把 CF 上的最新配置与爬虫包同步进本仓库，并自动完成地址改写。

```bash
cp sync/config.example.json sync/config.json   # 填入 token
python3 sync/bot.py            # 常驻，默认 15 分钟一轮
python3 sync/bot.py --once     # 只跑一轮
python3 sync/bot.py --check    # 只比对差异，不推送
```

行为要点：

- **多个源轮询**：`tv / admin / ztv2` 三个域依次试，单域限流不判死。
- **坏内容不落盘**：拿到限流页 / HTML / 空站点列表一律丢弃，绝不覆盖上一次的好内容。
- **半成品不推**：配置变了但爬虫包取不到（限流），本轮跳过，等下一轮——不会推出"配置是新的、包是旧的"的错配版本。
- **指纹去重**：`manifest.json` 记 md5，只推真正变化的部分；包没变就不重复推 1.2MB。
- **失败退避**：连续失败按 2 倍递增等待，最长 1 小时。

## 五、已知边界

- 配置里 `ext.base` / `ext.host` 指向主站的部分是**运行时接口**（站点 API），不是静态资源，无法镜像到 git；
  这类站点在 CF 彻底不可用时仍会不可用。备用线解决的是**配置下发 + 爬虫包分发**。
- 备用线是主站的镜像，**内容以主站为准**，本仓库只做搬运，不改站点配置。
- 仓库公开：配置本身在主站就是公开下发的，无额外暴露。
