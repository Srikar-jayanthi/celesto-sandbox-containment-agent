import os
import re
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
AUDIT_LOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "commands.jsonl"))

# Dangerous command indicators for safety hooks
BLOCKED_PATTERNS = [
    re.compile(r"curl.*(?:\$API_KEY|\.env|webhook|attacker|exfil)", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+(?:/|/etc|/var|/root|~|\$HOME)", re.IGNORECASE),
    re.compile(r"(?:nc|netcat|bash\s+-i).*(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE),
    re.compile(r"cat\s+.*(?:\.env|id_rsa|shadow)", re.IGNORECASE),
    re.compile(r"pip\s+install\s+.*(?:evil|backdoor|malicious|pwned)", re.IGNORECASE),
]


class CommandBlockedError(Exception):
    """Raised when a command is blocked by a safety hook before reaching the VM."""
    pass


class CommandResult:
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str, blocked: bool = False):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.blocked = blocked
        self.ok = (exit_code == 0) and not blocked


class CelestoSandboxClient:
    """
    Manages isolated execution inside Celesto microVM sandboxes.
    Enforces that every command is logged to logs/commands.jsonl with
    execution_target='celesto_sandbox'.
    """

    def __init__(
        self,
        sandbox_name: str,
        provider: str = "cloud",
        backend: str = "firecracker",
        network_enabled: bool = False,
        hooks: Optional[List[Callable[[str], bool]]] = None,
        audit_log_path: str = AUDIT_LOG_PATH,
    ):
        if not SANDBOX_REGEX.match(sandbox_name):
            raise ValueError(f"Invalid sandbox name '{sandbox_name}'. Must match ^sbx-[a-z0-9]{{8,}}$")

        self.sandbox_name = sandbox_name
        self.provider = provider
        self.backend = backend
        self.network_enabled = network_enabled
        self.hooks = hooks or []
        self.audit_log_path = audit_log_path
        self.state = "created"
        self.snapshots: Dict[str, Dict[str, Any]] = {}

        os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)

    def _log_audit(self, command: str, decision: str):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sandbox_name": self.sandbox_name,
            "command": command,
            "decision": decision,
            "execution_target": "celesto_sandbox",
        }
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def start(self) -> None:
        self.state = "ready"

    def run(self, command: str) -> CommandResult:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        self.state = "running"

        # Evaluate safety hooks
        is_blocked = False
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(command):
                is_blocked = True
                break

        for hook in self.hooks:
            if not hook(command):
                is_blocked = True
                break

        if is_blocked:
            self._log_audit(command, decision="block")
            raise CommandBlockedError(f"Safety hook blocked command: {command}")

        self._log_audit(command, decision="allow")

        # Simulate or dispatch inside microVM
        # In mock/offline mode, return realistic exit codes
        exit_code = 0
        stdout = f"[celesto-guest: {self.sandbox_name}] executed: {command}"
        stderr = ""

        if "fail" in command.lower() or "error" in command.lower():
            exit_code = 1
            stderr = "Simulated failure inside guest kernel"

        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            blocked=False,
        )

    def snapshot(self, snapshot_id: str) -> str:
        self.snapshots[snapshot_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sandbox_name": self.sandbox_name,
            "state": self.state,
        }
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> None:
        if snapshot_id not in self.snapshots:
            raise KeyError(f"Snapshot {snapshot_id} does not exist")
        self.state = "ready"

    def stop(self) -> None:
        self.state = "stopped"

    def delete(self) -> None:
        self.state = "deleted"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.delete()
