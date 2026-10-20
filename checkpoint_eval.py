"""Repeatable ComfyUI model trials using the built-in CheckpointLoaderSimple node.

No model quality claims are inferred from runtime or output count.
This companion runner requires a running ComfyUI instance for live trials;
--dry-run and --report work without ComfyUI or extra dependencies.
"""
from __future__ import annotations

import argparse
import copy
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def trial_plan(checkpoints: list[str], seeds: list[int]) -> list[tuple[str, int]]:
    """Pair each model with the same seeds. Seed-major ordering avoids bias."""
    if not checkpoints or not seeds:
        raise ValueError("At least one checkpoint and one seed are required")
    if len(checkpoints) != len(set(checkpoints)) or len(seeds) != len(set(seeds)):
        raise ValueError("Duplicate checkpoints or seeds would bias comparison")
    if any(not name.strip() for name in checkpoints):
        raise ValueError("Checkpoint names must not be empty")
    return [(checkpoint, seed) for seed in seeds for checkpoint in checkpoints]


def prepare_workflow(workflow: dict, loader_id: str, sampler_id: str,
                     checkpoint: str, seed: int) -> dict:
    """Copy an API-format workflow, pin the checkpoint and sampling seed."""
    if not isinstance(workflow, dict):
        raise ValueError("Expected a ComfyUI API-format workflow object")
    result = copy.deepcopy(workflow)
    try:
        loader = result[str(loader_id)]
        sampler = result[str(sampler_id)]
        if loader.get("class_type") != "CheckpointLoaderSimple":
            raise ValueError(
                "Use the built-in CheckpointLoaderSimple node in the benchmark "
                "(the iterator's automatic index cannot guarantee pairing)"
            )
        if "ckpt_name" not in loader["inputs"] or "seed" not in sampler["inputs"]:
            raise ValueError("Nodes must expose ckpt_name and seed inputs")
        loader["inputs"]["ckpt_name"] = checkpoint
        sampler["inputs"]["seed"] = seed
    except KeyError as exc:
        raise ValueError(f"Missing workflow node or input: {exc}") from exc
    return result


class ComfyClient:
    def __init__(self, url: str, timeout: float = 20):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("--api must be an absolute http(s) URL")
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        request = urllib.request.Request(
            self.url + path, data=data, headers=headers,
            method="POST" if data is not None else "GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"ComfyUI request failed ({path}): {exc}") from exc
        if not isinstance(body, dict):
            raise RuntimeError(f"Expected JSON object from ComfyUI {path}")
        return body

    def submit(self, workflow: dict) -> str:
        response = self._request(
            "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}
        )
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return prompt_id

    def await_result(self, prompt_id: str, timeout: float,
                     poll_interval: float = 1.0) -> dict:
        deadline = time.monotonic() + timeout
        encoded_id = urllib.parse.quote(prompt_id, safe="")
        while True:
            response = self._request("/history/" + encoded_id)
            if prompt_id in response:
                record = response[prompt_id]
                if not isinstance(record, dict):
                    raise RuntimeError("Malformed ComfyUI history entry")
                status = record.get("status", {})
                if isinstance(status, dict) and status.get("status_str") in {"error", "failed"}:
                    raise RuntimeError("ComfyUI reported prompt execution failure")
                return record
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Prompt {prompt_id} not completed within {timeout}s")
            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))


def output_names(history: dict) -> list[str]:
    """List image names only; names alone do not prove output quality."""
    names = []
    for output in history.get("outputs", {}).values():
        if not isinstance(output, dict):
            continue
        for item in output.get("images", []):
            if isinstance(item, dict) and isinstance(item.get("filename"), str):
                names.append(item["filename"])
    return names


def run_trials(workflow: dict, client: ComfyClient, loader_id: str,
               sampler_id: str, trials: list[tuple[str, int]],
               output: Path, timeout: float, poll_interval: float) -> list[dict]:
    records: list[dict] = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for checkpoint, seed in trials:
            started = time.monotonic()
            record = {"checkpoint": checkpoint, "seed": seed, "status": "error",
                      "prompt_id": None, "latency_seconds": None, "images": [], "error": None}
            try:
                run_workflow = prepare_workflow(
                    workflow, loader_id, sampler_id, checkpoint, seed
                )
                prompt_id = client.submit(run_workflow)
                record["prompt_id"] = prompt_id
                history = client.await_result(prompt_id, timeout, poll_interval)
                record["images"] = output_names(history)
                record["status"] = "completed"
            except (ValueError, RuntimeError, TimeoutError) as exc:
                record["error"] = str(exc)
            record["latency_seconds"] = round(time.monotonic() - started, 4)
            records.append(record)
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
    return records


def report(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in records:
        groups.setdefault(row["checkpoint"], []).append(row)
    result = {}
    for checkpoint, rows in sorted(groups.items()):
        completed = [row for row in rows if row.get("status") == "completed"]
        times = [row["latency_seconds"] for row in completed
                 if isinstance(row.get("latency_seconds"), (int, float))]
        result[checkpoint] = {
            "attempted": len(rows), "completed": len(completed),
            "failed": len(rows) - len(completed),
            "mean_seconds": round(statistics.mean(times), 4) if times else None,
            "median_seconds": round(statistics.median(times), 4) if times else None,
            "images": sum(len(row.get("images", [])) for row in completed),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8188")
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--loader-id", default="")
    parser.add_argument("--sampler-id", default="")
    parser.add_argument("--checkpoints", nargs="+", default=[])
    parser.add_argument("--seeds", nargs="+", type=int, default=[])
    parser.add_argument("--out", type=Path, default=Path("trial-results.jsonl"))
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, help="Summarize an existing JSONL result file")
    args = parser.parse_args()
    if args.report:
        rows = [json.loads(line) for line in args.report.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(json.dumps(report(rows), indent=2))
        return 0
    if not args.workflow or not args.loader_id or not args.sampler_id:
        parser.error("--workflow, --loader-id and --sampler-id are required for trials")
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("timeouts and intervals must be positive")
    try:
        trials = trial_plan(args.checkpoints, args.seeds)
        workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
        for checkpoint, seed in trials:
            prepare_workflow(workflow, args.loader_id, args.sampler_id, checkpoint, seed)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps([{"checkpoint": model, "seed": seed} for model, seed in trials], indent=2))
        return 0
    client = ComfyClient(args.api)
    results = run_trials(workflow, client, args.loader_id, args.sampler_id,
                         trials, args.out, args.timeout, args.poll_interval)
    print(json.dumps(report(results), indent=2))
    return 1 if any(row["status"] != "completed" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
