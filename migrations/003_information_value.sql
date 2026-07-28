-- SRIS Pilot Release: proposed evidence used by the Value of Information engine.
-- Apply through the normal migration process after a verified backup.

CREATE TABLE IF NOT EXISTS evidence_proposals (
  id varchar(36) PRIMARY KEY,
  organization_id varchar(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  investigation_id varchar(36) NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  title varchar(240) NOT NULL,
  description text NOT NULL DEFAULT '',
  expected_effects jsonb NOT NULL DEFAULT '{}'::jsonb,
  weight double precision NOT NULL DEFAULT 0.5,
  estimated_cost double precision NULL,
  estimated_days double precision NULL,
  risk_level varchar(20) NOT NULL DEFAULT 'low',
  feasibility varchar(30) NOT NULL DEFAULT 'unknown',
  status varchar(30) NOT NULL DEFAULT 'proposed',
  limitations text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_evidence_proposals_org ON evidence_proposals(organization_id);
CREATE INDEX IF NOT EXISTS ix_evidence_proposals_investigation ON evidence_proposals(investigation_id);

ALTER TABLE evidence_proposals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON evidence_proposals;
CREATE POLICY tenant_isolation ON evidence_proposals
  USING (organization_id = current_setting('app.current_organization_id', true))
  WITH CHECK (organization_id = current_setting('app.current_organization_id', true));
