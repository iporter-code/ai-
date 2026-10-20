$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'RAG DEMO'
chcp 65001 | Out-Null
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = Join-Path $PWD '.venv\Scripts\python.exe'
mode con: cols=100 lines=36 | Out-Null

function Banner($title) {
  Clear-Host
  Write-Host '======================================================================' -ForegroundColor DarkCyan
  Write-Host "  $title" -ForegroundColor White
  Write-Host '======================================================================' -ForegroundColor DarkCyan
  Write-Host ''
}
function Say($text, $color = 'Gray') {
  Write-Host $text -ForegroundColor $color
}
function Prompt-Cmd($cmd) {
  Write-Host ''
  Write-Host "PS> $cmd" -ForegroundColor Yellow
  Write-Host ''
}

Start-Sleep -Seconds 5

Banner '不瞎编的私有知识库问答助手  ·  真机演示'
Say '一个只依据私有语料回答、带原文引用、资料不足会拒答的 RAG 应用。' 'White'
Say ''
Say '语料：3 个文档（课程笔记 / RAG 实验日记 / Python 环境备忘），约 5.7 千字。'
Say '检索：BM25 与 bge-small-zh 向量检索，命令行和 Web 均可运行时切换。'
Say '生成：Top-4 片段编号后交给大模型，强制 [n] 引用；两道拒答闸门。'
Say ''
Say '下面依次展示：索引信息 -> 文档题（向量）-> 精确命令（BM25）-> 跨段多跳（BM25）-> 两层拒答。' 'Cyan'
Start-Sleep -Seconds 22

Banner '1. 索引与配置：先确认语料、切分和检索参数'
Prompt-Cmd 'python -m app.cli info'
& $py -m app.cli info
Start-Sleep -Seconds 14

Banner '2. 文档题（向量检索）：跨两段证据回答，并给出引用'
Say '问题：作者为什么强调每个项目建独立虚拟环境？上学期遇到什么版本冲突？' 'White'
Start-Sleep -Seconds 4
Prompt-Cmd 'python -m app.cli ask "作者为什么强调每个项目建独立虚拟环境？上学期遇到了什么版本冲突？" --mode vector'
& $py -m app.cli ask '作者为什么强调每个项目建独立虚拟环境？上学期遇到了什么版本冲突？' --mode vector
Say ''
Say '看点：答案引用 [1][2]，下方列出文档名、片段号和原文；两段证据分别来自同一 TXT 的片段 6 和 5。' 'Cyan'
Start-Sleep -Seconds 18

Banner '3. 同一切换到 BM25：精确命令和版本号更稳'
Say '问题：PowerShell 激活虚拟环境时报“禁止运行脚本”，应该执行什么命令？' 'White'
Start-Sleep -Seconds 4
Prompt-Cmd 'python -m app.cli ask "PowerShell 激活虚拟环境时报禁止运行脚本，应该执行什么命令？" --mode bm25'
& $py -m app.cli ask 'PowerShell 激活虚拟环境时报禁止运行脚本，应该执行什么命令？' --mode bm25
Say ''
Say '看点：BM25 对 Set-ExecutionPolicy 这种精确串命中更稳；同一套 answer_question，只改了 --mode。' 'Cyan'
Start-Sleep -Seconds 14

Banner '3.5 跨段多跳（BM25）：两篇文档、两个弱点、两组命中率'
Say '问题：BM25 和向量检索各有什么致命弱点？作者 8 题对比里两者 Top-3 各命中多少？' 'White'
Start-Sleep -Seconds 4
Prompt-Cmd 'python -m app.cli ask "BM25 和向量检索各有什么致命弱点？作者 8 题对比里两者 Top-3 各命中多少？" --mode bm25'
& $py -m app.cli ask 'BM25 和向量检索各有什么致命弱点？作者 8 题对比里两者 Top-3 各命中多少？' --mode bm25
Say ''
Say '看点：答案把课程笔记的“弱点”与实验日记的“6/8、7/8”拼在一起，并给出来源编号。' 'Cyan'
Start-Sleep -Seconds 15

Banner '4. 陷阱题 A：语料根本没有 Chroma 版本号（生成层拒答）'
Say 'BM25 仍会检索到“chroma”相关片段，闸门放行；由大模型判断资料不足后拒答。' 'White'
Start-Sleep -Seconds 3
Prompt-Cmd 'python -m app.cli ask "作者实验时安装的 Chroma 版本号是多少？" --mode bm25'
& $py -m app.cli ask '作者实验时安装的 Chroma 版本号是多少？' --mode bm25
Start-Sleep -Seconds 13

Banner '5. 陷阱题 B：语料没有莫干山（检索层直接拒答）'
Say '查询词与语料无关，向量 Top-1 低于 0.40，不调用大模型，0 秒拒答。' 'White'
Start-Sleep -Seconds 3
Prompt-Cmd 'python -m app.cli ask "作者在莫干山徒步时住的是哪家民宿？" --mode vector'
& $py -m app.cli ask '作者在莫干山徒步时住的是哪家民宿？' --mode vector
Start-Sleep -Seconds 12

Banner '6. 结果与结论'
Say '20 题正式评测（10 文档 + 5 陷阱 + 5 多跳）：' 'White'
Say ''
Say '  BM25    : 正确率  90%  | 幻觉率 20% | Top-3 命中 86.7% | 首 token 9.76 s'
Say '  向量检索: 正确率  90%  | 幻觉率  0% | Top-3 命中 86.7% | 首 token 8.77 s'
Say ''
Say '结论：' 'Cyan'
Say '1) 检索负责找证据，生成负责用证据，评测负责证明它没有瞎编；'
Say '2) 高检索命中不等于高正确率：q11 两套检索都答错，q17 还把作业截止日当成考试日期；'
Say '3) 拒答要两层：分数闸门挡明显域外问题，生成约束挡“词面相关但答不了”的陷阱。'
Say ''
Say '录制结束。完整代码、20 题 CSV/JSONL、metrics.md 和实验报告都在仓库中。' 'Gray'
Start-Sleep -Seconds 28
