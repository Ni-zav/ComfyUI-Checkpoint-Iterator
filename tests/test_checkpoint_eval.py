"""Offline regression coverage; no GPU, ComfyUI installation, or network needed."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from checkpoint_eval import (
    ComfyClient, output_names, prepare_workflow, report, run_trials, trial_plan,
)

WORKFLOW = {
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "original.safetensors"}},
    "8": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20}},
}


class WorkflowTests(unittest.TestCase):
    def test_seed_pairing_order(self):
        self.assertEqual(trial_plan(["a", "b"], [1, 2]),
                         [("a", 1), ("b", 1), ("a", 2), ("b", 2)])

    def test_duplicate_models_rejected(self):
        with self.assertRaises(ValueError):
            trial_plan(["a", "a"], [1])

    def test_does_not_mutate_input(self):
        changed = prepare_workflow(WORKFLOW, "4", "8", "new.safetensors", 22)
        self.assertEqual(changed["4"]["inputs"]["ckpt_name"], "new.safetensors")
        self.assertEqual(changed["8"]["inputs"]["seed"], 22)
        self.assertEqual(WORKFLOW["4"]["inputs"]["ckpt_name"], "original.safetensors")
        self.assertEqual(WORKFLOW["8"]["inputs"]["seed"], 1)

    def test_rejects_automatic_iterator_for_paired_eval(self):
        workflow = {"4": {"class_type": "CheckpointLoaderIterator", "inputs": {}}, "8": WORKFLOW["8"]}
        with self.assertRaisesRegex(ValueError, "CheckpointLoaderSimple"):
            prepare_workflow(workflow, "4", "8", "a", 1)

    def test_rejects_missing_sampler_seed(self):
        workflow = {"4": WORKFLOW["4"], "8": {"class_type": "KSampler", "inputs": {}}}
        with self.assertRaises(ValueError):
            prepare_workflow(workflow, "4", "8", "a", 1)

    def test_report_excludes_failed_latency(self):
        rows = [{"checkpoint": "a", "status": "completed", "latency_seconds": 2, "images": ["x"]},
                {"checkpoint": "a", "status": "error", "latency_seconds": 8, "images": []}]
        self.assertEqual(report(rows)["a"],
                         {"attempted": 2, "completed": 1, "failed": 1,
                          "mean_seconds": 2, "median_seconds": 2, "images": 1})

    def test_images_do_not_assume_quality(self):
        self.assertEqual(output_names({"outputs": {"7": {"images": [{"filename": "a.png"}]}}}), ["a.png"])


class FakeComfyHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        if self.path != "/prompt":
            self.send_error(404)
            return
        n = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(n))
        self.__class__.requests.append(payload)
        self.respond({"prompt_id": str(len(self.__class__.requests))})

    def do_GET(self):
        if self.path.startswith("/history/"):
            prompt_id = self.path.split("/")[-1]
            self.respond({prompt_id: {"status": {"status_str": "success"},
                                      "outputs": {"9": {"images": [{"filename": "out.png"}]}}}})
        else:
            self.send_error(404)

    def respond(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ClientTests(unittest.TestCase):
    def test_end_to_end_against_fake_comfy_api(self):
        FakeComfyHandler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = ComfyClient(f"http://127.0.0.1:{server.server_port}")
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "results.jsonl"
                trials = trial_plan(["model-a", "model-b"], [42, 43])
                rows = run_trials(WORKFLOW, client, "4", "8", trials, target, 3, 0.01)
                persisted = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows, persisted)
            self.assertTrue(all(row["status"] == "completed" for row in rows))
            self.assertEqual(len(FakeComfyHandler.requests), 4)
            self.assertEqual(
                [(request["prompt"]["4"]["inputs"]["ckpt_name"],
                  request["prompt"]["8"]["inputs"]["seed"]) for request in FakeComfyHandler.requests],
                trials
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
