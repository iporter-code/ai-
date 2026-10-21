# docs 目录说明

## 交付物（4 个）

- `实验报告.pdf`：最终实验报告，4 页 A4，**6 图 5 表**：系统架构、指标对比、逐题延迟、真实运行界面、Gradio 界面、四条命令的真实输出；含评测结论、两问分析、AI 错误清单；
- `architecture.png`：系统架构图，由 `scripts/make_architecture.py` 生成；
- `演示录屏.mp4`：3 分 21 秒演示，含 2 道陷阱题当场拒答（5.6MB，随仓库提供）；
- `演示录屏脚本.md`：分镜、时间轴、制作方式与复现命令。

## 辅助文件

- `实验报告.md`：报告源文件。改完用 `python scripts/build_report_pdf_rl.py` 重新导出 `实验报告.pdf`；
- `AI错误清单.md`：AI 生成代码的 6 条错误与修正记录（报告 §5 的完整版）；
- `demo_run.log` / `demo_run.json`：演示视频的原始运行日志（问题、答案、引用、首 token、Top-4 分数），
  由 `scripts/record_demo.py` 生成，可用来核对视频里的每个字符；
- `report_shots/`：报告插图。`fig_screen.png` 由 `scripts/make_report_figures.py` 生成，
  `fig_metrics.png` / `fig_latency.png` 由 `scripts/make_report_charts.py` 从 `eval/results` 现算，
  `fig_cmds.png` 由 `scripts/make_report_shots.py` 现场执行四条命令后渲染，
  `ui.png` 是 `python -m app.ui` 的真实截图。

## internal/

`internal/` 存放自查材料（评审意见原文、核查记录、旧版无截图报告），已在 `.gitignore` 中排除，**不属于交付内容**。
