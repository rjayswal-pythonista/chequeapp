-- Cheque Printing SaaS — core schema (Technical Addendum Section 3.1)
-- Tables owned by postgres; the application connects as app_user
-- (non-owner, non-superuser) so row-level security applies to it.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  plan_tier TEXT NOT NULL DEFAULT 'starter',            -- 'starter' | 'growth' | 'business'
  maker_checker_enabled BOOLEAN NOT NULL DEFAULT false,
  dual_approval_threshold_paise BIGINT,                 -- NULL = disabled; cheques >= this need 2 checkers
  subscription_status TEXT NOT NULL DEFAULT 'active'
    CHECK (subscription_status IN ('active','grace','lapsed')),
  grace_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Billing webhook idempotency (Task 5.8): a duplicate delivery must be a no-op
CREATE TABLE webhook_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id),
  email TEXT NOT NULL UNIQUE,   -- NOTE: globally unique (deviation from addendum's
                                -- UNIQUE(org_id,email); see NOTES.md entry 1)
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','maker','checker')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bank_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id),
  bank_name TEXT NOT NULL,
  page_width_mm NUMERIC NOT NULL,
  page_height_mm NUMERIC NOT NULL,
  fields JSONB NOT NULL,
  printer_offset_x_mm NUMERIC NOT NULL DEFAULT 0,
  printer_offset_y_mm NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payees (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cheques (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id),
  bank_template_id UUID NOT NULL REFERENCES bank_templates(id),
  payee_id UUID NOT NULL REFERENCES payees(id),
  amount_paise BIGINT NOT NULL CHECK (amount_paise > 0),
  amount_words TEXT NOT NULL,
  cheque_date DATE NOT NULL,
  memo TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','pending_approval','pending_second_approval','approved','rejected','printed')),
  created_by UUID NOT NULL REFERENCES users(id),
  first_approved_by UUID REFERENCES users(id),  -- set when dual approval's first checker signs off
  approved_by UUID REFERENCES users(id),
  rejected_reason TEXT,
  printed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id),
  cheque_id UUID REFERENCES cheques(id),
  actor_user_id UUID NOT NULL REFERENCES users(id),
  action TEXT NOT NULL CHECK (action IN ('created','submitted','first_approved','approved','rejected','printed','reprinted')),
  detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- Row-level security ----
-- Applied to tenant-data tables. users/organizations are exempt because
-- signup and login must run before any org context exists (NOTES.md entry 1);
-- those two tables are scoped in application code instead.

ALTER TABLE bank_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON bank_templates
  USING (org_id = current_setting('app.current_org_id', true)::UUID)
  WITH CHECK (org_id = current_setting('app.current_org_id', true)::UUID);

ALTER TABLE payees ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payees
  USING (org_id = current_setting('app.current_org_id', true)::UUID)
  WITH CHECK (org_id = current_setting('app.current_org_id', true)::UUID);

ALTER TABLE cheques ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON cheques
  USING (org_id = current_setting('app.current_org_id', true)::UUID)
  WITH CHECK (org_id = current_setting('app.current_org_id', true)::UUID);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log
  USING (org_id = current_setting('app.current_org_id', true)::UUID)
  WITH CHECK (org_id = current_setting('app.current_org_id', true)::UUID);

-- Application role privileges
GRANT SELECT, INSERT, UPDATE ON organizations, users, bank_templates, payees, cheques, audit_log, webhook_events TO app_user;
