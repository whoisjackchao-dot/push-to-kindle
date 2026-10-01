# Kindle 阅读流水线

把项目里的 Markdown 一条命令变成 Kindle 上可读的电子书，并推送到设备。
配套脚本全在 `D:\DSH\kindle-jb\`，**零配置、免管理员**。

## 零、DSH 斜杠命令 `/push-to-kindle`

已注册为 DSH 用户级 skill（`C:\Users\<你的用户名>\.dsh\skills\push-to-kindle\SKILL.md`），在 DSH 里直接输入即可：

```
/push-to-kindle D:\DSH\你的项目\docs
/push-to-kindle 把 D:\DSH\paper 合并成一本推到我 kindle
```

也可以用自然语言触发（“推到 kindle”“把 md 发到 kindle”）。skill 里固化了参数表、**执行后必须做的 SHA256 核对**、以及 USB 未就绪时的排查步骤。

> 改了 skill 内容后无需重启 DSH —— 技能目录会热加载。
## 一、最常用的四条命令

```powershell
cd D:\DSH\kindle-jb

# 1) 单个 md -> 一本书，并推送到 Kindle
.\publish-to-kindle.ps1 -Path .\README.md -Push

# 2) 整个项目目录：每个 md 各一本书
.\publish-to-kindle.ps1 -Path D:\DSH\myproject -Recurse -Push

# 3) 整个项目合并成一本（适合把一套文档合成"一本书"读）
.\publish-to-kindle.ps1 -Path D:\DSH\myproject\docs -Recurse -Merge -Title "我的项目文档" -Push

# 4) 首次使用 / 修复工具链（装 pandoc + ebooklib + markdown）
.\publish-to-kindle.ps1 -Bootstrap -Path .\README.md
```

## 二、参数

| 参数 | 说明 |
|---|---|
| `-Path` | md 文件或目录（默认当前目录），可多个 |
| `-Recurse` | 目录时递归查找 |
| `-Merge` | 多个 md 合并成一本书 |
| `-Title` / `-Author` | 书名 / 作者（书名默认取文档首个 H1） |
| `-LibraryDir` | 成书输出目录（默认 `.\out`，同时是 OPDS 书库） |
| `-DestDir` | Kindle 内目标子目录。**留空则自动识别**：`markdown` → `documents\markdown` → `documents\Books` → `documents`。想强制指定就写全，例如 `-DestDir "documents\markdown"` |
| `-Engine` | `auto`(默认) / `pandoc` / `lib` / `builtin` |
| `-Name` | 输出文件名（不含扩展名）。留空则：单文件用源文件名、合并用 `-Title`。用于源文件叫 `main.md` 但想输出成 `xxx_main.epub` 的情况 |
| `-EmbedFont` | 是否内嵌中文字体，**默认开启**。`-EmbedFont:$false` 关闭 |
| `-FontRegular` / `-FontBold` | 内嵌用的字体文件（默认 Noto Sans SC **Medium** / Bold） |
| `-Push` | 尝试直接拷入已挂载的 Kindle（SHA256 校验） |
| `-Eject` | 推送后安全弹出设备 |
| `-Bootstrap` | 缺工具时自动 pip 安装到本目录 `pylib` |

## 三、两条推送通道（互为备份）

**通道 A：USB（快，但依赖设备把存储交接给电脑）**
Kindle 挂载为盘符时，`-Push` 直接拷到 `documents\Books`，逐文件 SHA256 校验后报告。
判断是否可用：`E:\` 能列出 `system` 与 `documents` 两个目录即视为就绪。

**通道 B：Wi-Fi / OPDS（不依赖 USB，实测可靠）**

```powershell
# 在电脑上起本地书库服务（放在后台跑）
python D:\DSH\kindle-jb\opds_server.py D:\DSH\kindle-jb\out 8080
```

KOReader 里：**☰ 主菜单 → 搜索（放大镜）→ OPDS catalog → 添加目录**，填
`http://<本机IP>:8080/opds`（本机 WLAN 为 `<你的电脑局域网IP>`），即可浏览并下载书库里的书。

> 成书放进 `-LibraryDir` 就等于"已入库"——OPDS 每次请求都会重新扫描该目录，**无需重启服务**。

若 Kindle 连不上，用**管理员** PowerShell 放行入站端口：

```powershell
New-NetFirewallRule -DisplayName "DSH-OPDS-8080-In" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Any
```

## 三点五、目录约定：`markdown` 文件夹

本机约定：Kindle 上用 **`markdown` 文件夹**集中放要读的文档。两条通道的处理方式不同：

| 通道 | 能否指定落到 `markdown` |
|---|---|
| **USB（`-Push`）** | ✅ 能。`-DestDir` 留空时**自动识别**设备上的 `markdown`（根目录或 documents 下均可），找不到才回退 `documents\Books` |
| **Wi-Fi / OPDS** | ❌ **服务端决定不了**。OPDS 只能决定书名和文件，保存位置由 KOReader 端选择 |

**OPDS 通道下发到 `markdown` 的两种做法：**

1. 下载时若 KOReader 弹出目录选择，直接选 `/mnt/us/markdown`；
2. 若它不问、直接存到别处：在 KOReader 的**文件浏览器**里长按刚下载的 `.epub` → 选 **复制/移动（Copy / Move）** → 导航到 `/mnt/us/markdown` → 粘贴。

> 注意：`.md` 原文件不要指望 KOReader 排版——它没有 Markdown 渲染，表格会退化成纯文本。**读用 EPUB，存档才放 `.md`。**
## 三点六、内嵌中文字体（默认开启）

墨水屏上细笔画字体（宋/明体类）会显得发灰，而**字重和字体选择存在阅读器的 `.sdr` 里、优先级高于书内样式**，所以只调 CSS 治不好。

解法：把字体**嵌进书里**。

| 项目 | 说明 |
|---|---|
| 字体 | Noto Sans SC（SIL OFL 开源许可，允许嵌入） |
| 字重 | 常规用 **Medium**（比 Regular 扎实）、粗体用 Bold |
| 体积 | 按 EPUB 实际用到的字形**子集化**：8.1MB → 约 220KB/档，一本书最终约 230–410KB |
| 实现 | `embed_font.py`：收集正文字符 → `fontTools.subset` 裁剪 → 写入 `EPUB/fonts/` → CSS 末尾追加 `@font-face` → OPF 清单登记 |
| 关闭 | `-EmbedFont:$false` |

**使用前提**：KOReader 里 字体设置 → 字体 → 选「文档内嵌字体 / Document font」，并确认「内嵌字体」开关打开。
## 四、三个转换引擎（同一份文档实测对比）

| 引擎 | 依赖 | 字节 | 目录项 | 表格保真 | 适用 |
|---|---|---|---|---|---|
| **pandoc**（默认） | `pylib` 内置 pandoc 3.9 | 34,937 | 32 | 21 表 / 115 th / 151 行 | 语法最全：图片、脚注、YAML、数学 |
| lib | markdown + ebooklib | 31,630 | 15 | 同上 | 想用标准 Python 生态时 |
| builtin | **无**（纯标准库） | 31,675 | 31 | 同上 | 完全离线、无第三方依赖 |

*三种引擎的表格保真度完全一致；默认用 pandoc 是因为它语法覆盖最全且目录深度（`--toc-depth=3`）与本项目内置引擎持平。*
*强制离线：`-Engine builtin`（`md2epub.py` 只用 Python 标准库，不联网、不依赖 pylib）。*

**排版**（`eink.css`，三个引擎共用）：表格 0.78em + `table-layout:fixed` + 强制断行（宽表不溢出）；
代码块 `pre-wrap` 自动换行；正文行高 1.65、中文两端对齐；章标题带下边框。

## 五、常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `未检测到已就绪的 Kindle 盘符` | 设备侧没把存储交接出来（常见于 KOReader 运行中）。先退出 KOReader，重启 Kindle，等主界面加载完再插线。此时书已入库，可走 OPDS |
| Kindle 读不到 `E:\`，但 USB 层已识别 | 同上。判定依据：`cmd dir E:` 返回 "The device is not ready." |
| **正文颜色偏浅、标题却正常** | 根因：常规字重的细笔画字体在墨水屏上发灰；且字体设置存在阅读器的 `.sdr` 里，优先级高于书内样式。**本项目已内置解法**：`-EmbedFont`（默认开）把 Noto Sans SC Medium 按字形子集化后嵌进 EPUB。**仍需在 KOReader 里做一步**：字体设置 → 字体 → 选「文档内嵌字体 / Document font」，否则旧字体选择会盖住内嵌字体。嫌过黑可换常规字重：`-FontRegular` 指向 Noto Sans SC 的 Regular 版 |
| 中文显示成方块 | KOReader 缺中文字体。把中文字体放进 Kindle 的 `E:\fonts`，KOReader 字体设置里选它 |
| `pip` 报 Permission denied | 系统临时目录不可写。流水线已自动把 pip 临时目录指到工作区内 |
| 同名 md 的 H1 相同 | 已处理：单文件模式用**源文件名**命名（稳定可覆盖），仍冲突时自动加 `_2` 后缀 |

## 六、文件清单

| 文件 | 作用 |
|---|---|
| `publish-to-kindle.ps1` | **主入口**：工具链自检/安装 → 转换 → 推送 → 校验 |
| `md2epub.py` | 内置引擎（零依赖，EPUB3 + nav/NCX 双目录） |
| `md2epub_lib.py` | markdown + ebooklib 引擎 |
| `eink.css` | 墨水屏排版样式（三引擎共用） |
| `opds_server.py` | 本地 OPDS 书库服务（Wi-Fi 传书） |
| `Fill-Kindle.ps1` | 越狱前用的存储填充/回收脚本 |
| `PLAN.md` | 越狱完成报告 |
| `out/` | 书库（成书输出 + OPDS 服务目录） |
| `pylib/` | 自动安装的第三方依赖（pandoc / markdown / ebooklib / lxml） |
| `backup/` | 越狱前的 Kindle 数据备份 |
| `_dev/` | 开发期的一次性分析脚本与校验报告 |





