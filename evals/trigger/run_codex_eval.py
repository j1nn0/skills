#!/usr/bin/env python3
"""Codex による skill description の選択評価を実行する。"""

import argparse
import json
import random
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def read_skill_metadata(skill_dir):
    """SKILL.md の name と description を返す。"""
    lines = (skill_dir / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{skill_dir / 'SKILL.md'} に YAML front matter がない")

    front_matter = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        front_matter.append(line)
    else:
        raise ValueError(f"{skill_dir / 'SKILL.md'} の YAML front matter が閉じられていない")

    name = ""
    description = ""
    index = 0
    while index < len(front_matter):
        line = front_matter[index]
        if line.startswith("name:"):
            name = line.removeprefix("name:").strip().strip("\"'")
        elif line.startswith("description:"):
            value = line.removeprefix("description:").strip()
            if value in {">", "|", ">-", "|-"}:
                continuation = []
                index += 1
                while index < len(front_matter) and front_matter[index].startswith(("  ", "\t")):
                    continuation.append(front_matter[index].strip())
                    index += 1
                description = " ".join(continuation)
                continue
            description = value.strip("\"'")
        index += 1
    if not name or not description:
        raise ValueError(f"{skill_dir / 'SKILL.md'} に name または description がない")
    return name, description


def response_schema(query_count):
    return {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {"type": "boolean"},
                "minItems": query_count,
                "maxItems": query_count,
            }
        },
        "required": ["decisions"],
        "additionalProperties": False,
    }


def build_prompt(name, description, queries):
    requests = "\n".join(f"{index + 1}. {query}" for index, query in enumerate(queries))
    return f"""You are classifying whether Codex should consult one candidate skill before responding.

Candidate skill name: {name}
Candidate skill description: {description}

User requests, in order:
{requests}

Do not perform any request and do not inspect files. Decide only whether the candidate skill is relevant enough to consult before responding. Return true only when the skill's described workflow would materially help with that request. Return one boolean decision for every request in the same order."""


def evaluate_batch(queries, name, description, model, workspace):
    """独立した Codex セッションで全ケースを一括判定する。"""
    with tempfile.TemporaryDirectory(prefix="codex-trigger-eval-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        schema_path = temporary_path / "schema.json"
        output_path = temporary_path / "response.json"
        schema_path.write_text(json.dumps(response_schema(len(queries))), encoding="utf-8")

        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-c",
            'model_reasoning_effort="low"',
            "--model",
            model,
            "-",
        ]
        result = subprocess.run(
            command,
            input=build_prompt(name, description, queries),
            text=True,
            capture_output=True,
            cwd=workspace,
            timeout=180,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return [{"triggered": None, "error": error}] * len(queries)
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            decisions = payload["decisions"]
            if len(decisions) != len(queries) or not all(isinstance(decision, bool) for decision in decisions):
                raise ValueError("decisions の件数または値が不正")
            return [{"triggered": decision, "error": None} for decision in decisions]
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
            return [{"triggered": None, "error": f"Codex の出力を読めない: {error}"}] * len(queries)
        except ValueError as error:
            return [{"triggered": None, "error": f"Codex の出力が不正: {error}"}] * len(queries)


def summarize(item, runs, threshold):
    successful = [run["triggered"] for run in runs if run["triggered"] is not None]
    trigger_rate = sum(successful) / len(successful) if successful else None
    selected = trigger_rate is not None and trigger_rate >= threshold
    return {
        "query": item["query"],
        "should_trigger": item["should_trigger"],
        "runs": runs,
        "successful_runs": len(successful),
        "trigger_rate": trigger_rate,
        "selected": selected,
        "pass": trigger_rate is not None and selected == item["should_trigger"],
    }


def split_indices(eval_set, holdout, seed=42):
    """should_trigger の比率を保った train/holdout の添字を返す。"""
    randomizer = random.Random(seed)
    positive = [index for index, item in enumerate(eval_set) if item["should_trigger"]]
    negative = [index for index, item in enumerate(eval_set) if not item["should_trigger"]]
    randomizer.shuffle(positive)
    randomizer.shuffle(negative)
    test_positive = positive[: max(1, int(len(positive) * holdout))]
    test_negative = negative[: max(1, int(len(negative) * holdout))]
    test_indices = set(test_positive + test_negative)
    train_indices = [index for index in range(len(eval_set)) if index not in test_indices]
    return train_indices, sorted(test_indices)


def summary_for(results, indices):
    selected = [results[index] for index in indices]
    passed = sum(result["pass"] for result in selected)
    return {"passed": passed, "failed": len(selected) - passed, "total": len(selected)}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--skill-path", type=Path, required=True, help="スキルディレクトリ")
    parser.add_argument("--description", help="評価する description。省略時は SKILL.md の値")
    parser.add_argument("--model", default="gpt-5.4-mini", help="Codex モデル (既定: gpt-5.4-mini)")
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--trigger-threshold", type=float, default=0.5)
    parser.add_argument("--holdout", type=float, default=0.4)
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.runs_per_query < 1 or args.max_workers < 1:
        parser.error("--runs-per-query と --max-workers は 1 以上にする")
    if not 0 < args.trigger_threshold <= 1:
        parser.error("--trigger-threshold は 0 より大きく 1 以下にする")
    if not 0 < args.holdout < 1:
        parser.error("--holdout は 0 より大きく 1 未満にする")
    return args


def main():
    args = parse_args()
    name, source_description = read_skill_metadata(args.skill_path)
    description = args.description or source_description
    eval_set = json.loads(args.eval_set.read_text(encoding="utf-8"))
    collected = {index: [] for index in range(len(eval_set))}
    queries = [item["query"] for item in eval_set]

    with ThreadPoolExecutor(max_workers=min(args.max_workers, args.runs_per_query)) as executor:
        futures = {
            executor.submit(evaluate_batch, queries, name, description, args.model, Path.cwd()): run_index
            for run_index in range(args.runs_per_query)
        }
        for future in as_completed(futures):
            run_index = futures[future]
            try:
                outcomes = future.result()
            except Exception as error:
                outcomes = [{"triggered": None, "error": str(error)}] * len(eval_set)
            for index, outcome in enumerate(outcomes):
                collected[index].append({"run": run_index + 1, **outcome})

    results = [summarize(item, sorted(collected[index], key=lambda run: run["run"]), args.trigger_threshold) for index, item in enumerate(eval_set)]
    passed = sum(result["pass"] for result in results)
    train_indices, test_indices = split_indices(eval_set, args.holdout)
    output = {
        "evaluator": "codex-exec-routing-classifier",
        "model": args.model,
        "skill": name,
        "description": description,
        "runs_per_query": args.runs_per_query,
        "trigger_threshold": args.trigger_threshold,
        "holdout": args.holdout,
        "summary": {"passed": passed, "failed": len(results) - passed, "total": len(results)},
        "train_summary": summary_for(results, train_indices),
        "test_summary": summary_for(results, test_indices),
        "results": results,
    }

    destination = args.results_dir / time.strftime("%Y-%m-%d_%H%M%S")
    destination.mkdir(parents=True, exist_ok=True)
    result_path = destination / "results.json"
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result_path)


if __name__ == "__main__":
    main()
