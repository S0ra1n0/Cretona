-- 011: Add composite indexes for high-throughput query optimization
-- Accelerates audit log filters, provider webhook queries, and soft-delete scans.

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_action_created
ON public.admin_audit_logs(action, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_actor_created
ON public.admin_audit_logs(actor_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_video_projects_provider_job
ON public.video_projects(provider, provider_job_id)
WHERE provider_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_video_projects_deleted_user
ON public.video_projects(deleted_at, user_id);
