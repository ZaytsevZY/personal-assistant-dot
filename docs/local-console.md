# 交互式本地工作台

这是持续交互的本地应用，运行期间可读取最新状态并执行明确的手动操作。使用 Python 标准库服务与原生 HTML/CSS/JavaScript，无需 npm 构建或外部前端资源。

## 启动与停止

先按[本地最小版本](local-mvp.md)初始化仓库外私人目录，然后：

```sh
python3 -B -m assistant_dot --private-root "<private-root>" /workbench
```

终端显示 `http://127.0.0.1:<port>`，在本机浏览器打开。默认选择空闲端口；可用 `/workbench --port 8765` 指定端口，冲突时报错。服务只绑定 IPv4 loopback，不能指定其他地址。在当前前台进程持续运行，`Ctrl-C` 停止；没有安装登录启动项、后台服务或定时任务。电脑关机、休眠或断线时不能保证服务可用。

## 可操作的部分

- 查看任务总数、最近记录、持久水位、集中计划与功能状态。刷新或操作完成后读取最新数据，不自动轮询。
- 手动运行合成新闻或开源演示，生成私人草稿。单次请求 ID 在当前页面保留到确认结果，供网络重试去重；刷新会丢失未确认 ID，异常时应先核对记录。
- 暂停/恢复手动运行器。暂停时界面与服务端都拒绝新运行，计划预览和登记仍可使用。
- 预览 IANA 计划窗口，不保存、不执行；登记只写私人账本；明确点击候选后才手动运行。
- 核对中断记录，保留未知结果，不自动重跑。后台调度和消息/日程写入按钮保持禁用。公开 RSS 与飞书/日历状态检查仅在明确点击时执行，账号消息和日程正文不提供网页读取。

任务和候选表最多显示最近 100 条；总数与最近记录指标分别标注。只返回合成记录和必要状态，不加载笔记、草稿正文、幂等键、账号或凭据。规则与恢复语义见[统一计划](manual-plans.md)，旧版[离线快照](console-snapshot.md)作为兼容导出保留。

## 新闻与推荐

新增[合成新闻预览](news-preview.md)：手动选择本次兴趣和分析时点，查看重大覆盖、兴趣与探索三个板块，展开来源、日期、事实陈述和评论。不会创建任务、写入兴趣或读取私人笔记；真实新闻在独立的“公开新闻”板块手动获取，见[真实连接](real-connections.md)。

## 本地安全边界

校验精确 Host、Origin 与每次启动生成的随机请求口令；写操作必须带同源 Origin、口令和受限 JSON。跨站 API、iframe、错误 Host、超大或未知字段请求被拒绝。只开放固定应用资源与动作，不提供目录浏览、任意文件读取、URL 代理或 shell 执行。

CSP 将资源与连接限制在本服务来源，禁止表单、嵌入和外部资源；响应不缓存，不记录请求正文或口令。页面使用文本节点。`network_enabled=false` 继续约束合成任务运行器。单独的公开 RSS 手动入口仅访问固定官方源；连接状态入口只探测已有本地配置，不开启投递，也不改变原运行器设置。

这是可信单机原型，不是多用户身份认证。其他本机进程或用户可能请求页面并取得会话口令，不应运行在不可信共享主机，不要映射公网、加代理或开隧道。没有 TLS、远程账户管理、跨机器租约、未知插件沙箱或加密备份。

## 验证

```sh
python3 -B tests/acceptance.py
python3 -B tests/plans_acceptance.py
python3 -B tests/workbench_acceptance.py
python3 -B tests/news_acceptance.py
python3 -B tests/live_news_acceptance.py
python3 -B tests/connections_acceptance.py
node tests/workbench_news.js
node tests/console_preview.js
node --check assistant_dot/workbench.js
python3 -B scripts/check_public.py
```

HTTP 验收临时启动 loopback 服务并在结束时关闭，私人目录全部是临时合成数据。浏览器验证针对工作台自己的 HTTP 应用与 API，不代理旧 `file:` 文件，也不绕过本地文件协议限制。
