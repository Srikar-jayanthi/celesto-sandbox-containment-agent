-- Create runs ledger table if it does not exist
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(128) PRIMARY KEY,
    sandbox_name VARCHAR(128) NOT NULL UNIQUE,
    problem_id VARCHAR(128) NOT NULL,
    state VARCHAR(64) NOT NULL,
    execution_target VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookup by sandbox_name and state
CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs (sandbox_name);
CREATE INDEX IF NOT EXISTS idx_runs_state ON runs (state);

-- Seed initial row required by specification
-- sandbox_name: sbx-seeddemo1, state: deleted, execution_target: celesto_sandbox
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, created_at, updated_at)
VALUES (
    'run-seed-demo-001',
    'sbx-seeddemo1',
    'problem-detonator-01',
    'deleted',
    'celesto_sandbox',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (sandbox_name) DO UPDATE SET
    run_id = EXCLUDED.run_id,
    problem_id = EXCLUDED.problem_id,
    state = EXCLUDED.state,
    execution_target = EXCLUDED.execution_target,
    updated_at = CURRENT_TIMESTAMP;
