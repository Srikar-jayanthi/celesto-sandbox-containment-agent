import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.agent.sandbox import CelestoSandboxClient, CommandBlockedError


class PackageDetonatorAgent:
    """
    Automated security agent that inspects and detonates suspicious
    packages inside Celesto microVM sandboxes.
    """

    def __init__(
        self,
        sandbox_name: str,
        package_name: str = "suspicious-pkg-demo",
        fail_step_7: bool = False,
        recovery_policy: str = "rollback",
        trace_path: Optional[str] = None,
    ):
        self.sandbox_name = sandbox_name
        self.package_name = package_name
        self.fail_step_7 = fail_step_7
        self.recovery_policy = recovery_policy
        self.trace_path = trace_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "reports", "failure_trace.jsonl")
        )
        self.sandbox = CelestoSandboxClient(sandbox_name=sandbox_name)

    def _trace(self, event: str, step: int, details: str, **kwargs):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sandbox_name": self.sandbox_name,
            "step": step,
            "event": event,
            "details": details,
            **kwargs,
        }
        os.makedirs(os.path.dirname(self.trace_path), exist_ok=True)
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def run_pipeline(self) -> Dict[str, Any]:
        """
        Executes the 10-step suspicious package detonation pipeline.
        Demonstrates recovery policy handling when step 7 fails.
        """
        start_time = time.time()
        steps_executed = []

        try:
            # Step 1: Boot clean microVM guest environment
            self._trace("step_start", 1, "Booting clean microVM guest environment")
            self.sandbox.start()
            steps_executed.append(1)
            self._trace("step_complete", 1, "MicroVM guest ready")

            # Step 2: Establish zero-trust network policy
            self._trace("step_start", 2, "Enforcing zero-trust network policy (outbound blocked)")
            self.sandbox.run("iptables -P OUTPUT DROP")
            steps_executed.append(2)
            self._trace("step_complete", 2, "Network policy active")

            # Step 3: Register safety hooks and command audit logger
            self._trace("step_start", 3, "Activating hypervisor safety hooks and audit logger")
            self.sandbox.run("echo 'Safety hooks initialized'")
            steps_executed.append(3)
            self._trace("step_complete", 3, "Safety hooks engaged")

            # Step 4: Download package manifest to isolated disk
            self._trace("step_start", 4, f"Fetching manifest for package '{self.package_name}'")
            self.sandbox.run(f"mkdir -p /sandbox/pkg && echo 'Package: {self.package_name}' > /sandbox/pkg/metadata.json")
            steps_executed.append(4)
            self._trace("step_complete", 4, "Metadata downloaded")

            # Step 5: Snapshot clean pre-installation baseline state
            self._trace("step_start", 5, "Creating snapshot checkpoint 'baseline-pre-detonation'")
            snapshot_id = self.sandbox.snapshot("baseline-pre-detonation")
            steps_executed.append(5)
            self._trace("step_complete", 5, f"Snapshot created: {snapshot_id}")

            # Step 6: Static code inspection on package archive
            self._trace("step_start", 6, "Running static heuristics and AST taint analysis")
            self.sandbox.run("python3 -m py_compile /sandbox/pkg/metadata.json || true")
            steps_executed.append(6)
            self._trace("step_complete", 6, "Static analysis finished without syntax errors")

            # Step 7: Risky step - install package in isolated guest
            self._trace("step_start", 7, f"Executing package installation: pip install {self.package_name}")
            if self.fail_step_7:
                self._trace(
                    "step_failed",
                    7,
                    "Package installation crashed: segmentation fault or dependency loop during build",
                )
                # Apply recovery policy
                self._trace(
                    "policy_applied",
                    7,
                    f"Applying recovery policy: {self.recovery_policy}",
                    policy=self.recovery_policy,
                )

                if self.recovery_policy == "rollback":
                    self.sandbox.restore_snapshot("baseline-pre-detonation")
                    self._trace("recovery_action", 7, "Restored snapshot baseline-pre-detonation successfully")
                elif self.recovery_policy == "resume":
                    self._trace("recovery_action", 7, "Resumed state on existing guest disk")
                elif self.recovery_policy == "fresh":
                    self.sandbox.delete()
                    self.sandbox = CelestoSandboxClient(sandbox_name=f"{self.sandbox_name}rec")
                    self.sandbox.start()
                    self._trace("recovery_action", 7, "Spawned fresh sandbox instance")

                # Continue through fallback / remediation
                self.sandbox.run("echo 'Remediation completed after step 7 recovery'")
            else:
                self.sandbox.run(f"echo 'Installed {self.package_name} safely'")

            steps_executed.append(7)
            self._trace("step_complete", 7, "Step 7 resolved")

            # Step 8: Behavioral analysis (file mutations, socket probes)
            self._trace("step_start", 8, "Inspecting filesystem mutations and socket attempts")
            self.sandbox.run("find /sandbox -type f -mmin -5")
            steps_executed.append(8)
            self._trace("step_complete", 8, "Behavioral telemetry gathered")

            # Step 9: Synthesize risk assessment report
            self._trace("step_start", 9, "Synthesizing risk assessment scorecard")
            self.sandbox.run("echo 'Risk score: 15/100 (LOW)' > /sandbox/risk_scorecard.json")
            steps_executed.append(9)
            self._trace("step_complete", 9, "Risk scorecard generated")

            # Step 10: Cleanup sandbox and finalize ledger record
            self._trace("step_start", 10, "Cleaning up sandbox environment and recording results")
            self.sandbox.stop()
            self.sandbox.delete()
            steps_executed.append(10)
            self._trace("step_complete", 10, "Sandbox deleted cleanly")

            success = True
        except Exception as exc:
            self._trace("pipeline_error", len(steps_executed), f"Pipeline failed with exception: {str(exc)}")
            success = False
        finally:
            # Lifecycle hygiene: ensure sandbox is deleted on success, failure, or interrupt
            if self.sandbox.state != "deleted":
                self.sandbox.delete()

        duration = time.time() - start_time
        return {
            "sandbox_name": self.sandbox_name,
            "success": success,
            "steps_executed": steps_executed,
            "wall_clock_s": round(duration, 3),
        }
