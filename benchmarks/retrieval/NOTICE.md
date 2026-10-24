# Data licences

The benchmark code in this directory is licensed under AGPL-3.0-or-later, like
the rest of Synthadoc. The data files in `data/` are licensed separately:

| File | Derived from | Licence |
| --- | --- | --- |
| `data/articles.json` | Titles, revision IDs and categories of English Wikipedia articles | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — © Wikipedia contributors |
| `data/queries.jsonl` | Queries written by an LLM from the text of those Wikipedia revisions | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — derived from Wikipedia; © Wikipedia contributors |
| `data/hotpot.json` | Question IDs from the HotpotQA validation set (distractor setting) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — Yang et al., 2018, [hotpotqa.github.io](https://hotpotqa.github.io/) |
| `data/baseline.json` | Scores computed by this benchmark | AGPL-3.0-or-later |

Article text and HotpotQA paragraphs are **not** stored in this repository.
`python -m benchmarks.retrieval fetch` downloads them from the Wikipedia API
(each article at its pinned revision) and the Hugging Face datasets server
into a local cache. Each article's history and authors are listed at
`https://en.wikipedia.org/w/index.php?oldid=<revid>`.

HotpotQA: Zhilin Yang, Peng Qi, Saizheng Zhang, Yoshua Bengio, William W.
Cohen, Ruslan Salakhutdinov and Christopher D. Manning. *HotpotQA: A Dataset
for Diverse, Explainable Multi-hop Question Answering.* EMNLP 2018.
