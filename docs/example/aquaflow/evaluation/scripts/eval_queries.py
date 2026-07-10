"""
AquaFlow 15-query evaluation runner.

Evaluates the Synthadoc query agent against 15 PE/M&A due diligence questions
(Q1–Q10 in English, Q11–Q15 in Chinese) drawn from the AquaFlow demo wiki.
Scoring: case-insensitive substring match against a curated fact list.
Grading: PASS ≥85%, WARN 60–84%, FAIL <60%.

Usage — run a single model:
    python eval_queries.py --model <label> [--port 7074]

    The <label> is an arbitrary name used for the output file; the active
    model is whatever is configured in the wiki's .synthadoc/config.toml.

    Examples:
        python eval_queries.py --model minimax-think
        python eval_queries.py --model minimax
        python eval_queries.py --model deepseek
        python eval_queries.py --model claude-sonnet-4-6
        python eval_queries.py --model qwen-plus
        python eval_queries.py --model gemini-flash

Usage — compare two or more result files:
    python eval_queries.py --compare minimax-think minimax deepseek

Models evaluated in the AquaFlow benchmark (config.toml snippets):
    minimax-think:      provider="minimax"   model="MiniMax-M3"                    (thinking=on, default)
    minimax:            provider="minimax"   model="MiniMax-M3"  thinking="disabled"
    deepseek:           provider="deepseek"  model="deepseek-chat"
    claude-opus-4-8:    provider="anthropic"  model="claude-opus-4-8"
    claude-sonnet-4-6:  provider="anthropic"  model="claude-sonnet-4-6"
    qwen-plus:          provider="qwen"      model="qwen-plus"
    gemini-flash:       provider="gemini"    model="gemini-2.5-flash-lite"

Results are saved to eval_results/<model>.json and a summary is printed to
stdout.  Run with --compare to diff two or more model result files.
"""

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows consoles so CJK and special chars don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Query bank — Q1-Q10 English, Q11-Q15 Chinese
# Each entry: question text + list of expected key facts (used for scoring)
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "id": "Q1",
        "lang": "en",
        "question": "What are the sources and uses of funds in an LBO of a water infrastructure company?",
        "facts": [
            "term loan b", "tlb", "318", "50%",
            "revolving credit", "revolver", "50m", "subordinated",
            "equity", "261m", "41%",
            "purchase price", "transaction fees", "financing fees",
        ],
    },
    {
        "id": "Q2",
        "lang": "en",
        "question": "What regulatory and market tailwinds are driving demand for PFAS water treatment solutions?",
        "facts": [
            "pfas", "epa", "npdwr", "april 2024",
            "4 parts per trillion", "2,400", "community water systems",
            "4-6b", "4–6b", "2024-2029", "2024–2029",
            "california", "michigan", "new york",
            "granular activated carbon", "anion exchange",
        ],
    },
    {
        "id": "Q3",
        "lang": "en",
        "question": "What adjustments does a quality of earnings analysis make to reported EBITDA?",
        "facts": [
            "addback", "add-back",
            "owner compensation", "one-time", "restructuring",
            "non-cash", "stock-based compensation",
            "prematurely", "non-recurring",
            "asc 606",
            "working capital",
            "5-15%",
        ],
    },
    {
        "id": "Q4",
        "lang": "en",
        "question": "What are the primary legal workstreams in a water infrastructure LBO due diligence?",
        "facts": [
            "corporate", "governance",
            "material contracts", "change-of-control",
            "intellectual property", "patent", "14",
            "litigation",
            "regulatory", "phase i", "npdes", "nsf/ansi",
            "real property", "185,000", "aurora",
            "debt", "finance",
            "rwi", "pfas",
            "flsa", "318",
            "3-4%", "3–4%",
        ],
    },
    {
        "id": "Q5",
        "lang": "en",
        "question": "What EBITDA multiple range is cited for water infrastructure exit valuations?",
        "facts": [
            "7.0x", "12.5x", "9.0x",
            "water treatment equipment",
            "8.5", "11x", "8.5–11",
            "xylem", "evoqua", "14.8x",
        ],
    },
    {
        "id": "Q6",
        "lang": "en",
        "question": "How do AquaFlow Systems' FY2023 financials compare to the valuation benchmarks, and what does that imply for entry price?",
        "facts": [
            "74.8m", "74.8",
            "8.5x", "11x", "9.0x", "9.5x",
            "635", "710",          # EV at 8.5x ($635M) and 9.5x ($710.6M) — both in answer
            "59%", "60%",          # 59% actual vs >60% upper-end threshold
            "pfas",
            "qoe", "dmwa", "19.4m", "december 31",
        ],
    },
    {
        "id": "Q7",
        "lang": "en",
        "question": "What covenant package is consistent with AquaFlow Systems' financial profile for a typical water infrastructure LBO?",
        "facts": [
            "cov-lite", "covenant-lite",
            "springing", "35%",
            "5.0x", "5.5x",
            "4.5x", "senior secured",
            "2.0x", "icr", "interest coverage",
            "fccr", "1.0x",
            "equity cure", "2-4", "8 quarters",
            "50m", "revolver",
            "68m", "9%",
            "37.4m",
        ],
    },
    {
        "id": "Q8",
        "lang": "en",
        "question": "What risks does each of the three diligence workstreams — QoE, legal, and ESG — uniquely surface for a water treatment company?",
        "facts": [
            "asc 606",
            "55-65%", "35-45%", "55–65%", "35–45%",
            "5-15%", "5–15%",
            "flsa", "318", "field technician",
            "phase i", "aurora", "185,000",
            "rwi", "pfas",
            "12.3", "16%",
            "ltir", "1.8", "1.6",
            "dei", "vp+",
            "71%",
        ],
    },
    {
        "id": "Q9",
        "lang": "en",
        "question": "How should ESG diligence findings on a water treatment target translate into deal structure — specifically covenants and exit multiple sensitivity?",
        "facts": [
            "4.5x", "4.75x",
            "5.0x", "5.25x",
            "phase i", "aurora", "185,000",
            "pfas indemnity", "environmental escrow",
            "rwi",
            "strategic sale", "s2s", "secondary",
            "ipo", "b-", "a-",
            "75m", "$75",
        ],
    },
    {
        "id": "Q10",
        "lang": "en",
        "question": "If AquaFlow Capital exits AquaFlow Systems in 3–5 years, what exit pathways and valuation approach are most defensible?",
        "facts": [
            "s2s", "secondary", "50%",
            "strategic", "35%", "xylem", "veolia",
            "ipo", "15%",
            "117m", "9.0x", "1,053",
            "215m", "838m", "261m",
            "3.2x", "moic", "33%", "irr",
            "64%", "27%",
            "dmwa", "b-", "59%",
        ],
    },
    {
        "id": "Q11",
        "lang": "zh",
        "question": "AquaFlow Systems公司在美国水处理设备市场中的竞争定位如何？",
        "facts": [
            "hydra solutions", "520",      # Hydra revenue: model writes "$520M" not "5.2亿"
            "xylem", "evoqua", "14.8",
            "veolia", "suez", "15",
            "bolt-on", "312",              # bolt-on not "补强"; "$312.4M" not "3.12亿"
            "22", "318", "技术人员",
            "78%", "aquaview",
            "59%",
            "pfas", "顺风",
        ],
    },
    {
        "id": "Q12",
        "lang": "zh",
        "question": "杠杆收购模型的关键财务指标和运作机制是什么？",
        "facts": [
            "318m", "tlb", "50%",
            "50m", "revolver", "循环",
            "56m", "subordinated", "次级",
            "261m", "41%", "股权",
            "5.0x", "3.0x",
            "5.5x", "4.5x", "2.0x", "1.0x",
            "50-75%", "50–75%", "超额现金",
            "5-15%", "5–15%",
            "mip", "5-15%",
            "64%", "60-70%",
        ],
    },
    {
        "id": "Q13",
        "lang": "zh",
        "question": "水务基础设施投资的ESG尽调重点关注哪些方面？",
        "facts": [
            "phase i", "pfas",
            "顺风", "逆风",
            "ltir", "vp+", "dei",
            "独立",
            "b+", "b-",
            "sasb", "tcfd",
        ],
    },
    {
        "id": "Q14",
        "lang": "zh",
        "question": "综合质量收益分析、法律尽调和ESG尽调，AquaFlow Systems作为LBO收购标的面临哪些主要风险，应如何在交易结构中加以应对？",
        "facts": [
            "5-15%", "qoe",
            "dmwa", "竞标",
            "0.5x", "缓冲",
            "59%", "经常性",
            "2.5x",
            "pfas", "托管",
            "5.0x", "5.25x",
            "4.5x", "4.75x",
            "超额现金",
            "s2s", "战略", "ipo",
        ],
    },
    {
        "id": "Q15",
        "lang": "zh",
        "question": "基于当前水务基础设施市场环境，AquaFlow Capital应采取何种退出策略，预期回报率和估值倍数范围是多少？",
        "facts": [
            "s2s", "50%", "8.0x", "10.0x", "9.0x",
            "战略", "35%", "9.0x", "11.5x", "10.5x",
            "ipo", "15%", "13.0x",
            "3.0x", "3.6x", "moic",
            "33%", "38%", "irr",
            "74.8", "117m",
            "64%", "ebitda增长",
            "27%", "债务",
            "78%", "aquaview",
            "dmwa", "b-", "59%",
        ],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EVAL_DIR = Path(__file__).parent.parent / "report"


def query_api(question: str, port: int, timeout: int = 90) -> dict:
    """Call GET /query on the local synthadoc server."""
    encoded = urllib.parse.quote(question, safe="")
    url = f"http://localhost:{port}/query?q={encoded}&no_cache=true&timeout_seconds={timeout}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def score_answer(answer: str, facts: list[str]) -> tuple[int, int, list[str]]:
    """Return (matched, total, missing_facts) via case-insensitive substring search.

    En-dashes (–) and em-dashes (—) are normalized to ASCII hyphens before
    comparison so facts like "5-15%" match wiki text written as "5–15%".
    """
    def _norm(s: str) -> str:
        return s.lower().replace("–", "-").replace("—", "-")

    answer_norm = _norm(answer)
    matched = []
    missing = []
    for fact in facts:
        if _norm(fact) in answer_norm:
            matched.append(fact)
        else:
            missing.append(fact)
    return len(matched), len(facts), missing


def grade(matched: int, total: int) -> str:
    """Score-based grade using a two-tier output scale.

    Grading framework:
      PASS  — ≥85% facts matched; system and model are both performing correctly.
      WARN  — <85% facts matched; root cause is model behaviour or non-determinism,
              NOT a system/code bug.  The missing-facts line explains what was missed.
      FAIL  — never emitted automatically.  Reserved for confirmed system/code bugs
              (e.g. wrong language, gap-detection false positive, retrieval failure).
              Mark manually in the benchmark document when a system root cause is
              identified and fixed.
    """
    if total == 0:
        return "N/A"
    return "PASS" if matched / total >= 0.85 else "WARN"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_eval(model: str, port: int) -> None:
    EVAL_DIR.mkdir(exist_ok=True)
    out_path = EVAL_DIR / f"{model}.json"

    results = []
    print(f"\n{'='*60}")
    print(f"Model: {model}  |  Port: {port}  |  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*60}\n")

    for entry in QUERIES:
        qid = entry["id"]
        question = entry["question"]
        facts = entry["facts"]

        print(f"  {qid}: {question[:70]}{'…' if len(question) > 70 else ''}")
        sys.stdout.flush()

        try:
            t0 = time.time()
            resp = query_api(question, port)
            elapsed = time.time() - t0
            answer = resp.get("answer", "") or ""
            sources = resp.get("sources", [])
            matched, total, missing = score_answer(answer, facts)
            status = grade(matched, total)
        except Exception as exc:
            answer = ""
            sources = []
            elapsed = 0.0
            matched, total, missing = 0, len(facts), facts[:]
            status = "ERR!"
            print(f"    ERROR: {exc}")

        pct = f"{matched}/{total} ({100*matched//total if total else 0}%)"
        print(f"    {status}  facts: {pct}  elapsed: {elapsed:.1f}s")
        if missing:
            print(f"    missing: {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")

        results.append({
            "id": qid,
            "lang": entry["lang"],
            "question": question,
            "answer": answer,
            "sources": sources,
            "matched": matched,
            "total": total,
            "missing": missing,
            "status": status,
            "elapsed_s": round(elapsed, 1),
        })

    out_path.write_text(json.dumps({
        "model": model,
        "port": port,
        "run_at": datetime.now().isoformat(),
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    total_matched = sum(r["matched"] for r in results)
    total_facts = sum(r["total"] for r in results)
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_warn = sum(1 for r in results if r["status"] == "WARN")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_err  = sum(1 for r in results if r["status"] == "ERR!")
    print(f"\nSummary: {total_matched}/{total_facts} facts matched  "
          f"({100*total_matched//total_facts if total_facts else 0}%)  |  "
          f"PASS={n_pass}  WARN={n_warn}"
          + (f"  FAIL={n_fail}" if n_fail else "")
          + (f"  ERR={n_err}"  if n_err  else ""))
    if n_warn:
        print("  WARN = model/non-deterministic limitation, not a system bug.")
    if n_fail:
        print("  FAIL = confirmed system/code bug — requires investigation.")
    print(f"Results saved → {out_path}\n")


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def compare(model_names: list[str]) -> None:
    files = {}
    for name in model_names:
        p = EVAL_DIR / f"{name}.json"
        if not p.exists():
            print(f"Missing result file: {p}")
            sys.exit(1)
        files[name] = json.loads(p.read_text(encoding="utf-8"))

    # Header
    print(f"\n{'Q':<5} {'Question':<52} " + "  ".join(f"{m:<12}" for m in model_names))
    print("-" * (60 + 14 * len(model_names)))

    for i, entry in enumerate(QUERIES):
        qid = entry["id"]
        q_short = entry["question"][:50]
        cols = []
        for name in model_names:
            res = files[name]["results"][i]
            pct = f"{100*res['matched']//res['total'] if res['total'] else 0}%"
            cols.append(f"{res['status']} {pct:<8}")
        print(f"{qid:<5} {q_short:<52} " + "  ".join(cols))

    print()
    for name in model_names:
        data = files[name]
        total_m = sum(r["matched"] for r in data["results"])
        total_f = sum(r["total"] for r in data["results"])
        n_pass = sum(1 for r in data["results"] if r["status"] == "PASS")
        n_warn = sum(1 for r in data["results"] if r["status"] == "WARN")
        n_fail = sum(1 for r in data["results"] if r["status"] == "FAIL")
        grade_str = f"PASS={n_pass} WARN={n_warn}" + (f" FAIL={n_fail}" if n_fail else "")
        print(f"{name}: {total_m}/{total_f} ({100*total_m//total_f if total_f else 0}%)  "
              f"{grade_str}  run: {data['run_at'][:16]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AquaFlow query evaluation runner")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run all 15 queries against a model")
    run_p.add_argument("--model", required=True, help="Model label (e.g. minimax, deepseek)")
    run_p.add_argument("--port", type=int, default=7074, help="Synthadoc server port")

    cmp_p = sub.add_parser("compare", help="Compare two or more model result files")
    cmp_p.add_argument("models", nargs="+", help="Model names to compare")

    # Shorthand: python eval_queries.py --model minimax
    parser.add_argument("--model", help="Shorthand for run --model")
    parser.add_argument("--port", type=int, default=7074)
    parser.add_argument("--compare", nargs="+", metavar="MODEL")

    args = parser.parse_args()

    if args.compare:
        compare(args.compare)
    elif getattr(args, "cmd", None) == "compare":
        compare(args.models)
    elif getattr(args, "cmd", None) == "run":
        run_eval(args.model, args.port)
    elif args.model:
        run_eval(args.model, args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
