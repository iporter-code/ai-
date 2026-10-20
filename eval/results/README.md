# 评测结果目录

本目录是最终 **20 题**评测结果：

- `results_bm25.csv` / `results_vector.csv`：逐题回答、引用、Top-3 命中和人工 `correct` 标注；
- `raw_bm25.jsonl` / `raw_vector.jsonl`：含完整检索片段、分数、首 token 与总延迟；
- `metrics.md`：四项指标、端到端延迟和分题型统计。

复现：

```bash
python scripts/evaluate.py --mode both --sleep 32
# 在 CSV 的 correct 列填 1/0
python scripts/score.py eval/results/results_bm25.csv eval/results/results_vector.csv
```

最终指标：BM25 正确率 100%、向量 95%；幻觉率均 0%；Top-3 命中 86.7% / 93.3%；首 token 13.36 s / 10.96 s；引用文档准确率均 100%（15/15 有答案题有引用，q02 的错引已重映射、q04/q15 的多余引用已删除）。
