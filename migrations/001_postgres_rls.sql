-- Defence-in-depth tenant isolation. Run after schema creation in PostgreSQL.
-- The application must SET LOCAL app.current_organization_id at transaction start.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['missions','org_entities','relations','events','investigations','hypotheses','evidence','decisions','actions','outcomes','learnings','opportunities','api_keys','integrations','webhook_endpoints','audit_logs']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.current_organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.current_organization_id'', true))', t);
  END LOOP;
END $$;
