-- SRIS v0.9: independent provenance records for examinable contributions.
CREATE TABLE IF NOT EXISTS provenance_records (
    id varchar(36) PRIMARY KEY,
    organization_id varchar(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    origin_type varchar(30) NOT NULL,
    origin_actor varchar(240),
    acquisition_type varchar(40) NOT NULL DEFAULT 'other',
    source_reference text,
    method_or_modality text NOT NULL,
    model_or_system varchar(240),
    version varchar(120),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    input_context_reference text,
    policy_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence_claim double precision,
    uncertainty_notes text NOT NULL DEFAULT '',
    limitations text NOT NULL,
    verification_status varchar(30) NOT NULL DEFAULT 'declared',
    verification_record jsonb NOT NULL DEFAULT '{}'::jsonb,
    integrity_reference varchar(240),
    metadata_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_provenance_records_organization_id ON provenance_records(organization_id);
CREATE INDEX IF NOT EXISTS ix_provenance_records_origin_type ON provenance_records(origin_type);
CREATE INDEX IF NOT EXISTS ix_provenance_records_verification_status ON provenance_records(verification_status);
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS provenance_id varchar(36);
CREATE INDEX IF NOT EXISTS ix_evidence_provenance_id ON evidence(provenance_id);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_evidence_provenance') THEN
        ALTER TABLE evidence ADD CONSTRAINT fk_evidence_provenance FOREIGN KEY (provenance_id) REFERENCES provenance_records(id) ON DELETE SET NULL;
    END IF;
END $$;
ALTER TABLE provenance_records ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON provenance_records;
CREATE POLICY tenant_isolation ON provenance_records
USING (organization_id = current_setting('app.current_organization_id', true))
WITH CHECK (organization_id = current_setting('app.current_organization_id', true));
