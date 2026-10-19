import os
import re
import json
import math
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")


# 1. Test docker-compose.yml and Dockerfile
def test_docker_compose_and_dockerfile():
    dockerfile_path = os.path.join(ROOT_DIR, "Dockerfile")
    compose_path = os.path.join(ROOT_DIR, "docker-compose.yml")

    assert os.path.isfile(dockerfile_path), "Dockerfile must exist at repository root"
    assert os.path.isfile(compose_path), "docker-compose.yml must exist at repository root"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_content = f.read()

    # Check services api and ledger
    assert "api:" in compose_content, "Service 'api' must be defined in docker-compose.yml"
    assert "ledger:" in compose_content, "Service 'ledger' must be defined in docker-compose.yml"

    # Check seed mount
    assert "./seeds:" in compose_content, "ledger service must mount ./seeds"

    # Check healthchecks
    assert "pg_isready" in compose_content, "ledger healthcheck must use pg_isready"
    assert "http://localhost:8080/health" in compose_content, "api healthcheck must request http://localhost:8080/health"

    # Check interval, timeout, retries, start_period
    assert "interval:" in compose_content
    assert "timeout:" in compose_content
    assert "retries:" in compose_content
    assert "start_period:" in compose_content
    assert "depends_on:" in compose_content
    assert "condition: service_healthy" in compose_content


# 2. Test environment variables
def test_environment_variables():
    env_example_path = os.path.join(ROOT_DIR, ".env.example")
    env_live_path = os.path.join(ROOT_DIR, ".env")

    assert os.path.isfile(env_example_path), ".env.example must exist at root"
    assert not os.path.exists(env_live_path), ".env must not be present at repository root"

    with open(env_example_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_keys = [
        "CELESTO_PROVIDER",
        "CELESTO_API_KEY",
        "LLM_API_KEY",
        "LLM_MODEL",
        "DATABASE_URL",
        "API_PORT",
    ]
    for key in required_keys:
        assert f"{key}=" in content, f"Key {key} must be in .env.example"

    # Confirm values are placeholders
    assert "replace-me" in content or "replace-with" in content


# 3. Test reports/problem.json
def test_problem_json():
    path = os.path.join(ROOT_DIR, "reports", "problem.json")
    assert os.path.isfile(path), "reports/problem.json must exist"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in ["who", "agent_work", "proof_output", "idea_source"]:
        assert key in data, f"Missing required key '{key}' in problem.json"

    assert data["idea_source"] in ["idea_bank", "original"]
    assert isinstance(data["who"], str) and len(data["who"]) >= 40
    assert isinstance(data["agent_work"], str) and len(data["agent_work"]) >= 40
    assert isinstance(data["proof_output"], str) and len(data["proof_output"]) >= 20


# 4. Test logs/commands.jsonl
def test_commands_audit_log():
    log_path = os.path.join(ROOT_DIR, "logs", "commands.jsonl")
    assert os.path.isfile(log_path), "logs/commands.jsonl must exist"

    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) > 0, "logs/commands.jsonl must have at least one line"

    for idx, line in enumerate(lines):
        record = json.loads(line)
        for req_field in ["ts", "sandbox_name", "command", "decision", "execution_target"]:
            assert req_field in record, f"Line {idx} missing {req_field}"

        # ISO-8601 validation
        datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))

        assert SANDBOX_REGEX.match(record["sandbox_name"]), f"Invalid sandbox_name on line {idx}: {record['sandbox_name']}"
        assert record["command"] != "", f"Empty command on line {idx}"
        assert record["decision"] in ["allow", "block"], f"Invalid decision on line {idx}: {record['decision']}"
        assert record["execution_target"] == "celesto_sandbox", f"execution_target must be celesto_sandbox, got {record['execution_target']}"


# 5. Test reports/capabilities.json
def test_capabilities_json():
    path = os.path.join(ROOT_DIR, "reports", "capabilities.json")
    assert os.path.isfile(path), "reports/capabilities.json must exist"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "capabilities" in data
    caps = data["capabilities"]
    assert len(caps) >= 2, "Must specify at least two capabilities"

    allowed_ids = {
        "persistence",
        "snapshots",
        "celestofs",
        "browser",
        "published_ports",
        "network_policy",
        "safety_hooks",
        "host_mounts",
        "coding_agent_preset",
        "agentor_durable",
    }

    seen_ids = set()
    for cap in caps:
        cap_id = cap.get("id")
        assert cap_id in allowed_ids, f"Disallowed capability id: {cap_id}"
        assert cap_id not in seen_ids, f"Duplicate capability id: {cap_id}"
        seen_ids.add(cap_id)

        why = cap.get("why", "")
        assert isinstance(why, str) and len(why) >= 80, f"why field must be >= 80 chars, was {len(why)}"

        evidence_path = cap.get("evidence_path", "")
        full_evidence = os.path.join(ROOT_DIR, evidence_path)
        assert os.path.isfile(full_evidence), f"evidence_path does not exist: {evidence_path}"


# 6. Test reports/lifecycle.json
def test_lifecycle_json():
    path = os.path.join(ROOT_DIR, "reports", "lifecycle.json")
    assert os.path.isfile(path), "reports/lifecycle.json must exist"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("cleanup_on_success") is True
    assert data.get("cleanup_on_failure") is True
    assert data.get("cleanup_on_interrupt") is True

    names = data.get("sandbox_names", [])
    assert len(names) > 0, "sandbox_names must not be empty"
    assert len(names) == len(set(names)), "sandbox_names must be unique"

    for name in names:
        assert SANDBOX_REGEX.match(name), f"Invalid sandbox name: {name}"

    # Confirm each name appears in commands.jsonl or reliability.json
    commands_log = os.path.join(ROOT_DIR, "logs", "commands.jsonl")
    reliability_path = os.path.join(ROOT_DIR, "reports", "reliability.json")

    known_names = set()
    if os.path.exists(commands_log):
        with open(commands_log, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    known_names.add(json.loads(line).get("sandbox_name"))

    if os.path.exists(reliability_path):
        with open(reliability_path, "r", encoding="utf-8") as f:
            rdata = json.load(f)
            for r in rdata.get("runs", []):
                known_names.add(r.get("sandbox_name"))

    for name in names:
        assert name in known_names, f"Lifecycle sandbox {name} not found in commands.jsonl or reliability.json"


# 7. Test reports/reliability.json and reports/postmortem.md
def test_reliability_and_postmortem():
    rel_path = os.path.join(ROOT_DIR, "reports", "reliability.json")
    postmortem_path = os.path.join(ROOT_DIR, "reports", "postmortem.md")

    assert os.path.isfile(rel_path), "reports/reliability.json must exist"
    assert os.path.isfile(postmortem_path), "reports/postmortem.md must exist"

    with open(postmortem_path, "r", encoding="utf-8") as f:
        pm_content = f.read()
    assert len(pm_content) >= 200, f"postmortem.md must be >= 200 chars, got {len(pm_content)}"

    with open(rel_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    run_count = data.get("run_count", 0)

    assert run_count >= 20, "run_count must be at least 20"
    assert len(runs) == run_count, "run_count must match len(runs)"

    seen_names = set()
    for r in runs:
        sname = r.get("sandbox_name")
        assert SANDBOX_REGEX.match(sname), f"Invalid sandbox_name: {sname}"
        assert sname not in seen_names, f"Duplicate sandbox_name: {sname}"
        seen_names.add(sname)

        assert r.get("fresh") is True, f"fresh must be true on run {sname}"
        assert isinstance(r.get("success"), bool)
        assert r.get("wall_clock_s") >= 0
        assert r.get("boot_to_ready_s") >= 0
        assert r.get("cost_usd") >= 0

    # Arithmetic checks
    success_count = sum(1 for r in runs if r["success"])
    expected_rate = success_count / float(run_count)
    assert abs(data.get("success_rate", 0) - expected_rate) <= 0.001

    # Sorted wall_clock_s
    sorted_wall = sorted([r["wall_clock_s"] for r in runs])
    n = len(sorted_wall)
    expected_median_wall = (sorted_wall[n // 2 - 1] + sorted_wall[n // 2]) / 2.0
    assert abs(data.get("median_wall_clock_s", 0) - expected_median_wall) <= 0.001

    # p90 rank = ceil(0.90 * n)
    p90_rank = math.ceil(0.90 * n)
    expected_p90_wall = sorted_wall[p90_rank - 1]
    assert abs(data.get("p90_wall_clock_s", 0) - expected_p90_wall) <= 0.001

    # Median boot to ready
    sorted_boot = sorted([r["boot_to_ready_s"] for r in runs])
    expected_median_boot = (sorted_boot[n // 2 - 1] + sorted_boot[n // 2]) / 2.0
    assert abs(data.get("median_boot_to_ready_s", 0) - expected_median_boot) <= 0.001

    # Total cost
    expected_total_cost = sum(r["cost_usd"] for r in runs)
    assert abs(data.get("total_cost_usd", 0) - expected_total_cost) <= 0.01

    assert data.get("postmortem_path") == "reports/postmortem.md"


# 8. Test reports/containment.json
def test_containment_json():
    path = os.path.join(ROOT_DIR, "reports", "containment.json")
    assert os.path.isfile(path), "reports/containment.json must exist"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("attack") in ["prompt_injection_exfil", "destructive_command", "suspicious_package"]
    assert data.get("blocked") is True
    assert data.get("host_untouched") is True

    evidence_paths = data.get("evidence_paths", [])
    assert len(evidence_paths) >= 1
    for ep in evidence_paths:
        full_ep = os.path.join(ROOT_DIR, ep)
        assert os.path.isfile(full_ep), f"Containment evidence path missing: {ep}"


# 9. Test reports/failure_policy.json and failure_trace.jsonl
def test_failure_policy_and_trace():
    policy_path = os.path.join(ROOT_DIR, "reports", "failure_policy.json")
    assert os.path.isfile(policy_path), "reports/failure_policy.json must exist"

    with open(policy_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("failed_step") == 7
    assert data.get("total_steps") == 10
    policy = data.get("policy")
    assert policy in ["resume", "rollback", "fresh"]
    assert isinstance(data.get("rationale"), str) and len(data.get("rationale")) >= 200

    trace_path = os.path.join(ROOT_DIR, data.get("trace_path", "reports/failure_trace.jsonl"))
    assert os.path.isfile(trace_path), f"Trace file does not exist: {trace_path}"

    with open(trace_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) > 0, "failure_trace.jsonl must have lines"

    found_policy_applied = False
    for line in lines:
        entry = json.loads(line)
        if entry.get("event") == "policy_applied" and entry.get("policy") == policy:
            found_policy_applied = True
            break

    assert found_policy_applied, f"No line found with event='policy_applied' and policy='{policy}'"


# 10. Test reports/concurrency.json
def test_concurrency_json():
    path = os.path.join(ROOT_DIR, "reports", "concurrency.json")
    assert os.path.isfile(path), "reports/concurrency.json must exist"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("jobs", [])
    assert len(jobs) >= 5, "concurrency.json must contain at least 5 jobs"

    seen_names = set()
    for job in jobs:
        sname = job.get("sandbox_name")
        assert SANDBOX_REGEX.match(sname), f"Invalid sandbox_name in concurrency job: {sname}"
        assert sname not in seen_names, f"Duplicate sandbox_name in concurrency: {sname}"
        seen_names.add(sname)

        started_at = job.get("started_at", "")
        assert started_at, "started_at must be non-empty"

    notes = data.get("breakage_notes", "")
    assert isinstance(notes, str) and len(notes) >= 40, "breakage_notes must be at least 40 characters"


# 11. Test Run Ledger API Endpoints
def test_run_ledger_api():
    from src.api.main import app

    client = TestClient(app)

    # GET /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok"}

    # GET /api/runs
    res_runs = client.get("/api/runs")
    assert res_runs.status_code == 200
    runs = res_runs.json()
    assert isinstance(runs, list)
    names = [r["sandbox_name"] for r in runs]
    assert "sbx-seeddemo1" in names, "Seed row 'sbx-seeddemo1' must be present in GET /api/runs"

    # POST /api/runs valid
    valid_payload = {
        "run_id": "test-run-001",
        "sandbox_name": "sbx-testval01",
        "problem_id": "prob-detonator-01",
        "state": "running",
        "execution_target": "celesto_sandbox",
    }
    res_post_valid = client.post("/api/runs", json=valid_payload)
    assert res_post_valid.status_code == 201
    created_data = res_post_valid.json()
    assert created_data["sandbox_name"] == "sbx-testval01"
    assert created_data["state"] == "running"

    # POST /api/runs invalid execution_target -> 400
    host_payload = {
        "run_id": "test-run-002",
        "sandbox_name": "sbx-testval02",
        "problem_id": "prob-detonator-01",
        "state": "running",
        "execution_target": "host",
    }
    res_post_host = client.post("/api/runs", json=host_payload)
    assert res_post_host.status_code == 400, "POST with execution_target 'host' must return 400"

    # POST /api/runs invalid state -> 400
    bad_state_payload = {
        "run_id": "test-run-003",
        "sandbox_name": "sbx-testval03",
        "problem_id": "prob-detonator-01",
        "state": "unknown_state",
        "execution_target": "celesto_sandbox",
    }
    res_bad_state = client.post("/api/runs", json=bad_state_payload)
    assert res_bad_state.status_code == 400, "POST with unknown state must return 400"

    # POST /api/runs invalid sandbox_name -> 400
    bad_name_payload = {
        "run_id": "test-run-004",
        "sandbox_name": "invalid_name",
        "problem_id": "prob-detonator-01",
        "state": "created",
        "execution_target": "celesto_sandbox",
    }
    res_bad_name = client.post("/api/runs", json=bad_name_payload)
    assert res_bad_name.status_code == 400, "POST with invalid sandbox_name must return 400"
