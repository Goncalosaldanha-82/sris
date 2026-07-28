-- SRIS epistemic core: first-class observations, assumptions, constraints,
-- alternatives, implementations, attribution assessments and learning reuse.
-- In a live installation run through Alembic after taking a verified backup.

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'observations','assumptions','constraints','alternatives','implementations',
    'attribution_assessments','learning_reuses'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.current_organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.current_organization_id'', true))', t
    );
  END LOOP;
END $$;
