from __future__ import annotations


def format_prometheus_metrics(
    *,
    uptime_seconds: float,
    active_jobs: int,
    completed_jobs: int,
    failed_jobs: int,
    memory_rss_mb: float,
    database_backend: str,
    database_status: str,
    storage_backend: str,
) -> str:
    """Format core system metrics according to the Prometheus text-based exposition format 0.0.4."""
    lines = [
        "# HELP cretona_uptime_seconds Total time the server has been running in seconds.",
        "# TYPE cretona_uptime_seconds gauge",
        f"cretona_uptime_seconds {uptime_seconds:.2f}",
        "",
        "# HELP cretona_memory_rss_bytes Resident memory size in bytes.",
        "# TYPE cretona_memory_rss_bytes gauge",
        f"cretona_memory_rss_bytes {int(memory_rss_mb * 1024 * 1024)}",
        "",
        "# HELP cretona_video_jobs_total Total video generation jobs by terminal status.",
        "# TYPE cretona_video_jobs_total counter",
        f'cretona_video_jobs_total{{status="completed"}} {completed_jobs}',
        f'cretona_video_jobs_total{{status="failed"}} {failed_jobs}',
        "",
        "# HELP cretona_active_jobs Current video generation jobs running.",
        "# TYPE cretona_active_jobs gauge",
        f"cretona_active_jobs {active_jobs}",
        "",
        "# HELP cretona_database_status Database connectivity state (1=healthy, 0=unhealthy).",
        "# TYPE cretona_database_status gauge",
        (
            f'cretona_database_status{{backend="{database_backend}"}} '
            f'{1 if database_status == "healthy" else 0}'
        ),
        "",
        "# HELP cretona_storage_backend Storage provider in use.",
        "# TYPE cretona_storage_backend gauge",
        f'cretona_storage_backend{{provider="{storage_backend}"}} 1',
        "",
    ]
    return "\n".join(lines)
