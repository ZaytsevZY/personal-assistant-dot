# 真实来源与本地连接

通用代码、接口、测试和说明在 Git。账号凭据、真实聊天、日程、私人配置和缓存必须留在仓库之外；“项目在 Git”不意味着把这些数据公开。

## 当前真实能力

| 功能 | 实现状态 | 验证边界 |
| --- | --- | --- |
| 官方公开 RSS | CLI 与工作台均可手动获取 | 有真实只读验证；没有独立事实核查或重大新闻完整性保证 |
| 飞书 profile 状态 | 显式选择已有 CLI profile，脱敏返回凭据状态 | 本地状态检查，不代表服务器令牌或消息读取成功 |
| 飞书单会话读取 | CLI 已实现，显式 profile、会话 ID 和七天以内窗口 | 只做合成测试；真实账号需要已授权且可用的 user 身份 |
| Apple 日历权限 | 固定身份应用；状态不请求，独立 CLI 可显式发起授权 | 只有用户能处理系统完整访问提示；界面可见不代表应用获权 |
| Apple 日历读取 | 完整授权后可列日历、按 ID 限窗读取或仅验证数量 | 代码与本机授权分开验证；未授权时拒绝读取 |
| 消息发送、日程写入 | 未实现、未开放 | 没有发送或创建测试，没有后台自动投递 |

## 公开新闻：点击才联网

```sh
python3 -B -m assistant_dot /news-fetch
python3 -B -m assistant_dot /news-fetch --sources fed,nasa
```

工作台提供“公开新闻”板块，可按次选择来源；`/news-sources` 可离线查看清单与暂缓原因。仅访问代码中固定注册的已审查 feed，不使用账号、搜索历史或私人兴趣，不抓文章正文和图片，不持久化结果、不投递。请求发出后可能在上游留下常规访问日志和客户端 IP；不传入任何私人内容。

来源与官方 RSS 说明：

- [UN Geneva RSS](https://www.ungeneva.org/en/news-media/rss)：机构时政与人权新闻；[固定 feed](https://www.ungeneva.org/en/news-media/press-releases-list/rss.xml)。该地址由官方旧地址重定向核实，运行时不自动跟随跳转。
- [Federal Reserve Board RSS](https://www.federalreserve.gov/feeds/feeds.htm)：机构经济与货币政策发布；[固定 feed](https://www.federalreserve.gov/feeds/press_all.xml)。
- [NASA RSS](https://www.nasa.gov/rss-feeds/)：机构科技与航天发布；[固定 feed](https://www.nasa.gov/news-release/feed/)。

另已增加 ECB 与 Global Voices，来源清单、许可与当前限制见[来源审查](news-sources.md)。下文初始三源说明保留以解释已有边界。这仍是窄范围的来源，不能代表国家、语言或编辑立场的多样性。主题来自来源注册表的粗分类，不是对每篇报道的语义判断。保留来源标题、报道链接、发布日期和获取时间；事件日期不从标题猜测，重大性不自动推断。真实 RSS 暂不进入兴趣推荐排名，也不把机构表述当成已核实事实。此前的[合成推荐试验](news-preview.md)仍独立保留。

每源最多 512 KiB、10 条近七天候选；单源连接超时 5 秒、传输最多 12 秒，进程有额外总时限；当前五个来源最多三家提供方并发、同一提供方串行，最坏约 28 秒。来源故障与没有近期候选分别显示。拒绝 DTD、实体声明、非 UTF-8、不支持的结构及过大 XML；拒绝无时区和无法解析的发布日期。CET/CEST 按明示固定偏移处理，不推断其他未知时区。只展示固定来源域名上的干净 HTTPS 报道链接，不自动访问这些链接。

使用 `/usr/bin/curl` 的正常证书验证与系统信任库，不使用 `-k`、登录凭据、cookies、curlrc、代理或重定向。超时或输出超限时终止该调用的进程组，错误正文不回显。固定官方 HTTPS 域名仍依赖操作系统 DNS 与证书信任，不提供证书钉扎或不可信网络隔离。没有任意 URL 获取 API。

RSS 供给不等于文章、图片或所有内容的再分发许可。仅本地阅读标题并链接原站；机构名称不表示背书。没有把实际获取的标题、文章、feed 缓存或图片提交到 Git，MIT 只覆盖项目自有代码与材料。

## 飞书：每次明确选择账号

项目复用已安装的官方 `lark-cli`，不安装软件、不执行登录或 OAuth、不复制其钥匙串凭据。`--profile` 仅影响本次调用，不运行 `profile use`，不改变全局默认账号。工作与个人 profile 必须由用户分别建立并确认，不能默认另一个账号就是个人身份。

```sh
python3 -B -m assistant_dot /feishu-status --profile PROFILE_NAME
python3 -B -m assistant_dot --private-root "<private-root>" /feishu-read --profile PROFILE_NAME --chat-id CHAT_ID --since START_ISO --until END_ISO
```

状态查询只返回机器人与用户凭据是否可用，不返回 app ID、用户 ID、姓名、邮箱、scope 或凭据。工作台必须手动输入 profile 并点击检查，首次加载不探测账号。

单会话读取仅在 CLI 中开放，要求仓库外已初始化私人目录、明确 chat ID、明确带时区起止时间，最多七天和第一页 20 条；不自动翻页、不下载附件、不补抓 reactions、不推断目标会话。返回的原始响应可能含私人消息、ID 和后续页 token，只输出给当前本地 CLI，不保存、不送入模型或网页。请勿重定向到仓库、共享终端或公开日志。

凭据不是 ready/available 时拒绝读取，不自动登录或刷新。CLI API 本身的既有令牌管理仍由其控制；本项目不扩大 scope。具体账号的可读范围、服务器令牌有效性和个人 profile 尚需用户在自己的环境核实。连接器缺权限时应停下说明，不能换账号或机器人补读。

## Apple 日历：固定应用身份，明确授权

项目自有的 **Personal Assistant Calendar Reader** 应用使用 bundle ID `org.personalassistantdot.calendarreader`。需要 macOS 14+、系统 Swift 工具链与 codesign。先构建，再按明确同意的范围授权；构建本身不会启动应用、请求权限或读取日程。

```sh
python3 -B scripts/build_calendar_reader.py
python3 -B -m assistant_dot /calendar-status
# 明确同意系统完整访问后，才手动执行下一条：
python3 -B -m assistant_dot /calendar-authorize
```

默认安装在系统 Shared 目录中的 `PersonalAssistantDot-<uid>` 专用子目录：目录与应用仅当前用户可访问，不用它共享私人数据。该位置仍须在所有 Git 工作树之外。构建器不会覆盖现有应用或 receipt。更新原生代码时，应先关闭应用，将旧应用和 receipt 移到 Git 树外的私人备份目录，再重新构建；有需要可恢复成对备份。不要删除系统授权数据库或绕过 Gatekeeper。若系统拦截，应停止并报告。

应用是本机 ad-hoc 签名，未公证；不是具有开发者证书的通用分发包。固定名称和 bundle ID 可以清楚标识请求应用，不能保证重新编译后继承 TCC 权限。更新可能需要用户重新核对系统权限。客户端每次检查应用身份、所有者权限、源码清单、签名与二进制摘要；不匹配时拒绝启动，不能用新源码冒用旧应用。

`/calendar-authorize` 先探测权限；仅 `not_determined` 时启动授权窗口，由用户亲自处理 macOS 提示。被拒绝、受限制或仅写权限时不会重复弹窗，而是报告需要在系统设置核对。授权分支不读取日历或日程。工作台没有授权 API；状态按钮只查询权限，不弹授权请求。

macOS 的[完整日历访问](https://developer.apple.com/documentation/eventkit/ekeventstore/requestfullaccesstoevents(completion:))包含读写能力；不能称其为系统“只读授权”。应用说明使用 [NSCalendarsFullAccessUsageDescription](https://developer.apple.com/documentation/bundleresources/information-property-list/nscalendarsfullaccessusagedescription)。项目只实现读取，不包含新增、修改或删除日程方法，也不联网。读取之前再次检查授权，未获得完整访问时拒绝读取。

```sh
python3 -B -m assistant_dot --private-root "<private-root>" /calendar-calendars
python3 -B -m assistant_dot --private-root "<private-root>" /calendar-verify --calendar-id CALENDAR_ID --since START_ISO --until END_ISO
python3 -B -m assistant_dot --private-root "<private-root>" /calendar-events --calendar-id CALENDAR_ID --since START_ISO --until END_ISO
```

读取需要仓库外已初始化的私人目录。日历可能重名，列表包含来源标题与类型，只在本地 CLI 返回；用户明确核对来源和日历 ID，不默认选取某个账号或同名日历。原生 `resolve` 操作可按用户明确提供的来源和标题精确匹配，只返回匹配数与 ID；多项匹配时不得自动选择。

窗口必须带时区、精确到秒且最多七天。`/calendar-verify` 仅返回命中数量和窗口长度，不返回事件正文；零条也明确报告为空。`/calendar-events` 最多返回 200 条标题、起止时间与全天标记，不序列化参与者、地点、备注和会议链接。EventKit 会在本地进程中取回匹配事件对象，因此数量验证也属于真实日历读取，必须在同意范围内。

客户端通过 LaunchServices 运行同一应用，结果文件位于一次性的所有者私有临时目录，结束后清理；原生读取进程自带 15 秒时限。超时或结果失败需报告不确定状态，不自动重试授权或改用其他权限通道。日历列表、匹配 ID 和事件不进入网页、Git、模型调用或其他服务；CLI 输出不要重定向至仓库、共享终端或公开日志。没有 App 密码、iCloud 凭据复制、日程写入或自动运行。

## 执行边界

`settings.json` 的网络关闭标记继续约束合成任务运行器；不会因此自动打开账号、抓取或投递。公开 RSS 是单独的手动、固定来源权限。账号读取只能由带明确目标的 CLI 命令触发，状态检查不授予读取权限。工作台只暴露 RSS 和脱敏状态接口，没有聊天、日程正文或写入接口。

没有安装启动项、后台进程或定时任务；Mac 休眠或关闭时不可用。进程包装只是时限和输出约束，不是第三方插件沙箱。真实连接的授权、私有数据、备份及所有失败状态都不会成为公开提交内容。
