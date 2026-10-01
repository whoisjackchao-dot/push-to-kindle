# push-to-kindle

把 Markdown 变成排版精良的 EPUB，推到 Kindle 上舒服地读。

既是 **DSH 斜杠命令**（`/push-to-kindle`），也能当普通命令行工具用。

## 特性

- **一条命令走完**：Markdown → EPUB → 推送 → SHA256 校验
- **三种转换引擎**：pandoc（默认）/ markdown+ebooklib / **零依赖**内置引擎
- **内嵌中文字体**：按正文实际用到的字形子集化 Noto Sans SC（8.1MB → 约 220KB/档），
  解决墨水屏上"正文字体偏浅发灰"的老问题，且不依赖阅读器设置
- **两条投递通道**：USB 直拷（自动识别设备的 `markdown` 目录）/ 本地 OPDS 服务（Wi-Fi 下载）
- **零管理员权限**：所有依赖装在仓库内 `pylib/`，不污染系统

## 快速开始

### 1. 克隆

```powershell
git clone https://github.com/whoisjackchao-dot/push-to-kindle D:\DSH\kindle-jb
```

> 脚本默认按 `D:\DSH\kindle-jb` 组织。克隆到别处也行，改 `SKILL.md` 顶部的 `$K` 即可。

### 2. 装成 DSH 斜杠命令（可选）

把 `SKILL.md` 复制到 `<DSH_HOME>\skills\push-to-kindle\SKILL.md`
（Windows 默认 `C:\Users\<你>\.dsh\skills\push-to-kindle\SKILL.md`）。DSH **热加载**，不用重启。

### 3. 补齐工具链

```powershell
.\scripts\publish-to-kindle.ps1 -Bootstrap -Path .\README.md
```

会把 pandoc / markdown / ebooklib / fonttools 装进仓库内 `pylib\`（走 PyPI，免管理员）。

### 4. 开始用

```powershell
# 单文件
.\scripts\publish-to-kindle.ps1 -Path D:\proj\README.md -Push

# 整个项目，每个 md 一本
.\scripts\publish-to-kindle.ps1 -Path D:\proj -Recurse -Push

# 整个项目合并成一本
.\scripts\publish-to-kindle.ps1 -Path D:\proj\docs -Recurse -Merge -Title "项目文档" -Push

# 源文件叫 main.md，想输出成 xxx_main.epub
.\scripts\publish-to-kindle.ps1 -Path D:\proj\main.md -Name proj_main -Push
```

装了 skill 之后，在 DSH 里直接：`/push-to-kindle D:\proj`

## 前置条件

| 需要 | 说明 |
|---|---|
| Windows 10/11 | PowerShell 7 优先，5.1 亦可 |
| Python 3.9+ | 需在 PATH 中 |
| Kindle | 已[越狱](https://kindlemodding.org/jailbreaking/)并装好 KOReader |
| 中文字体 | 默认用系统里的 Noto Sans SC；没有就用 `-FontRegular` 指定任意 TTF/OTF，或 `-EmbedFont:$false` 关掉 |

## 参数速查

| 参数 | 说明 |
|---|---|
| `-Path` | md 文件或目录（默认当前目录），可多个 |
| `-Recurse` | 目录时递归查找 |
| `-Merge` / `-Title` / `-Author` | 多个 md 合并成一本书 |
| `-Name` | 输出文件名（不含扩展名）；留空则单文件用源文件名 |
| `-LibraryDir` | 成书目录，默认 `<仓库同级>\out`（同时是 OPDS 书库） |
| `-DestDir` | 设备内子目录；**留空自动识别** `markdown` → `documents\markdown` → `documents\Books` → `documents` |
| `-Push` / `-Eject` | 拷入设备 / 推送后安全弹出 |
| `-EmbedFont` | 是否内嵌字体，**默认开**；`-EmbedFont:$false` 关闭 |
| `-FontRegular` / `-FontBold` | 替换内嵌字体（嫌 Medium 过黑就换 Regular） |
| `-Engine` | `auto`（默认 pandoc）/ `lib` / `builtin` |
| `-Bootstrap` | 缺工具时自动安装到 `pylib\` |

## 两条投递通道

**USB（`-Push`）** —— 设备挂载成盘符时直接拷入并逐文件 SHA256 校验，能进 `markdown` 目录。

**Wi-Fi / OPDS** —— 成书落进书库目录即"已入库"，服务每次请求都重新扫描，无需重启：

```powershell
python .\scripts\opds_server.py .\out 8080
```

KOReader 里：主菜单 → 搜索 → **OPDS catalog** → 添加 `http://<你的电脑局域网IP>:8080/opds`。
注意 OPDS 下载默认落在设备**根目录**，需要在 KOReader 文件浏览器里移动到 `markdown`。

## 目录结构

```
push-to-kindle/
├── SKILL.md                # DSH 斜杠命令定义
├── KINDLE-PIPELINE.md      # 完整技术文档（引擎对比、字体嵌入原理、排错）
├── scripts/
│   ├── publish-to-kindle.ps1   # 主入口：工具链 → 转换 → 推送 → 校验
│   ├── md2epub.py              # 零依赖内置引擎（EPUB3 + nav/NCX 双目录）
│   ├── md2epub_lib.py          # markdown + ebooklib 引擎
│   ├── embed_font.py           # 字体子集化 + 内嵌 + @font-face 注入
│   ├── eink.css                # 墨水屏排版样式（三引擎共用）
│   └── opds_server.py          # 本地 OPDS 书库服务
└── .gitignore
```

## 常见故障

| 现象 | 处理 |
|---|---|
| "未检测到已就绪的 Kindle 盘符" | 设备侧没把存储交接给电脑。**退出 KOReader（☰→退出，不是按 Home）→ 重启 Kindle → 等主界面加载完 → 重插**。书已入书库，也可走 OPDS |
| `dir E:` 报 "device is not ready" | 同上 |
| 刚插上查不到盘符 | 挂载有延迟，等 3–5 秒再查 |
| OPDS 连不上 | 管理员 PowerShell：`New-NetFirewallRule -DisplayName "OPDS-In" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Any` |
| 正文偏浅 | KOReader：字体设置 → 字体 → 选「文档内嵌字体 / Document font」（`.sdr` 里存的旧字体选择会盖住内嵌字体） |
| 中文显示成方块 | 把中文字体放进 Kindle 的 `fonts\` 目录，KOReader 里选用 |

## 说明

- 仓库内**不含任何个人信息**：设备序列号、内网 IP、用户名等已剔除或占位化
- 每次转换都会嵌入新的生成时间戳/UUID，**同内容重新构建哈希也会不同**；判断版本要按内容比对
- `.sdr` 是 KOReader 的阅读进度/设置，**必须与书同名**，移动或改名要成对操作
