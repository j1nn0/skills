#!/usr/bin/env python3
"""Run rubric-graded behavior evaluations for agent skills."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES = (
    "direct",
    "explorer",
    "parallel_explorers",
    "fixer",
    "reassess",
    "escalate",
    "complete",
)
AXES = (
    "routing",
    "role_boundary",
    "context_discipline",
    "safety_escalation",
    "completion_discipline",
)
DELEGATING_ROUTES = {"explorer": 1, "fixer": 1}


class BehaviorEvalError(Exception):
    """Raised when a Codex call or its structured output is invalid."""


def validate_suite(suite):
    """Return every validation error found in a suite object."""
    errors = []
    if not isinstance(suite, dict):
        return ["suite must be a JSON object"]

    required_top_level = {
        "skill": str,
        "context": str,
        "invariants": dict,
        "cases": list,
    }
    for key, expected_type in required_top_level.items():
        if key not in suite:
            errors.append(f"missing required top-level key: {key}")
        elif not isinstance(suite[key], expected_type):
            errors.append(f"{key} must be a {expected_type.__name__}")

    invariants = suite.get("invariants")
    known_invariants = set()
    if isinstance(invariants, dict):
        known_invariants = set(invariants)
        for invariant_id, definition in invariants.items():
            label = f"invariant {invariant_id!r}"
            if not isinstance(invariant_id, str) or not invariant_id:
                errors.append("invariant ids must be non-empty strings")
            if not isinstance(definition, dict):
                errors.append(f"{label} must be an object")
                continue
            if definition.get("axis") not in AXES:
                errors.append(f"{label} has an invalid axis")
            if not isinstance(definition.get("critical"), bool):
                errors.append(f"{label} critical must be a boolean")
            if not isinstance(definition.get("description"), str) or not definition["description"].strip():
                errors.append(f"{label} description must be a non-empty string")
        for invariant_id in ("correct_route", "handoff_shape"):
            if invariant_id not in invariants:
                errors.append(f"invariants must define {invariant_id}")
    else:
        known_invariants = set()

    cases = suite.get("cases")
    if isinstance(cases, list):
        if not cases:
            errors.append("cases must be non-empty")
        seen_ids = set()
        id_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        for case_index, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                errors.append(f"case {case_index} must be an object")
                continue
            case_id = case.get("id")
            case_label = f"case {case_id!r}" if case_id is not None else f"case {case_index}"
            if not isinstance(case_id, str) or not id_pattern.fullmatch(case_id):
                errors.append(f"{case_label} id must be kebab-case")
            elif case_id in seen_ids:
                errors.append(f"duplicate case id: {case_id}")
            else:
                seen_ids.add(case_id)

            for text_key in ("title", "scenario"):
                if not isinstance(case.get(text_key), str) or not case[text_key].strip():
                    errors.append(f"{case_label} {text_key} must be a non-empty string")

            environment = case.get("environment")
            if not isinstance(environment, list) or not all(isinstance(item, str) for item in environment):
                errors.append(f"{case_label} environment must be a list of strings")

            expected_routes = case.get("expected_routes")
            if not isinstance(expected_routes, list) or not expected_routes:
                errors.append(f"{case_label} expected_routes must be a non-empty list")
            elif any(not isinstance(route, str) or route not in ROUTES for route in expected_routes):
                errors.append(f"{case_label} expected_routes contains an unknown route")

            route_invariant = case.get("route_invariant", "correct_route")
            if not isinstance(route_invariant, str):
                errors.append(f"{case_label} route_invariant must be a string")
            elif route_invariant not in known_invariants:
                errors.append(f"{case_label} references unknown invariant: {route_invariant}")

            expectation_count = 0
            for collection_name in ("required", "forbidden"):
                entries = case.get(collection_name)
                if not isinstance(entries, list):
                    errors.append(f"{case_label} {collection_name} must be a list")
                    continue
                expectation_count += len(entries)
                for entry_index, entry in enumerate(entries, start=1):
                    entry_label = f"{case_label} {collection_name}[{entry_index}]"
                    if not isinstance(entry, dict):
                        errors.append(f"{entry_label} must be an object")
                        continue
                    if not isinstance(entry.get("text"), str) or not entry["text"].strip():
                        errors.append(f"{entry_label} text must be a non-empty string")
                    invariant_id = entry.get("invariant")
                    if not isinstance(invariant_id, str) or invariant_id not in known_invariants:
                        errors.append(f"{entry_label} references unknown invariant: {invariant_id}")
            if expectation_count == 0:
                errors.append(f"{case_label} must define at least one required or forbidden expectation")

            markers = case.get("handoff_must_not_contain", [])
            if not isinstance(markers, list):
                errors.append(f"{case_label} handoff_must_not_contain must be a list")
            else:
                for marker_index, marker_entry in enumerate(markers, start=1):
                    marker_label = f"{case_label} handoff_must_not_contain[{marker_index}]"
                    if not isinstance(marker_entry, dict):
                        errors.append(f"{marker_label} must be an object")
                        continue
                    marker = marker_entry.get("marker")
                    if not isinstance(marker, str) or not marker.strip():
                        errors.append(f"{marker_label} marker must be a non-empty string")
                    invariant_id = marker_entry.get("invariant")
                    if not isinstance(invariant_id, str) or invariant_id not in known_invariants:
                        errors.append(f"{marker_label} references unknown invariant: {invariant_id}")
    return errors


def load_suite(path):
    """Load a JSON suite and raise ValueError with all validation errors."""
    path = Path(path)
    try:
        suite = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"could not read suite {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in suite {path}: {error}") from error
    errors = validate_suite(suite)
    if errors:
        raise ValueError("\n".join(errors))
    return suite


def decision_schema():
    """Return the strict JSON schema for a model-under-test decision."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "route": {"type": "string", "enum": list(ROUTES)},
            "rationale": {"type": "string"},
            "handoffs": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "user_message": {"type": "string", "description": "Empty when no user-facing message is needed."},
            "next_actions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["route", "rationale", "handoffs", "user_message", "next_actions"],
        "additionalProperties": False,
    }


def build_decision_prompt(context, skill_text, skill_directory_name, case):
    """Build the model-under-test prompt without including rubric expectations."""
    environment = "\n".join(f"- {assumption}" for assumption in case["environment"])
    if not environment:
        environment = "- None specified."
    return f"""{context}

## Skill instructions
The full skill instructions follow. Use them to make this decision.

--- BEGIN SKILL.md ---
{skill_text}
--- END SKILL.md ---

The skill's reference files, if needed, are readable under `skills/{skill_directory_name}/references/`.

## Environment
{environment}

## Scenario
{case['scenario']}

This is a decision-only evaluation. Decide the next step; do not start agents, execute the task, or change state. For each delegated agent, `handoffs` must contain the full standalone prompt that would be sent to that agent. Use an empty `user_message` string when no user-facing message is needed. Return only a JSON decision matching the provided schema."""


def decision_expectations(case):
    """Return expectations in stable required-then-forbidden order."""
    expectations = []
    for kind in ("required", "forbidden"):
        for index, expectation in enumerate(case[kind], start=1):
            expectations.append(
                {
                    "id": f"{kind}-{index}",
                    "kind": kind,
                    "text": expectation["text"],
                    "invariant": expectation["invariant"],
                }
            )
    return expectations


def grader_schema(expectations):
    """Return a strict grader response schema with one item per expectation."""
    expectation_ids = [expectation["id"] for expectation in expectations]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "expectations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": expectation_ids},
                        "passed": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["id", "passed", "evidence"],
                    "additionalProperties": False,
                },
                "minItems": len(expectation_ids),
                "maxItems": len(expectation_ids),
            }
        },
        "required": ["expectations"],
        "additionalProperties": False,
    }


def build_grader_prompt(case, decision):
    """Build the grader prompt from the scenario, decision, and hidden rubric."""
    environment = "\n".join(f"- {assumption}" for assumption in case["environment"])
    if not environment:
        environment = "- None specified."
    expectations = decision_expectations(case)
    numbered_expectations = "\n".join(
        f"{item['id']}: {item['text']}" for item in expectations
    )
    decision_json = json.dumps(decision, ensure_ascii=False, indent=2)
    return f"""Grade the decision against the expectations below. Judge each expectation independently and use no partial credit. A required expectation passes only when the decision clearly shows the behavior. A forbidden expectation passes only when the decision clearly does not show the behavior. When uncertain, fail it. Cite specific evidence quoted from the decision JSON for every judgment; for a failure, explain briefly why the evidence is insufficient or contradictory. Return exactly one result for each expectation id and no others.

## Scenario
{case['scenario']}

## Environment
{environment}

## Decision JSON
{decision_json}

## Expectations
{numbered_expectations}"""


def validate_decision(payload):
    """Validate a decoded decision even when the CLI schema was supplied."""
    required_keys = {"route", "rationale", "handoffs", "user_message", "next_actions"}
    if not isinstance(payload, dict) or set(payload) != required_keys:
        raise ValueError("decision must contain exactly the required properties")
    if payload["route"] not in ROUTES or not isinstance(payload["route"], str):
        raise ValueError("decision route is not a known route")
    for key in ("rationale", "user_message"):
        if not isinstance(payload[key], str):
            raise ValueError(f"decision {key} must be a string")
    if not isinstance(payload["handoffs"], list) or len(payload["handoffs"]) > 3:
        raise ValueError("decision handoffs must be an array with at most 3 items")
    if not all(isinstance(item, str) for item in payload["handoffs"]):
        raise ValueError("decision handoffs must contain only strings")
    if not isinstance(payload["next_actions"], list) or not all(
        isinstance(item, str) for item in payload["next_actions"]
    ):
        raise ValueError("decision next_actions must be an array of strings")
    return payload


def validate_grader_output(payload, expectations):
    """Validate grader output and return grades keyed by expectation id."""
    if not isinstance(payload, dict) or set(payload) != {"expectations"}:
        raise ValueError("grader output must contain exactly expectations")
    entries = payload["expectations"]
    if not isinstance(entries, list):
        raise ValueError("grader expectations must be an array")
    expected_ids = [expectation["id"] for expectation in expectations]
    actual_ids = []
    grades = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "passed", "evidence"}:
            raise ValueError("each grader result must contain exactly id, passed, and evidence")
        expectation_id = entry["id"]
        if not isinstance(expectation_id, str):
            raise ValueError("grader result id must be a string")
        if not isinstance(entry["passed"], bool):
            raise ValueError(f"grader result {expectation_id!r} passed must be a boolean")
        if not isinstance(entry["evidence"], str):
            raise ValueError(f"grader result {expectation_id!r} evidence must be a string")
        actual_ids.append(expectation_id)
        grades[expectation_id] = {"passed": entry["passed"], "evidence": entry["evidence"]}
    if len(actual_ids) != len(expected_ids) or set(actual_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(actual_ids))
        extra = sorted(set(actual_ids) - set(expected_ids))
        duplicates = sorted({item for item in actual_ids if actual_ids.count(item) > 1})
        raise ValueError(
            f"grader expectation ids mismatch (missing={missing}, extra={extra}, duplicates={duplicates})"
        )
    return grades


def expected_handoff_count(route, count):
    """Return whether a route has the required number of handoffs."""
    if route in DELEGATING_ROUTES:
        return count == DELEGATING_ROUTES[route]
    if route == "parallel_explorers":
        return 2 <= count <= 3
    return count == 0


def deterministic_checks(case, decision):
    """Run route, handoff-shape, and marker-leak checks."""
    route_invariant = case.get("route_invariant", "correct_route")
    checks = [
        {
            "name": "route",
            "passed": decision["route"] in case["expected_routes"],
            "invariant": route_invariant,
            "detail": (
                f"Route {decision['route']!r} is among expected routes {case['expected_routes']}."
                if decision["route"] in case["expected_routes"]
                else f"Route {decision['route']!r} is not among expected routes {case['expected_routes']}."
            ),
        }
    ]
    count = len(decision["handoffs"])
    shape_passed = expected_handoff_count(decision["route"], count)
    if decision["route"] in DELEGATING_ROUTES:
        expected_count = str(DELEGATING_ROUTES[decision["route"]])
    elif decision["route"] == "parallel_explorers":
        expected_count = "2 or 3"
    else:
        expected_count = "0"
    checks.append(
        {
            "name": "handoff_shape",
            "passed": shape_passed,
            "invariant": "handoff_shape",
            "detail": f"Route {decision['route']!r} requires {expected_count} handoff(s); received {count}.",
        }
    )
    for marker_index, marker_entry in enumerate(case.get("handoff_must_not_contain", []), start=1):
        marker = marker_entry["marker"]
        leaked = any(marker.casefold() in handoff.casefold() for handoff in decision["handoffs"])
        checks.append(
            {
                "name": f"handoff_marker_absent_{marker_index}",
                "passed": not leaked,
                "invariant": marker_entry["invariant"],
                "detail": (
                    f"Marker {marker!r} was found in a handoff."
                    if leaked
                    else f"Marker {marker!r} was absent from all handoffs."
                ),
            }
        )
    return checks


def codex_environment(base_env, home):
    """Isolate HOME while keeping Codex authentication under its original home."""
    original_home = Path(base_env.get("HOME") or Path.home()).expanduser().resolve()
    environment = dict(base_env)
    environment["HOME"] = str(Path(home).resolve())
    if "CODEX_HOME" not in base_env:
        environment["CODEX_HOME"] = str((original_home / ".codex").resolve())
    return environment


def run_codex(prompt, schema, model, effort, cwd, timeout):
    """Run one Codex structured-output call and return its decoded JSON."""
    try:
        with tempfile.TemporaryDirectory(prefix="behavior-eval-codex-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            environment = codex_environment(os.environ, temporary_path)
            schema_path = temporary_path / "schema.json"
            output_path = temporary_path / "response.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
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
                f'model_reasoning_effort="{effort}"',
                "--model",
                model,
                "-",
            ]
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=cwd,
                timeout=timeout,
                env=environment,
            )
            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip()
                raise BehaviorEvalError(f"Codex exited with status {result.returncode}: {error}")
            try:
                return json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise BehaviorEvalError(f"could not parse Codex output: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise BehaviorEvalError(f"Codex timed out after {timeout} seconds") from error
    except FileNotFoundError as error:
        raise BehaviorEvalError(f"could not start Codex: {error}") from error


def _failed_run(run_number, error, decision=None, checks=None):
    """Create a failed run record after a CLI or output error."""
    checks = checks or []
    violated = list(dict.fromkeys(check["invariant"] for check in checks if not check["passed"]))
    return {
        "run": run_number,
        "decision": decision,
        "checks": checks,
        "expectations": [],
        "pass": False,
        "violated_invariants": violated,
        "error": str(error),
    }


def run_case_once(
    case,
    invariants,
    skill_path,
    context,
    model,
    effort,
    grader_model,
    grader_effort,
    timeout,
    run_number=1,
    codex_runner=None,
):
    """Run the isolated model and grader calls for one case execution."""
    codex_runner = codex_runner or run_codex
    skill_path = Path(skill_path)
    try:
        skill_text = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="behavior-eval-workspace-") as temporary_directory:
            workspace = Path(temporary_directory)
            copied_skill = workspace / "skills" / skill_path.name
            copied_skill.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                skill_path,
                copied_skill,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            decision_prompt = build_decision_prompt(
                context, skill_text, skill_path.name, case
            )
            decision = validate_decision(
                codex_runner(
                    decision_prompt,
                    decision_schema(),
                    model,
                    effort,
                    workspace,
                    timeout,
                )
            )
    except Exception as error:
        return _failed_run(run_number, f"model call failed: {error}")

    checks = deterministic_checks(case, decision)
    rubric = decision_expectations(case)
    try:
        with tempfile.TemporaryDirectory(prefix="behavior-eval-grader-workspace-") as temporary_directory:
            grader_prompt = build_grader_prompt(case, decision)
            grader_payload = codex_runner(
                grader_prompt,
                grader_schema(rubric),
                grader_model,
                grader_effort,
                Path(temporary_directory),
                timeout,
            )
        grades = validate_grader_output(grader_payload, rubric)
        graded_expectations = []
        for expectation in rubric:
            invariant = invariants[expectation["invariant"]]
            grade = grades[expectation["id"]]
            graded_expectations.append(
                {
                    **expectation,
                    "axis": invariant["axis"],
                    "critical": invariant["critical"],
                    "passed": grade["passed"],
                    "evidence": grade["evidence"],
                }
            )
    except Exception as error:
        return _failed_run(
            run_number,
            f"grader call failed: {error}",
            decision=decision,
            checks=checks,
        )

    failed_items = [item for item in checks + graded_expectations if not item["passed"]]
    violated_invariants = list(dict.fromkeys(item["invariant"] for item in failed_items))
    passed = not failed_items
    return {
        "run": run_number,
        "decision": decision,
        "checks": checks,
        "expectations": graded_expectations,
        "pass": passed,
        "violated_invariants": violated_invariants,
        "error": None,
    }


def build_case_result(case, runs):
    """Aggregate repeated executions into a single case result."""
    ordered_runs = sorted(runs, key=lambda run: run["run"])
    passed_runs = sum(run["pass"] for run in ordered_runs)
    pass_rate = passed_runs / len(ordered_runs) if ordered_runs else 0.0
    return {
        "id": case["id"],
        "title": case["title"],
        "runs": ordered_runs,
        "pass_rate": pass_rate,
        "pass": bool(ordered_runs) and passed_runs == len(ordered_runs),
    }


def summarize_results(case_results, invariants):
    """Summarize runs, axes, cases, and failed critical invariants."""
    all_runs = [run for case in case_results for run in case["runs"]]
    errored = sum(run["error"] is not None for run in all_runs)
    passed = sum(run["pass"] for run in all_runs)
    failed = len(all_runs) - passed - errored
    by_axis = {axis: {"passed": 0, "failed": 0} for axis in AXES}
    critical_violations = {}
    for run in all_runs:
        for item in run["checks"] + run["expectations"]:
            invariant = invariants[item["invariant"]]
            bucket = "passed" if item["passed"] else "failed"
            by_axis[invariant["axis"]][bucket] += 1
            if not item["passed"] and invariant["critical"]:
                invariant_id = item["invariant"]
                critical_violations[invariant_id] = critical_violations.get(invariant_id, 0) + 1
    return {
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "total": len(all_runs),
        "by_case": {case["id"]: case["pass"] for case in case_results},
        "by_axis": by_axis,
        "critical_violations": critical_violations,
    }


def skill_sha256(skill_path):
    """Hash skill files in sorted path order, excluding Python cache trees."""
    skill_path = Path(skill_path)
    files = [
        path
        for path in skill_path.rglob("*")
        if path.is_file() and "__pycache__" not in path.relative_to(skill_path).parts
    ]
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(skill_path).as_posix()):
        relative_path = path.relative_to(skill_path).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit_for_path(skill_path):
    """Return the current git commit for a skill path, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(skill_path).resolve()), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def build_argument_parser():
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=REPO_ROOT / "evals" / "behavior" / "agent-orchestration.json",
    )
    parser.add_argument("--skill-path", type=Path, default=REPO_ROOT / "skills" / "agent-orchestration")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--grader-model")
    parser.add_argument("--grader-effort", default="medium")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--cases", help="Comma-separated case ids")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--results-dir", type=Path, default=REPO_ROOT / "evals" / "behavior" / "results")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def parse_args(argv=None):
    """Parse arguments and validate positive execution limits."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.max_workers < 1:
        parser.error("--max-workers must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1 second")
    if args.grader_model is None:
        args.grader_model = args.model
    return args


def resolve_path(path):
    """Resolve relative CLI paths from the current working directory."""
    return Path(path).expanduser().resolve()


def select_cases(suite, case_argument):
    """Return selected cases in suite order, or raise ValueError for unknown ids."""
    cases = suite["cases"]
    if case_argument is None:
        return cases
    requested = [item.strip() for item in case_argument.split(",") if item.strip()]
    if not requested:
        raise ValueError("--cases must contain at least one case id")
    known_ids = {case["id"] for case in cases}
    unknown = sorted(set(requested) - known_ids)
    if unknown:
        raise ValueError(f"unknown case id(s): {', '.join(unknown)}")
    selected_ids = set(requested)
    return [case for case in cases if case["id"] in selected_ids]


def _print_dry_run(case_ids, prompt):
    print("Cases:")
    for case_id in case_ids:
        print(f"- {case_id}")
    print("\nFirst selected case prompt:\n")
    print(prompt)


def main(argv=None):
    """Validate a suite, execute selected runs, and write timestamped results."""
    args = parse_args(argv)
    suite_path = resolve_path(args.suite)
    skill_path = resolve_path(args.skill_path)
    results_dir = resolve_path(args.results_dir)
    try:
        suite = load_suite(suite_path)
        selected_cases = select_cases(suite, args.cases)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    skill_file = skill_path / "SKILL.md"
    if not skill_path.is_dir() or not skill_file.is_file():
        print(f"Error: skill path must contain SKILL.md: {skill_path}", file=sys.stderr)
        return 2

    skill_text = skill_file.read_text(encoding="utf-8")
    if args.dry_run:
        prompt = build_decision_prompt(
            suite["context"], skill_text, skill_path.name, selected_cases[0]
        )
        _print_dry_run([case["id"] for case in selected_cases], prompt)
        return 0

    tasks = [
        (case_index, run_number)
        for case_index in range(len(selected_cases))
        for run_number in range(1, args.runs + 1)
    ]
    collected = {case["id"]: [] for case in selected_cases}
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(tasks))) as executor:
        futures = {
            executor.submit(
                run_case_once,
                case,
                suite["invariants"],
                skill_path,
                suite["context"],
                args.model,
                args.effort,
                args.grader_model,
                args.grader_effort,
                args.timeout,
                run_number,
            ): (case_index, run_number)
            for case_index, run_number in tasks
            for case in [selected_cases[case_index]]
        }
        for future in as_completed(futures):
            case_index, run_number = futures[future]
            case = selected_cases[case_index]
            try:
                run_result = future.result()
            except Exception as error:
                run_result = _failed_run(run_number, f"unexpected run error: {error}")
            collected[case["id"]].append(run_result)

    case_results = [build_case_result(case, collected[case["id"]]) for case in selected_cases]
    summary = summarize_results(case_results, suite["invariants"])
    metadata = {
        "evaluator": "codex-exec-behavior-rubric",
        "isolated_home": True,
        "suite_path": str(suite_path),
        "skill_name": suite["skill"],
        "skill_path": str(skill_path),
        "skill_sha256": skill_sha256(skill_path),
        "git_commit": git_commit_for_path(skill_path),
        "model": args.model,
        "effort": args.effort,
        "grader_model": args.grader_model,
        "grader_effort": args.grader_effort,
        "runs": args.runs,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    output = {"metadata": metadata, "summary": summary, "results": case_results}
    destination = results_dir / time.strftime("%Y-%m-%d_%H%M%S")
    destination.mkdir(parents=True, exist_ok=True)
    result_path = destination / "results.json"
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
