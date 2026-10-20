# 评测集说明

`questions.jsonl` 是本次实验实际使用的 20 题评测集，配比与作业要求一致：

- **10 道文档题**：q01–q10，答案可在单个片段中直接找到；
- **5 道多跳题**：q11–q15，需要两篇文档或相隔较远的两个片段；
- **5 道陷阱题**：q16–q20，语料中没有答案，用于测“不瞎编”。

> 课程明确要求评测集由本人出题。本文件是本次实验使用的成品，提交前请逐题核对，确认你理解并认可每道题与标准答案；如需替换，按下面字段改完后重新跑评测即可。

## 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 唯一编号 |
| `type` | 是 | `doc` / `trap` / `multi_hop` |
| `question` | 是 | 实际提问 |
| `standard_answer` | 是 | 根据原文写的标准答案 |
| `source_docs` | 是 | 答案应来自哪些文件；陷阱题填空数组 |
| `evidence` | 建议 | 从原文原样复制的短句，用于自动算 Top-3 命中；多跳题每篇文档一句 |

## 出题与判定口径

1. 先通读 `data/raw/` 三个文档，从课程笔记、实验日记、环境备忘中各取事实，不照着检索结果反推。
2. 陷阱题先确认语料没有答案：`reranker`、期末考试日期、莫干山民宿、Chroma 版本号、提交邮箱均未出现。
3. `evidence` 必须是原文子串；多跳题要求 Top-3 同时包含所有 evidence 才算命中。
4. `correct` 由人工逐题判定：核心事实正确且没有文档外编造记 1；陷阱题正确拒答记 1；比较题结论错误记 0。
5. 本系统实际给模型 Top-4，但作业指标按 Top-3 计算，因此会出现“Top-3 未命中但答案正确”的情况（q12/q13），报告中单独说明。

## 阈值校准

`calibration.jsonl` 是独立于 20 题评测集的 10 题校准集（5 个可答 + 5 个应拒答），只用于检查 0.40/0.30 的分离度，不参与最终正确率统计：

```bash
python scripts/calibrate.py
```

## 跑评测

```bash
# 只验证检索，不调用大模型
python scripts/evaluate.py --retrieval-only --mode both

# 两种检索各跑 20 题；Pollinations 免费接口用 --sleep 32 可完全避免限流
python scripts/evaluate.py --mode both --sleep 32

# 在 results_*.csv 的 correct 列填 1/0 后计算指标
python scripts/score.py eval/results/results_bm25.csv eval/results/results_vector.csv
```

输出：`eval/results/results_*.csv`、`raw_*.jsonl`、`metrics.md`。CSV/JSONL 保存 `answer`、`raw_answer`、`refusal_reason`、`from_gate`、`source_docs`、`citation_details`，可直接复核拒答层和引用来源。检索-only 写到 `*_retrieval.*`，不会覆盖正式结果。最终结果见 `metrics.md` 和 `docs/实验报告_4页.pdf`。
