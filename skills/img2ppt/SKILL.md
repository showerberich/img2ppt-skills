---
name: img2ppt
slug: img2ppt
displayName: 图片转可编辑 PPT
version: 1.0.0
summary: 调用 img2ppt 服务，把图片或 PDF 转成每个文字和图形都可编辑的 PPTX
description: Convert an image or PDF into an editable PowerPoint (.pptx) through the img2ppt HTTP API. Use when the user wants a picture, screenshot, poster, diagram, infographic or PDF turned into a PPT/PPTX they can edit, or asks to "把这张图转成 PPT / 做成可编辑的 PPT". Requires an API token in IMG2PPT_TOKEN; conversions cost credits, and the account is topped up on the img2ppt site.
description_zh: 把图片、截图、海报、信息图、流程图或 PDF 转成完全可编辑的 PPTX：每个文字是原生文本框，每个色块、图标和箭头都是原生 PowerPoint 形状。通过 img2ppt 服务转换，需要 IMG2PPT_TOKEN，按张或按页计费，失败自动退分。
description_en: Convert images, screenshots, posters, diagrams, infographics, or PDFs into fully editable PowerPoint files through the img2ppt API. Every text box, shape, icon, and arrow is a native PowerPoint object. Requires IMG2PPT_TOKEN; usage is charged per image or page, and failed jobs are refunded automatically.
author: img2ppt
license: MIT
category: productivity
allowed-tools: Bash
---

# 图片 / PDF → 可编辑 PPT

把一个图片或 PDF 交给 img2ppt 服务，拿回一份**每个文字框、色块、图标都是原生可编辑对象**的
PPTX（不是整页位图贴进去的假 PPT）。

## 效果预览

![img2ppt 成品示例：信息图、流程图、科研图重建后的可编辑 PPT](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/hero-grid.webp)

下面是「原图 → 重建后的可编辑 PPTX 渲染结果」对照：

| 原图 | 可编辑 PPT 渲染 |
|---|---|
| ![空间规划框架原图](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-framework-src.webp) | ![空间规划框架重建结果](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-framework-out.webp) |
| ![微塑料食物链原图](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-microplastic-src.webp) | ![微塑料食物链重建结果](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-microplastic-out.webp) |
| ![RAG 架构原图](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-rag-src.webp) | ![RAG 架构重建结果](https://raw.githubusercontent.com/showerberich/img2ppt-skills/main/skills/img2ppt/assets/demo-rag-out.webp) |

## 先决条件

1. 一枚令牌（用一次就一直有效，可随时吊销）：

   ```bash
   curl -s -X POST "$IMG2PPT_API/api/auth/token" \
     -H 'Content-Type: application/json' \
     -d '{"email":"你注册的邮箱","password":"站内设置的登录密码","name":"claude-code"}'
   ```

   返回里的 `token` **只显示这一次**，存进环境变量：

   ```bash
   export IMG2PPT_TOKEN="ppt_xxx"
   export IMG2PPT_API="https://image2ppt.asia"     # 一般不用改
   ```

   没设过登录密码：先在站上登录 → 个人中心 → 设置登录密码。

2. 积分。**一张图 1 积分，PDF 每页 1 积分**，跑失败会自动退回、不扣费。
   积分不够时接口返回 402，把 `recharge_url` 给用户，让他去站上充值（微信/支付宝）。

## 怎么用

```bash
python3 scripts/img2ppt.py me                     # 我是谁、还剩多少积分
python3 scripts/img2ppt.py convert 海报.png        # 转 → 海报.pptx（落在原图旁边）
python3 scripts/img2ppt.py convert 海报.png -o 结果.pptx
python3 scripts/img2ppt.py convert 讲义.pdf --pages 5   # 多页 PDF：只转前 5 页（省积分）
python3 scripts/img2ppt.py status 12345           # 单独查某个作业
```

`convert` 会一直等到成品出来（**20–40 分钟是常态**，见下），期间把服务端的中文进度
原样打出来，例如：

```
作业 #12345 已提交（扣 1 积分，余额 4）
  [3m12s] 已出第 2 版中间稿，正在对照原图调整…
  [18m40s] 正在与设计稿逐块比对（最差块：右下角）
成品已保存：/Users/me/海报.pptx（18 分 51 秒 · 第 13 版）
```

退出码：`0` 成功 · `2` 令牌无效 · `3` 积分不够（要去充值） · `4` 转换失败 · `5` 超时。
脚本只依赖 Python 3 标准库，不用 pip 装任何东西。

## 为什么要等 20–40 分钟

这不是「一次生成」。服务端是把原图读成元素清单 → 渲染成 PPTX → **再渲染回图片和原图
逐块比对**，找出最差的那一块去修，如此循环十几版。慢是因为在自我校对，不是在卡。
所以：

- **不要**用几十秒的短超时去轮询，也不要因为「半天没动静」就重试 —— 重试是**重新扣一次分**。
- 想给用户看中间效果：`GET /api/v1/jobs/{id}/preview` 是最新一版渲染图，
  `GET /api/v1/jobs/{id}/round/{n}/pptx` 是第 n 版**中间稿的 PPT**（`job.round` 那个号一定下得到）。
  等不及的人可以先拿走看，后面服务端还会继续改。
- 报进度时把服务端给的 `stage` 原样转述给用户（它是中文自然语言，不用自己翻译）。

## 给用户报价之前

先调 `GET /api/v1/pricing` 拿准数字，别自己编：

- 一张图 1 积分；PDF 每页 1 积分，超过积分数会返回 `need_confirm`，让用户选转前几页；
- 上限：单文件 40MB、PDF 200 页；
- 多页 PDF 一定要**先把页数和要扣的分数告诉用户**再确认，静默扣一大笔会伤信任。

## HTTP 接口速查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/me` | 邮箱 + 余额 + `recharge_url` |
| GET | `/api/v1/pricing` | 计价与限制（动手前先看） |
| POST | `/api/v1/convert` | multipart：`file`、`ratio`(auto/16:9/4:3)、`confirm_pages` |
| GET | `/api/v1/jobs/{id}` | `status`(pending/ok/failed) · `stage` · `preview` · `round` · `has_file` |
| GET | `/api/v1/jobs/{id}/pptx` | 成品 PPTX（没跑完 404） |
| GET | `/api/v1/jobs/{id}/preview` | 最新中间稿的渲染图 |
| GET | `/api/v1/jobs/{id}/round/{n}/pptx` | 第 n 版中间稿的 PPT |

全部要带 `Authorization: Bearer $IMG2PPT_TOKEN`。状态码：`401` 令牌无效 ·
`402` 积分不够（去 `recharge_url` 充值）· `403` 别人的作业 · `404` 不存在/还没好。

## 别做的事

- **别把令牌写进代码、日志或提交到仓库**。它等同于账号在这个工具里的长期凭证。
- 别替用户「顺手」多转几张试效果 —— 每张都扣积分，扣的是他的钱。
- 令牌疑似泄露：`POST /api/auth/token/revoke`（带自己的 Bearer）立刻吊销，不用登录网页。
