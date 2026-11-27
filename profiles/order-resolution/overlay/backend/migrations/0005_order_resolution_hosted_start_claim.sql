ALTER TABLE order_resolution_hosted_operations
    ADD COLUMN IF NOT EXISTS first_request_id UUID;
