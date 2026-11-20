-- batch_process_status.retry_count: transient-retry counter used by the poller.
-- Apply to the production DB (Cloud SQL Studio) BEFORE deploying the functions.
-- Without this column the loader fails every run with 500 and the poller cannot
-- write PENDING/FAILED. Safe to run more than once.
-- See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 6.
ALTER TABLE batch_process_status
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

-- Check:
-- SELECT column_name, data_type, column_default, is_nullable
--   FROM information_schema.columns
--  WHERE table_name = 'batch_process_status' AND column_name = 'retry_count';
