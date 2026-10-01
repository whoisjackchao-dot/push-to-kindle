---
name: push-to-kindle
description: 把 Markdown 转成 EPUB 并推送到 Kindle 阅读。触发：/push-to-kindle、“推到 kindle”、“把 md 发到 kindle”、“推送书籍到设备”、“生成 kindle 电子书”。默认嵌入中文字体、自动识别设备上的 markdown 目录，USB 不通时回退 Wi-Fi/OPDS。
---

# push-to-kindle — Markdown 转 EPUB 并推送到 Kindle

把项目里的 `.md` 文档变成排版精良（含内嵌中文字体）的 EPUB，推送到 Kindle 的 `markdown` 目录。

## 立即执行

```powershell
# 脚本位置：克隆到别处时改这一行
$K = 'D:\DSH\kindle-jb'

& "$K\publish-to-kindle.ps1" -Path <目标md或目录> -Push
```

常用组合：

```powershell
# 单个文件
& "$K\publish-to-kindle.ps1" -Path D:\DSH\proj\README.md -Push

# 整个项目，每个 md 一本
& "$K\publish-to-kindle.ps1" -Path D:\DSH\proj -Recurse -Push

# 整个项目合并成一本
& "$K\publish-to-kindle.ps1" -Path D:\DSH\proj\docs -Recurse -Merge -Title "项目文档" -Push

# 源文件叫 main.md，想输出成 xxx_main.epub
& "$K\publish-to-kindle.ps1" -Path D:\DSH\proj\main.md -Name proj_main -Push
```

## 参数

| 参数 | 说明 |
|---|---|
| `-Path` | md 文件或目录（默认当前目录），可多个 |
| `-Recurse` | 目录时递归查找 |
| `-Merge` / `-Title` / `-Author` | 多文件合并成一本书 |
| `-Name` | 输出文件名（不含扩展名）；留空则单文件用源文件名 |
| `-LibraryDir` | 成书目录，默认 `D:\DSH\kindle-jb\out`（同时是 OPDS 书库） |
| `-DestDir` | 设备内目标子目录；**留空即自动识别** markdown → documents\markdown → documents\Books → documents |
| `-Push` / `-Eject` | 拷入设备 / 推送后安全弹出 |
| `-EmbedFont` | 是否内嵌字体，**默认开**；`-EmbedFont:$false` 关闭 |
| `-FontRegular` / `-FontBold` | 替换内嵌字体（嫌 Medium 过黑可换 Regular） |
| `-Engine` | `auto`(默认，pandoc) / `lib` / `builtin`（零依赖） |
| `-Bootstrap` | 缺工具时自动 pip 安装到工作区 `pylib` |

## 执行后必须核对并在回复里报告

1. 每本书的**文件名、字节数、推送状态**（已拷入 / 仅入库 / OPDS 可下载）
2. **设备挂载时**：比对设备文件与书库文件的 SHA256 是否一致
3. 最终落盘路径（例如 `E:\markdown\xxx.epub`）
4. 若未推送：说明原因（设备未就绪）并给出两条可选路径（重插设备 / OPDS 下载）

## 两条通道

- **USB（`-Push`）**：设备挂载为盘符时直接拷入并逐文件 SHA256 校验，能进 `markdown` 目录
- **Wi-Fi / OPDS**：成书落进书库目录即“已入库”，服务每次请求重新扫描，无需重启。KOReader：主菜单 → 搜索 → OPDS catalog → 添加 `http://<你的电脑局域网IP>:8080/opds`。注意 **OPDS 下载落在设备根目录**，需在 KOReader 文件浏览器里移动到 `markdown`
- OPDS 服务启动：`python D:\DSH\kindle-jb\opds_server.py D:\DSH\kindle-jb\out 8080`

## 常见故障

| 现象 | 处理 |
|---|---|
| “未检测到已就绪的 Kindle 盘符” | 设备侧没把存储交接给电脑。让用户：**退出 KOReader（☰→退出，不是按 Home）→ 重启 Kindle → 等主界面加载完 → 重插数据线**。此时书已在书库，也可走 OPDS |
| USB 层能看到设备但 `dir E:` 报 “device is not ready” | 同上 |
| 刚插上就查不到盘符 | 挂载有延迟，等 3–5 秒重查再下结论 |
| OPDS 连不上 | 管理员 PowerShell：`New-NetFirewallRule -DisplayName "DSH-OPDS-8080-In" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Any` |
| 打开后正文偏浅 | KOReader：字体设置 → 字体 → 选「文档内嵌字体 / Document font」（`.sdr` 里的旧字体选择会盖住内嵌字体） |
| 中文显示成方块 | 把中文字体放进 `E:\fonts`，KOReader 里选用 |

## 已知边界

- 每次转换都嵌入新的生成时间戳/UUID，**同内容重新构建哈希也会不同**；判断“是否同一版”要按内容或“设备文件 == 刚生成的那份”
- `.sdr` 是 KOReader 的阅读进度/设置，**必须与书同名**；移动或改名时要成对操作
- 移动过文件后 KOReader 的历史记录可能留着旧路径，直接从文件浏览器打开即可

## 参考

- 详细文档：`D:\DSH\kindle-jb\KINDLE-PIPELINE.md`
- 脚本：`publish-to-kindle.ps1`、`md2epub.py`、`md2epub_lib.py`、`embed_font.py`、`eink.css`、`opds_server.py`、`Fill-Kindle.ps1`

