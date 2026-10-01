<#
.SYNOPSIS
    把项目里的 Markdown 转成 EPUB，并推送到 Kindle（或本地 OPDS 书库）。

.DESCRIPTION
    一条命令完成：工具链自检/安装 -> Markdown 转 EPUB -> 推送。
    默认把成书放进书库目录，该目录同时被本地 OPDS 服务器提供，
    Kindle 上 KOReader 可通过 Wi-Fi 直接下载；若 Kindle 已挂载为盘符，则直接拷入。

.EXAMPLE
    .\publish-to-kindle.ps1 -Path .\README.md -Push

.EXAMPLE
    # 把整个项目里的 md 合并成一本，推到 Kindle 的 documents\Books
    .\publish-to-kindle.ps1 -Path .\docs -Recurse -Merge -Title "项目文档" -Push

.EXAMPLE
    # 首次使用：安装/补齐工具链（pandoc + ebooklib + markdown）
    .\publish-to-kindle.ps1 -Bootstrap -Path .\README.md

.NOTES
    引擎：auto(默认) 有 pandoc 用 pandoc，否则用内置零依赖引擎；
          pandoc/lib/builtin 可强制指定。
#>
[CmdletBinding()]
param(
    # Markdown 文件或目录（默认当前目录）
    [string[]]$Path,

    # 目录时递归查找
    [switch]$Recurse,

    # 多个文件合并成一本书（否则每个文件一本）
    [switch]$Merge,

# 输出文件名（不含扩展名）。留空则：单文件用源文件名、合并用 -Title
    [string]$Name = '',
    # 书名（默认取文档首个 H1，其次取文件名/目录名）
    [string]$Title,

    # 作者
    [string]$Author = '本地生成',

    # 成书输出目录（同时是 OPDS 书库目录）
    [string]$LibraryDir = 'D:\DSH\kindle-jb\out',

    # Kindle 内的目标子目录；留空则自动识别（优先设备上的 markdown 文件夹）
    [string]$DestDir = '',

# 嵌入裁剪后的中文字体（默认开启）：不依赖阅读器设置，正文更黑更清晰
    [bool]$EmbedFont = $true,

    # 常规字重字体（默认用 Medium 档，墨水屏上笔画更扎实）
    [string]$FontRegular = 'C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf',

    # 粗体字体
    [string]$FontBold = 'C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf',
    [ValidateSet('auto', 'pandoc', 'lib', 'builtin')]
    [string]$Engine = 'auto',

    # 缺工具时自动安装到本目录的 pylib（免管理员）
    [switch]$Bootstrap,

    # 尝试直接拷贝到已挂载的 Kindle
    [switch]$Push,

    # 推送后安全弹出
    [switch]$Eject,

    # 完成后打开书库目录
    [switch]$Open
)

$ErrorActionPreference = 'Stop'
$Root     = $PSScriptRoot
$Pylib    = Join-Path $Root 'pylib'
$PipTmp   = Join-Path $Root '.pip-tmp'
$Css      = Join-Path $Root 'eink.css'
$PandocExe= Join-Path $Pylib 'pypandoc\files\pandoc.exe'
$EngineBuiltin = Join-Path $Root 'md2epub.py'
$EngineLib     = Join-Path $Root 'md2epub_lib.py'

function Write-Head($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }

# ---------- 工具链 ----------
function Get-ToolState {
    $py = $false
    try { $null = & python --version 2>&1; if ($LASTEXITCODE -eq 0) { $py = $true } } catch { }
    [pscustomobject]@{
        Python = $py
        Pandoc = (Test-Path -LiteralPath $PandocExe)
        Libs   = ((Test-Path -LiteralPath (Join-Path $Pylib 'markdown')) -and
                  (Test-Path -LiteralPath (Join-Path $Pylib 'ebooklib')))
    }
}

function Install-Tools {
    Write-Head "安装工具链到 $Pylib"
    New-Item -ItemType Directory -Force -Path $Pylib, $PipTmp | Out-Null
    # pip 的解包临时目录必须放在可写位置（沙箱/受限环境下系统 TEMP 会拒绝访问）
    $env:TMP = $PipTmp; $env:TEMP = $PipTmp
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    # pandoc 走 pypandoc_binary（自带 pandoc.exe），免管理员、免 winget
    & python -m pip install --target $Pylib --upgrade --no-warn-script-location `
        markdown ebooklib pypandoc_binary
    if ($LASTEXITCODE -ne 0) { throw "工具链安装失败（检查网络/pip）" }
}

# ---------- 引擎 ----------
function Resolve-Engine([string]$Want) {
    $st = Get-ToolState
    if ($Want -eq 'pandoc') {
        if (-not $st.Pandoc) { throw "指定了 pandoc，但未找到 $PandocExe（先跑 -Bootstrap）" }
        return 'pandoc'
    }
    if ($Want -eq 'lib') {
        if (-not $st.Libs) { throw "指定了 lib 引擎，但 pylib 缺 markdown/ebooklib（先跑 -Bootstrap）" }
        return 'lib'
    }
    if ($Want -eq 'builtin') { return 'builtin' }
    if ($st.Pandoc) { return 'pandoc' }
    return 'builtin'
}

function Get-DocTitle([string]$file) {
    try {
        $line = Get-Content -LiteralPath $file -Encoding UTF8 -TotalCount 200 |
                Where-Object { $_ -match '^#\s+\S' } | Select-Object -First 1
        if ($line) { return ($line -replace '^#\s+', '').Trim().TrimEnd('#').Trim() }
    } catch { }
    return [System.IO.Path]::GetFileNameWithoutExtension($file)
}

function Invoke-EmbedFont {
    # 把字体裁剪成"本书实际用到的字形"再嵌入，8MB 字体 -> 几百 KB
    param([string]$OutFile)
    $tool = Join-Path $Root 'embed_font.py'
    if (-not (Test-Path -LiteralPath $tool)) { Write-Warning "缺少 embed_font.py，跳过字体嵌入"; return }
    if (-not (Test-Path -LiteralPath $FontRegular)) { Write-Warning "字体不存在，跳过: $FontRegular"; return }
    $a = @($OutFile, '--regular', $FontRegular, '--family', 'KindleCN')
    if ($FontBold -and (Test-Path -LiteralPath $FontBold)) { $a += @('--bold', $FontBold) }
    $o = & python $tool @a 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Warning "字体嵌入失败（保留未嵌入版本）：$($o -join ' ')" }
}

function Get-SafeName([string]$s, [string]$fallback) {
    $n = ($s -replace '[\\/:*?"<>|\r\n\t]', '_').Trim().TrimEnd('.')
    if ($n.Length -gt 48) { $n = $n.Substring(0, 48).Trim().TrimEnd('.') }
    if (-not $n) { $n = $fallback }
    return $n
}

function Invoke-Convert {
    param([string[]]$Files, [string]$OutFile, [string]$Title, [string]$Author, [string]$Engine)

    if ($Engine -eq 'pandoc') {
        $a = @()
        foreach ($f in $Files) { $a += $f }
        $a += @('-o', $OutFile, '--toc', '--toc-depth=3', '--split-level=2', '--css', $Css,
                '--metadata', "title=$Title", '--metadata', 'lang=zh-CN', '--metadata', "author=$Author")
        $o = & $PandocExe @a 2>&1
        if ($LASTEXITCODE -ne 0) { throw "pandoc 转换失败：`n$($o -join "`n")" }
        return
    }

    if ($Engine -eq 'lib') {
        $a = @()
        foreach ($f in $Files) { $a += $f }
        $a += @('-o', $OutFile, '-t', $Title, '-a', $Author)
        $o = & python $EngineLib @a 2>&1
        if ($LASTEXITCODE -ne 0) { throw "lib 引擎转换失败：`n$($o -join "`n")" }
        return
    }

    # builtin：单文件直接转；多文件先合成临时 md（各文件 H1 变章标题，其余标题降一级）
    $inFile = $Files[0]
    $tmp = $null
    if ($Files.Count -gt 1) {
        $tmpDir = Join-Path $Root '.tmp'
        New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
        $tmp = Join-Path $tmpDir ("merge_{0}.md" -f ([guid]::NewGuid().ToString('N')))
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.AppendLine("# $Title")
        [void]$sb.AppendLine("")
        foreach ($f in $Files) {
            $ft = Get-DocTitle $f
            [void]$sb.AppendLine("## $ft")
            [void]$sb.AppendLine("")
            foreach ($l in (Get-Content -LiteralPath $f -Encoding UTF8)) {
                if ($l -match '^(#{1,5})\s') { [void]$sb.AppendLine('#' + $l) } else { [void]$sb.AppendLine($l) }
            }
            [void]$sb.AppendLine("")
        }
        Set-Content -LiteralPath $tmp -Value $sb.ToString() -Encoding utf8
        $inFile = $tmp
    }
    try {
        $o = & python $EngineBuiltin $inFile $OutFile $Author 2>&1
        if ($LASTEXITCODE -ne 0) { throw "builtin 引擎转换失败：`n$($o -join "`n")" }
    } finally {
        if ($tmp -and (Test-Path -LiteralPath $tmp)) { Remove-Item -LiteralPath $tmp -Force }
    }
}

# ---------- 推送 ----------
function Resolve-DestDir {
    # 未显式指定 -DestDir 时：优先用设备上名为 markdown 的文件夹（用户约定），
    # 其次回退到 documents\Books，最后回退到根目录。
    param([string]$Root)
    foreach ($cand in @('markdown', 'documents\markdown', 'documents\Books')) {
        if (Test-Path -LiteralPath (Join-Path $Root $cand)) { return $cand }
    }
    return 'documents'
}

function Get-KindleDrive {
    foreach ($i in 65..90) {
        $r = [string][char]$i + ':\'
        $di = $null
        try { $di = New-Object System.IO.DriveInfo $r } catch { continue }
        if ($di.DriveType -ne 'Removable') { continue }
        $ready = $false; try { $ready = $di.IsReady } catch { }
        if (-not $ready) { continue }
        if ((Test-Path -LiteralPath ($r + 'system')) -and (Test-Path -LiteralPath ($r + 'documents'))) { return $di }
    }
    return $null
}

function Remove-KindleSafely {
    param([string]$Letter)
    try {
        $sh = New-Object -ComObject Shell.Application
        $item = $sh.Namespace(17).ParseName("${Letter}:")
        $verb = $item.Verbs() | Where-Object { $_.Name -replace '&','' -match '弹出|Eject' } | Select-Object -First 1
        if ($verb) { $verb.DoIt() }
    } catch { }
}

# ================= 主流程 =================
if (-not $Path -or $Path.Count -eq 0) { $Path = @((Get-Location).Path) }

$st = Get-ToolState
Write-Head "工具链状态"
"python         : $(if($st.Python){'OK'}else{'缺失'})"
"pandoc         : $(if($st.Pandoc){'OK  ' + $PandocExe}else{'缺失'})"
"markdown/ebooklib: $(if($st.Libs){'OK'}else{'缺失'})"

if (-not $st.Python) { throw "未找到 python，无法转换" }
if ((-not $st.Pandoc -or -not $st.Libs) -and $Bootstrap) { Install-Tools; $st = Get-ToolState }

$engine = Resolve-Engine $Engine

# 收集输入
$files = @()
foreach ($p in $Path) {
    if (Test-Path -LiteralPath $p -PathType Container) {
        $files += Get-ChildItem -LiteralPath $p -Filter '*.md' -File -Recurse:$Recurse | Select-Object -ExpandProperty FullName
    } elseif (Test-Path -LiteralPath $p -PathType Leaf) {
        $files += (Resolve-Path -LiteralPath $p).Path
    }
}
$files = $files | Where-Object { $_ -and $_.ToLower().EndsWith('.md') } | Select-Object -Unique
if (-not $files) { throw "没有找到任何 .md 文件：$($Path -join ', ')" }

New-Item -ItemType Directory -Force -Path $LibraryDir | Out-Null

Write-Head "开始转换"
"引擎     : $engine"
"书库目录 : $LibraryDir"
"输入     : $($files.Count) 个 md"
foreach ($f in $files) { "           - $f" }

$jobs = @()
if ($Merge) {
    if (-not $Title) { $Title = Split-Path -Leaf (Resolve-Path -LiteralPath (Split-Path -Parent $files[0])).Path }
    $safe = if ($Name) { Get-SafeName $Name $Name } else { Get-SafeName $Title (Split-Path -Leaf (Split-Path -Parent $files[0])) }
    $jobs += [pscustomobject]@{ Title = $Title; Files = $files; Out = (Join-Path $LibraryDir ($safe + '.epub')) }
} else {
    foreach ($f in $files) {
        $t = Get-DocTitle $f
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($f)
        $safe = if ($Name) { Get-SafeName $Name $Name } else { Get-SafeName $stem $stem }
        $jobs += [pscustomobject]@{ Title = $t; Files = @($f); Out = (Join-Path $LibraryDir ($safe + '.epub')) }
    }
}

# 文件名去重（不同 md 的 H1 可能相同，不能互相覆盖）
$seen = @{}
foreach ($j in $jobs) {
    $cand = $j.Out
    if ($seen.ContainsKey($cand)) {
        $n = 2
        do { $cand = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($j.Out), ([System.IO.Path]::GetFileNameWithoutExtension($j.Out) + "_$n.epub")); $n++ } while ($seen.ContainsKey($cand))
    }
    $seen[$cand] = $true
    $j.Out = $cand
}

$results = @()
foreach ($j in $jobs) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-Convert -Files $j.Files -OutFile $j.Out -Title $j.Title -Author $Author -Engine $engine
    if ($EmbedFont) { Invoke-EmbedFont -OutFile $j.Out }
    $sw.Stop()
    $sz = (Get-Item -LiteralPath $j.Out).Length
    $results += [pscustomobject]@{ 书名 = $j.Title; 文件 = (Split-Path -Leaf $j.Out); KB = [math]::Round($sz/1KB,1); 秒 = [math]::Round($sw.Elapsed.TotalSeconds,1); 推送 = '待定' }
    Write-Host ("  [OK] {0}  ({1} KB, {2}s)" -f (Split-Path -Leaf $j.Out), [math]::Round($sz/1KB,1), [math]::Round($sw.Elapsed.TotalSeconds,1)) -ForegroundColor Green
}

# 推送
$kd = Get-KindleDrive
if ($Push) {
    if ($kd) {
        Write-Head "推送到 Kindle $($kd.Name)"
$sub = if ($DestDir) { $DestDir } else { Resolve-DestDir -Root $kd.Name }
        Write-Host "  目标子目录: $sub  $(if (-not $DestDir) { '(自动识别)' } else { '(指定)' })"
        $dest = Join-Path $kd.Name $sub
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        foreach ($r in $results) {
            $src = Join-Path $LibraryDir $r.文件
            $dst = Join-Path $dest $r.文件
            Copy-Item -LiteralPath $src -Destination $dst -Force
            $h1 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
            $h2 = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
            $ok = ($h1 -eq $h2)
            $r.推送 = if ($ok) { '已拷入' } else { '校验失败' }
        }
        if ($Eject) { Remove-KindleSafely -Letter $kd.Name.Substring(0,1) }
    } else {
        Write-Host "  未检测到已就绪的 Kindle 盘符 —— 成书已放入 OPDS 书库，可在 KOReader 里通过 Wi-Fi 下载" -ForegroundColor Yellow
        foreach ($r in $results) { $r.推送 = 'OPDS 可下载' }
    }
} else {
    foreach ($r in $results) { $r.推送 = '仅入库' }
}

Write-Head "结果"
$results | Format-Table -AutoSize | Out-String | Write-Host

"书库目录 : $LibraryDir"
if ($kd -and $Push) {
    "设备目录 : $($kd.Name)$sub"
    "KOReader 路径: 文件浏览器 -> " + ($sub -replace '\\', '/')
} else {
    "KOReader 路径: 文件浏览器 -> documents/Books（或你设备上的 markdown 目录）"
}
Write-Host "OPDS 地址（若 OPDS 服务在跑）: http://<本机IP>:8080/opds" -ForegroundColor DarkGray

if ($Open) { Invoke-Item -LiteralPath $LibraryDir }







