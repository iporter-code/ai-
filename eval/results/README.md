# 评测结果目录

本目录是最终 **20 题 / 32 片段**评测结果：

- `results_bm25.csv` / `results_vector.csv`：逐题回答、引用、Top-3 命中、拒答层和人工 `correct` 标注；
- `raw_bm25.jsonl` / `raw_vector.jsonl`：含完整检索片段、分数、首 token 与总延迟；
- `metrics.md`：四项指标、引用指标、端到端延迟和分题型统计。

复现：

```bash
python scripts/evaluate.py --mode both --sleep 32
# 在 CSV 的 correct 列填 1/0
python scripts/score.py eval/results/results_bm25.csv eval/results/results_vector.csv
```

最终指标：BM25 正确率 90%（18/20）、向量 90%（18/20）；幻觉率 BM25 20%（q17 把作业截止日答成考试日期）、向量 0%；Top-3 命中均 86.7%；首 token 9.76 s / 8.77 s；引用文档准确率均 100%。

q06 BM25、q11 向量曾因接口返回空答案失败，已用同一配置重跑并替换；q17 的 BM25 幻觉保留为失败案例，未用改题或放宽阈值掩盖。`--retrieval-only` 默认写入 `*_retrieval.*`，不会覆盖正式结果。
