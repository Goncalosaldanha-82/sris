CREATE TABLE IF NOT EXISTS guided_reasoning_sessions (
 id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 mission_id VARCHAR(36) NOT NULL REFERENCES missions(id) ON DELETE CASCADE, user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
 intention VARCHAR(30) NOT NULL, guidance_version VARCHAR(50) NOT NULL DEFAULT 'sees-guidance-0.4', status VARCHAR(20) NOT NULL DEFAULT 'active',
 current_index INTEGER NOT NULL DEFAULT 0, answers JSON NOT NULL DEFAULT '[]', started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), completed_at TIMESTAMPTZ NULL);
CREATE INDEX IF NOT EXISTS ix_guided_reasoning_org_mission ON guided_reasoning_sessions(organization_id, mission_id);
ALTER TABLE guided_reasoning_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS guided_reasoning_sessions_tenant_isolation ON guided_reasoning_sessions;
CREATE POLICY guided_reasoning_sessions_tenant_isolation ON guided_reasoning_sessions USING (organization_id = current_setting('app.current_organization_id', true));
