# docs 目录说明

## 交付物（4 个）

- `实验报告.pdf`：最终实验报告，4 页 A4，含系统架构图、评测表格与结论、两幅录屏截图、AI 错误清单；
- `architecture.png`：系统架构图，由 `scripts/make_architecture.py` 生成；
- `演示录屏.mp4`：3 分 00 秒真机演示，CLI 操作，含 2 道陷阱题当场拒答；
- `演示录屏脚本.md`：分镜、真实命令与复现方式。

## 辅助文件

- `实验报告.md`：报告源文件。改完用 `python scripts/build_report_pdf_rl.py` 重新导出 `实验报告.pdf`；
- `AI错误清单.md`：AI 生成代码的 6 条错误与修正记录（报告 §5 的完整版）；
- `demo.ps1`：录屏时执行的命令脚本；
- `report_shots/`、`demo_cards/`：报告插图与片尾卡片用的截图。

## internal/

`internal/` 存放自查材料（评审意见原文、核查记录、旧版无截图报告），已在 `.gitignore` 中排除，**不属于交付内容**。
