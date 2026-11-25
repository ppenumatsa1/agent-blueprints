-- Install only in the isolated synthetic POC database as its owner.
-- Required psql variables: database_host, runtime_role, tenant_id, identity_oid, operator_oid.
\set ON_ERROR_STOP on
BEGIN;
CREATE SCHEMA ors_poc;
REVOKE ALL ON SCHEMA ors_poc FROM PUBLIC;

CREATE TABLE ors_poc.scope (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    database_host text NOT NULL CHECK (database_host <> ''),
    database_name name NOT NULL,
    runtime_role name NOT NULL,
    tenant_id uuid NOT NULL,
    identity_oid uuid NOT NULL,
    operator_oid uuid NOT NULL
);
INSERT INTO ors_poc.scope
    (database_host, database_name, runtime_role, tenant_id, identity_oid, operator_oid)
VALUES (:'database_host', current_database(), :'runtime_role', :'tenant_id',
    :'identity_oid', :'operator_oid');

-- The owner authorizes one exact, already pending synthetic proposal and outcome.
CREATE TABLE ors_poc.grant_record (
    case_id uuid PRIMARY KEY,
    payload jsonb NOT NULL,
    proposal_version integer NOT NULL,
    handle_digest text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    expires_at timestamptz NOT NULL
);
CREATE TABLE ors_poc.decision_audit (
    case_id uuid PRIMARY KEY REFERENCES ors_poc.grant_record (case_id),
    operator_oid uuid NOT NULL,
    tenant_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    handle_digest text NOT NULL,
    action text NOT NULL,
    destination_id text NOT NULL,
    decision text NOT NULL,
    decided_at timestamptz NOT NULL
);

CREATE FUNCTION ors_poc.operator_allowed(actor_tenant text, actor_id text, verified_host text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM ors_poc.scope AS s
        JOIN pg_catalog.pg_roles AS r ON r.rolname = s.runtime_role
        JOIN pg_catalog.pgaadauth_list_principals(false)
            AS p(rolename, principaltype, objectid, tenantid, ismfa, isadmin)
            ON p.rolename = r.rolname
        WHERE s.database_name = current_database()
            AND (verified_host IS NULL OR s.database_host = verified_host)
            AND s.runtime_role = session_user
            AND s.tenant_id::text = actor_tenant
            AND s.operator_oid::text = actor_id
            AND p.objectid::text = s.identity_oid::text
            AND p.tenantid::text = s.tenant_id::text
            AND p.principaltype = 'service'
            AND NOT p.isadmin
            AND NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication
                OR r.rolbypassrls)
            AND NOT pg_has_role(r.oid, current_user, 'MEMBER')
            AND NOT has_schema_privilege(r.oid, 'ors_poc', 'CREATE')
            AND NOT has_table_privilege(r.oid, 'ors_poc.scope', 'INSERT,UPDATE,DELETE,TRUNCATE')
            AND NOT has_table_privilege(r.oid, 'ors_poc.grant_record',
                'INSERT,UPDATE,DELETE,TRUNCATE')
            AND NOT has_table_privilege(r.oid, 'ors_poc.decision_audit',
                'INSERT,UPDATE,DELETE,TRUNCATE')
            AND NOT EXISTS (
                SELECT 1 FROM pg_class AS protected_table
                WHERE protected_table.oid IN (
                    'public.order_resolution_decisions'::regclass,
                    'public.wf_cases'::regclass,
                    'public.order_resolution_proposals'::regclass
                ) AND (pg_has_role(r.oid, protected_table.relowner, 'MEMBER')
                    OR has_table_privilege(r.oid, protected_table.oid, 'TRIGGER,TRUNCATE'))
            )
            AND (
                SELECT count(*) FROM pg_trigger AS t
                WHERE t.tgenabled = 'A' AND (t.tgrelid, t.tgfoid) IN (
                    ('public.order_resolution_decisions'::regclass,
                        to_regprocedure('ors_poc.audit_self_decision()')),
                    ('public.wf_cases'::regclass,
                        to_regprocedure('ors_poc.preserve_case_binding()')),
                    ('public.order_resolution_proposals'::regclass,
                        to_regprocedure('ors_poc.preserve_granted_proposal()'))
                )
            ) = 3
    )
$$;

CREATE FUNCTION ors_poc.decision_allowed(
    target_case uuid, actor_tenant text, actor_id text, target_decision text,
    require_audit boolean, verified_host text
)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
    SELECT ors_poc.operator_allowed(actor_tenant, actor_id, verified_host) AND EXISTS (
        SELECT 1
        FROM ors_poc.grant_record AS g
        JOIN public.wf_cases AS c ON c.id = g.case_id
        JOIN public.order_resolution_proposals AS p ON p.case_id = g.case_id
        LEFT JOIN ors_poc.decision_audit AS a ON a.case_id = g.case_id
        WHERE g.case_id = target_case AND g.decision = target_decision
            AND c.tenant_id = actor_tenant AND c.owner_id = actor_id AND c.reviewer_id = actor_id
            AND c.payload = g.payload AND c.checkpoint_id IS NULL
            AND p.is_current AND p.approval_required
            AND p.tenant_id = actor_tenant AND p.owner_id = actor_id AND p.reviewer_id = actor_id
            AND p.proposal_version = g.proposal_version
            AND p.decision_handle_digest = g.handle_digest
            AND p.decision_channel = 'foundry-responses'
            AND c.payload #>> '{proposal,action}' = p.action
            AND c.payload #>> '{proposal,destination_id}' = p.destination_id
            AND c.payload #>> '{proposal,input_digest}' = p.input_digest
            AND (p.action, p.destination_id) IN (
                ('partial_refund_10', 'synthetic-refund'),
                ('replacement_shipment', 'synthetic-fulfillment')
            )
            AND (
                (NOT require_audit AND a.case_id IS NULL AND c.status = 'pending'
                    AND g.expires_at > statement_timestamp()
                    AND p.decision_expires_at > statement_timestamp())
                OR (a.tenant_id::text = actor_tenant AND a.operator_oid::text = actor_id
                    AND a.proposal_version = p.proposal_version
                    AND a.handle_digest = p.decision_handle_digest
                    AND a.action = p.action AND a.destination_id = p.destination_id
                    AND a.decision = target_decision)
            )
    )
$$;

CREATE FUNCTION ors_poc.audit_self_decision()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.wf_cases AS c
                   WHERE c.id = NEW.case_id AND c.owner_id = NEW.actor_id)
        AND NOT EXISTS (SELECT 1 FROM ors_poc.grant_record AS g WHERE g.case_id = NEW.case_id)
    THEN
        RETURN NEW;
    END IF;
    IF NEW.decision_scope <> 'workflow.approve' OR NEW.decision_channel <> 'foundry-responses'
        OR NOT ors_poc.decision_allowed(
            NEW.case_id, NEW.tenant_id, NEW.actor_id, NEW.decision, false, NULL)
    THEN
        RAISE EXCEPTION 'POC decision lacks an exact protected grant' USING ERRCODE = '42501';
    END IF;
    INSERT INTO ors_poc.decision_audit
        (case_id, operator_oid, tenant_id, proposal_version, handle_digest, action,
         destination_id, decision, decided_at)
    SELECT NEW.case_id, NEW.actor_id::uuid, NEW.tenant_id::uuid, NEW.proposal_version,
        g.handle_digest, NEW.action, NEW.destination_id, NEW.decision, statement_timestamp()
    FROM ors_poc.grant_record AS g
    JOIN public.order_resolution_proposals AS p ON p.case_id = g.case_id
        AND p.is_current AND p.proposal_version = g.proposal_version
    WHERE g.case_id = NEW.case_id AND p.proposal_version = NEW.proposal_version
        AND p.action = NEW.action AND p.destination_id = NEW.destination_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'POC decision binding has changed' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION ors_poc.preserve_case_binding()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF OLD.owner_id = OLD.reviewer_id
        OR EXISTS (SELECT 1 FROM ors_poc.grant_record AS g WHERE g.case_id = OLD.id)
    THEN
        IF TG_OP = 'DELETE' OR
            (NEW.id, NEW.tenant_id, NEW.owner_id, NEW.reviewer_id, NEW.payload)
                IS DISTINCT FROM
            (OLD.id, OLD.tenant_id, OLD.owner_id, OLD.reviewer_id, OLD.payload)
        THEN
            RAISE EXCEPTION 'POC case identity and payload are immutable' USING ERRCODE = '42501';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION ors_poc.preserve_granted_proposal()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM ors_poc.grant_record AS g WHERE g.case_id = OLD.case_id)
        AND (TG_OP = 'DELETE' OR NEW IS DISTINCT FROM OLD)
    THEN
        RAISE EXCEPTION 'POC proposal binding is immutable' USING ERRCODE = '42501';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION ors_poc.issue_grant(
    target_case uuid, target_version integer, target_handle_digest text,
    target_action text, target_destination text, target_decision text, verified_host text
)
RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    requested ors_poc.grant_record%ROWTYPE;
BEGIN
    SELECT c.id, c.payload, p.proposal_version, p.decision_handle_digest, target_decision,
        least(p.decision_expires_at, statement_timestamp() + interval '5 minutes')
    INTO requested
    FROM ors_poc.scope AS s
    JOIN pg_catalog.pgaadauth_list_principals(false)
        AS principal(rolename, principaltype, objectid, tenantid, ismfa, isadmin)
        ON principal.rolename = session_user
    JOIN public.wf_cases AS c ON c.id = target_case
    JOIN public.order_resolution_proposals AS p ON p.case_id = c.id AND p.is_current
    WHERE session_user = current_user AND s.database_name = current_database()
        AND s.database_host = verified_host
        AND principal.principaltype = 'user' AND principal.isadmin
        AND principal.objectid::text = s.operator_oid::text
        AND principal.tenantid::text = s.tenant_id::text
        AND c.tenant_id = s.tenant_id::text
        AND c.owner_id = s.operator_oid::text AND c.reviewer_id = c.owner_id
        AND c.status = 'pending' AND c.checkpoint_id IS NULL
        AND p.tenant_id = c.tenant_id AND p.owner_id = c.owner_id AND p.reviewer_id = c.reviewer_id
        AND p.approval_required AND p.decision_channel = 'foundry-responses'
        AND p.proposal_version = target_version
        AND p.decision_handle_digest = target_handle_digest
        AND p.decision_handle_digest = encode(sha256(convert_to(c.request_id, 'UTF8')), 'hex')
        AND p.decision_expires_at > statement_timestamp()
        AND p.action = target_action AND p.destination_id = target_destination
        AND (p.action, p.destination_id) IN (
            ('partial_refund_10', 'synthetic-refund'),
            ('replacement_shipment', 'synthetic-fulfillment')
        )
        AND c.payload #>> '{proposal,action}' = p.action
        AND c.payload #>> '{proposal,destination_id}' = p.destination_id
        AND c.payload #>> '{proposal,input_digest}' = p.input_digest
        AND target_decision IN ('approved', 'rejected')
    FOR UPDATE OF c, p;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    INSERT INTO ors_poc.grant_record VALUES (requested.*)
    ON CONFLICT (case_id) DO NOTHING;
    RETURN EXISTS (
        SELECT 1 FROM ors_poc.grant_record AS g
        WHERE g.case_id = target_case
            AND (g.payload, g.proposal_version, g.handle_digest, g.decision) =
                (requested.payload, target_version, target_handle_digest, target_decision)
            AND g.expires_at > statement_timestamp()
    );
END
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ors_poc FROM PUBLIC;
CREATE TRIGGER ors_poc_audit_self_decision AFTER INSERT ON public.order_resolution_decisions
    FOR EACH ROW EXECUTE FUNCTION ors_poc.audit_self_decision();
CREATE TRIGGER ors_poc_preserve_case_binding BEFORE UPDATE OR DELETE ON public.wf_cases
    FOR EACH ROW EXECUTE FUNCTION ors_poc.preserve_case_binding();
CREATE TRIGGER ors_poc_preserve_granted_proposal BEFORE UPDATE OR DELETE
    ON public.order_resolution_proposals
    FOR EACH ROW EXECUTE FUNCTION ors_poc.preserve_granted_proposal();
ALTER TABLE public.order_resolution_decisions ENABLE ALWAYS TRIGGER ors_poc_audit_self_decision;
ALTER TABLE public.wf_cases ENABLE ALWAYS TRIGGER ors_poc_preserve_case_binding;
ALTER TABLE public.order_resolution_proposals ENABLE ALWAYS TRIGGER ors_poc_preserve_granted_proposal;
GRANT USAGE ON SCHEMA ors_poc TO :"runtime_role";
GRANT EXECUTE ON FUNCTION ors_poc.operator_allowed(text, text, text) TO :"runtime_role";
GRANT EXECUTE ON FUNCTION ors_poc.decision_allowed(uuid, text, text, text, boolean, text)
    TO :"runtime_role";
COMMIT;
