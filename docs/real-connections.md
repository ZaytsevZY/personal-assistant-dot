# 真实来源与本地连接

通用代码、接口、测试和说明在 Git。账号凭据、真实聊天、日程、私人配置和缓存必须留在仓库之外；“项目在 Git”不意味着把这些数据公开。

## 当前真实能力

| 功能 | 实现状态 | 验证边界 |
| --- | --- | --- |
| 官方公开 RSS | CLI 与工作台均可手动获取 | 有真实只读验证；没有独立事实核查或重大新闻完整性保证 |
| 飞书 profile 状态 | 显式选择已有 CLI profile，脱敏返回凭据状态 | 本地状态检查，不代表服务器令牌或消息读取成功 |
| 飞书单会话读取 | CLI 已实现，显式 profile、会话 ID 和七天以内窗口 | 只做合成测试；真实账号需要已授权且可用的 user 身份 |
| Apple 日历权限 | EventKit 原生只读探测，不请求访问 | 在 Mac 验证；界面能看到日历不代表脚本有权限 |
| Apple 日历读取 | 已获系统权限时可在 CLI 列日历、按 ID 读取 | 合成参数测试；未获授权的环境不读取真实日程 |
| 消息发送、日程写入 | 未实现、未开放 | 没有发送或创建测试，没有后台自动投递 |

## 公开新闻：点击才联网

```sh
python3 -B -m assistant_dot /news-fetch
python3 -B -m assistant_dot /news-fetch --sources fed,nasa
```

工作台新增“公开新闻”板块。仅访问代码中固定注册的三个官方 feed，不使用账号、搜索历史或私人兴趣，不抓文章正文和图片，不持久化结果、不投递。请求发出后可能在上游留下常规访问日志和客户端 IP；不传入任何私人内容。

来源与官方 RSS 说明：

- [UN Geneva RSS](https://www.ungeneva.org/en/news-media/rss)：机构时政与人权新闻；[固定 feed](https://www.ungeneva.org/en/news-media/press-releases-list/rss.xml)。该地址由官方旧地址重定向核实，运行时不自动跟随跳转。
- [Federal Reserve Board RSS](https://www.federalreserve.gov/feeds/feeds.htm)：机构经济与货币政策发布；[固定 feed](https://www.federalreserve.gov/feeds/press_all.xml)。
- [NASA RSS](https://www.nasa.gov/rss-feeds/)：机构科技与航天发布；[固定 feed](https://www.nasa.gov/news-release/feed/)。

这只是窄范围的机构来源，不能代表国家、语言或编辑立场的多样性。主题来自来源注册表的粗分类，不是对每篇报道的语义判断。保留来源标题、报道链接、发布日期和获取时间；事件日期不从标题猜测，重大性不自动推断。真实 RSS 暂不进入兴趣推荐排名，也不把机构表述当成已核实事实。此前的[合成推荐试验](news-preview.md)仍独立保留。

每源最多 512 KiB、10 条近七天候选；单源连接超时 5 秒、传输最多 12 秒，进程有额外总时限；三源串行最多约 42 秒。来源故障与没有近期候选分别显示。拒绝 DTD、实体声明、非 UTF-8、不支持的结构及过大 XML；拒绝无时区和无法解析的发布日期。CET/CEST 按明示固定偏移处理，不推断其他未知时区。只展示固定来源域名上的干净 HTTPS 报道链接，不自动访问这些链接。

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

## Apple 日历：权限与目标分开

```sh
python3 -B -m assistant_dot /calendar-status
python3 -B -m assistant_dot --private-root "<private-root>" /calendar-calendars
python3 -B -m assistant_dot --private-root "<private-root>" /calendar-events --calendar-id CALENDAR_ID --since START_ISO --until END_ISO
```

Mac 通过自有 Swift/EventKit 桥接；需要系统 Swift 工具链。每次编译缓存位于独立临时目录，结束清理。状态查询只调用授权状态 API，不读取日历或请求访问。读取函数先检查已有系统授权，未授权、被拒绝、受限制或仅写权限时拒绝读取。

日历名称可能重名，列表包含来源标题与类型，只在本地 CLI 返回。必须由用户核对账户与日历，并主动选择 ID；没有默认选择“个人”或任何其他同名日历。只读所选日历最多七天、200 条事件，保留时区与全天标记；不读取参与者、地点、备注和会议链接，不创建、修改或删除任何事件。列表及事件只在本地 CLI 返回，不进入网页、Git 或模型调用。

Apple 的 EventKit 读取通常需要系统完整访问权限，该权限包含读写能力；本项目桥接只实现读取，不能将代码边界描述成系统授予的“只读权限”。[Apple 授权状态说明](https://developer.apple.com/documentation/EventKit/EKAuthorizationStatus)区分 fullAccess、writeOnly 等状态。应用身份、签名与权限归属取决于实际宿主；当前命令行桥接没有签名应用打包或授权请求入口，不能保证在别的宿主直接继承权限。

若状态为 `not_determined`，真实读取仍未接通。下一步需先确定稳定的本地应用身份及访问范围，并由用户明确同意后在 Mac 完成系统授权；不能用打开 Calendar 界面、AppleScript 或其他权限通道绕过。没有创建 App 密码、上传 iCloud 凭据或改系统设置。

## 执行边界

`settings.json` 的网络关闭标记继续约束合成任务运行器；不会因此自动打开账号、抓取或投递。公开 RSS 是单独的手动、固定来源权限。账号读取只能由带明确目标的 CLI 命令触发，状态检查不授予读取权限。工作台只暴露 RSS 和脱敏状态接口，没有聊天、日程正文或写入接口。

没有安装启动项、后台进程或定时任务；Mac 休眠或关闭时不可用。进程包装只是时限和输出约束，不是第三方插件沙箱。真实连接的授权、私有数据、备份及所有失败状态都不会成为公开提交内容。
