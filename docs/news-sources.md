# 新闻来源审查与覆盖缺口

当前注册表在 [news_sources.py](../assistant_dot/news_sources.py)，审查日期为 2026-11-04。`/news-sources` 可在不联网时查看类型、机构/编辑背景、语言、使用边界和暂缓候选。当前只有手动、个人本地阅读；来源政策可能变化，需要再次核对，注册表不授予商业使用或再分发权。

| 已注册来源 | 范围与视角 | 使用核查 |
| --- | --- | --- |
| UN Geneva | 国际机构发布，时政为粗分类 | [官方 RSS](https://www.ungeneva.org/en/news-media/rss)和[UN 条款](https://www.un.org/en/about-us/terms-of-use)；个人阅读，不再分发 |
| Federal Reserve Board | 美国央行一手经济发布 | [官方 RSS 阅读说明](https://www.federalreserve.gov/feeds/feeds.htm)及[网站政策](https://www.federalreserve.gov/website-linking-policies.htm)；标明来源，外链内容另有权利 |
| NASA | 美国机构的科技/航天发布 | [官方 RSS](https://www.nasa.gov/rss-feeds/)及[使用说明](https://www.nasa.gov/nasa-brand-center/images-and-media/)；仅标题与链接，不取图片、标志或正文 |
| European Central Bank | 欧元区一手经济发布 | [RSS](https://www.ecb.europa.eu/home/html/rss.en.html)与[版权条件](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)；保持来源归属，不转载署名论文 |
| Global Voices | 非营利全球贡献者网络的编辑报道与评论 | [RSS 页面](https://globalvoices.org/feeds/)及[归属政策](https://globalvoices.org/about/global-voices-attribution-policy/)允许按条件使用；保留原文、作者和归属政策链接，第三方素材有例外；不获取媒体或正文 |

Global Voices 是不同于机构公报的编辑来源，但不能因为域名或组织不同就证明某条报道有独立消息链。它的[机构说明](https://globalvoices.org/about/)介绍全球贡献者网络与非营利结构；这不是对每篇文章准确性、立场或消息来源的认证。本机可能无法访问它，界面将保留失败状态，不能把“已注册”写成“已获取”。

## 暂缓，不发出请求

| 候选 | 审查结果与原因 |
| --- | --- |
| Le Monde | [官方 RSS 条件](https://www.lemonde.fr/en/about-us/article/2026/03/27/le-monde-rss-feeds_6751860_115.html)限定个人、非职业、非集体阅读；本机获取未成功，暂不注册 |
| CNA | [官方 RSS 条件](https://www.channelnewsasia.com/rss/rssterms)限制个人非商业用途、改动和转发，要求直达原文；本机获取未成功，暂不注册 |
| 中央通訊社（台湾） | [官方 RSS 与使用规范](https://www.cna.com.tw/about/rss.aspx)允许有归属的个人非商业阅读，需保留发稿归属，不得引用全文；官网列出的 FeedBurner 国际 feed 在本机超时，暂不注册；与新加坡 CNA 是不同机构 |
| The Register | [官方 feeds](https://www.theregister.com/design/page/feeds)与[条款](https://www.theregister.com/profile/terms_and_conditions_of_use)可供个人阅读，但本机收到人机验证 HTML；不解挑战、不伪装浏览器，不作为新闻解析 |
| Al Jazeera | [条款](https://terms.aljazeera.net/)对自动访问另有限制，不能仅因存在 RSS 就假设可覆盖这些限制；暂不接入 |
| arXiv | [RSS](https://info.arxiv.org/help/rss.html)指向[API 条款](https://info.arxiv.org/help/api/tou.html)，元数据与论文权利不同，并要求所有受控机器遵守单连接与限频；当前没有跨进程限频状态，暂不接入 |

不加入未核实使用条件、付费或要求新账号/权限的来源。没有调整代理、TLS 信任、身份、系统设置或访问保护来提高成功率。

## 如何呈现覆盖

每个主题分别显示近期候选数、提供一手候选的机构数、编辑报道提供方数、所选来源数、成功来源数及缺口。提供方按注册表的 publisher 去重，同一家机构的多个栏目不会被当成多家；这个数字不是独立核实数。

缺口包括：未选择来源、来源不可用、没有近七天候选、缺一手材料、缺编辑报道、编辑报道提供方不足两家。即使没有这些缺口，也不宣称全面覆盖、重大性已判断或消息链已核实。

地域标签描述来源的机构或编辑背景，不代表文章发生地点。当前仍以英文为主，中文、亚洲/非洲/拉美本地一手材料与更多编辑机构不足；Global Voices 的全球网络不能替代这些缺口。没有按地区给用户推断政治立场，也没有从点击学习兴趣。

对 Global Voices，仅按来源明确提供的 category 标签映射时政、经济、科技；无匹配标签时计为主题外，不从标题猜测。标签到三类主题的映射是本项目的粗规则，不是作者认可的重大性或事实判断。

## 日期、失败与性能

RSS 使用带明确时区的 pubDate；Atom 优先 published，只有 updated 时保留 `published_at=null`，另列更新时间及 `atom_updated_only`。事件日期仍未知，不把发布时间或更新时间写成事件发生时间。更新过的旧报道、跨来源相同事件和更正尚未自动识别。

每源保持 512 KiB、10 条近七天候选上限；最多三个提供方并发，同一提供方的 feed 串行。当前五个来源最坏约 28 秒加少量启动开销。只在明确点击后运行临时工作线程，结束就回收，没有计时器、自动重试或后台投递。

错误区分超时、DNS、连接、TLS、HTTP、响应过大与不支持/不安全的格式；不显示原始 stderr。请求失败与成功但无近期候选分别记录。页面输入变化隐藏旧结果，刷新保留本页来源选择，页面重载恢复公开默认；不保存兴趣或阅读历史。

标题、作者和条款用文本及原站链接呈现，不获取或执行来源中的 HTML、脚本、指令、媒体或附件。真实新闻、原始 feed 与真实验证结果没有写入公共仓库；测试使用合成资料。
