DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'order_resolution_hosted_operations'::regclass
            AND conname = 'order_resolution_hosted_operations_outcome_check'
    ) THEN
        ALTER TABLE order_resolution_hosted_operations
            DROP CONSTRAINT order_resolution_hosted_operations_status_check,
            DROP CONSTRAINT order_resolution_hosted_operations_check,
            ADD CONSTRAINT order_resolution_hosted_operations_outcome_check CHECK (
                (status IN ('acknowledged', 'failed') AND remote_id IS NOT NULL)
                OR (status IN ('pending', 'rejected', 'unknown') AND remote_id IS NULL)
            );
    END IF;
END
$$;
