import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CalendarClock, CheckCircle2, Clock3, Pause, Play, RefreshCw } from "lucide-react";
import api from "./services/api";

function WorkflowDashboard() {
  const [scheduler, setScheduler] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyJob, setBusyJob] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [jobsResponse, historyResponse] = await Promise.all([
        api.get("/workflows/jobs"),
        api.get("/workflows/history?limit=20"),
      ]);
      setScheduler(jobsResponse.data.scheduler);
      setJobs(jobsResponse.data.jobs || []);
      setExecutions(historyResponse.data.executions || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to load workflow status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { Promise.resolve().then(load); }, [load]);

  const hasActiveJobs = jobs.some((job) => job.is_running || job.status === "queued");
  useEffect(() => {
    if (!hasActiveJobs) return undefined;
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, load]);

  async function performAction(job, action) {
    setBusyJob(job.job_id);
    setError("");
    setNotice("");
    try {
      if (action === "run") {
        await api.post(`/workflows/jobs/${encodeURIComponent(job.job_id)}/run`);
        setNotice(`${job.name} was queued for a manual run.`);
      } else {
        await api.post(`/workflows/jobs/${encodeURIComponent(job.job_id)}/${action}`);
        setNotice(`${job.name} ${action === "pause" ? "paused" : "resumed"}.`);
      }
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || `Unable to ${action} this workflow.`);
    } finally {
      setBusyJob(null);
    }
  }

  function requestRun(job) {
    const confirmed = window.confirm(
      `Run “${job.name}” now using current ShopSense data? This may take a few minutes.`
    );
    if (confirmed) performAction(job, "run");
  }

  if (loading) {
    return <section className="workflow-page"><div className="analytics-message" role="status">Loading workflow status…</div></section>;
  }

  if (error && jobs.length === 0) {
    return (
      <section className="workflow-page">
        <div className="workflow-heading"><div><h2>Automated Workflows</h2><p>Manage scheduled analytics jobs.</p></div><button className="secondary-button" onClick={load}><RefreshCw size={16} /> Retry</button></div>
        <div className="analytics-error" role="alert"><AlertCircle size={18} /> {error}</div>
      </section>
    );
  }

  return (
    <section className="workflow-page" aria-label="Automated analytics workflows">
      <div className="workflow-heading">
        <div><h2>Automated Workflows</h2><p>Review schedules, run jobs, and inspect recent execution history.</p></div>
        <button className="secondary-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>

      {notice && <div className="workflow-feedback success" role="status"><CheckCircle2 size={17} />{notice}</div>}
      {error && <div className="analytics-error" role="alert"><AlertCircle size={18} />{error}</div>}

      <div className="workflow-status-card analytics-card">
        <div><span className={`workflow-status-dot ${scheduler?.running ? "online" : "offline"}`} />
          <strong>Scheduler {scheduler?.status || "unknown"}</strong></div>
        <span>Timezone: {scheduler?.timezone || "—"}</span>
        {scheduler?.message && <p role="status">{scheduler.message}</p>}
        <p>Execution history is held in memory and clears when the API process restarts.</p>
      </div>

      {jobs.length === 0 ? (
        <div className="analytics-card workflow-empty"><CalendarClock size={28} /><h3>No workflow jobs are configured</h3><p>Configured jobs will appear here when available.</p></div>
      ) : (
        <div className="workflow-job-grid">
          {jobs.map((job) => (
            <article className="analytics-card workflow-job" key={job.job_id}>
              <div className="workflow-job-title"><div><h3>{job.name}</h3><p>{job.description}</p></div><span className={`workflow-job-badge ${job.status}`}>{job.status.replaceAll("_", " ")}</span></div>
              <dl className="workflow-job-details">
                <div><dt>Frequency</dt><dd>{job.schedule}</dd></div>
                <div><dt>Last run</dt><dd>{formatDate(job.last_execution_time, scheduler?.timezone)}</dd></div>
                <div><dt>Next scheduled run</dt><dd>{formatDate(job.next_execution_time, scheduler?.timezone)}</dd></div>
                <div><dt>Last result</dt><dd>{job.last_execution_status || "No executions yet"}</dd></div>
              </dl>
              {job.last_result_summary && <p className="workflow-summary">{job.last_result_summary}</p>}
              {job.last_error && <p className="workflow-error" role="alert">{job.last_error}</p>}
              <div className="workflow-actions">
                <button className="primary-button" onClick={() => requestRun(job)} disabled={busyJob === job.job_id || job.is_running || job.status === "queued"}>
                  <Play size={15} /> {busyJob === job.job_id ? "Submitting…" : "Run Now"}
                </button>
                {job.status === "paused" ? (
                  <button className="secondary-button" onClick={() => performAction(job, "resume")} disabled={busyJob === job.job_id || !scheduler?.running}><Play size={15} /> Resume</button>
                ) : (
                  <button className="secondary-button" onClick={() => performAction(job, "pause")} disabled={busyJob === job.job_id || !scheduler?.running}><Pause size={15} /> Pause</button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <section className="analytics-card workflow-history">
        <div className="workflow-history-heading"><div><h3>Recent execution history</h3><p>Most recent {executions.length} execution{executions.length === 1 ? "" : "s"}</p></div><Clock3 size={20} /></div>
        {executions.length === 0 ? <div className="workflow-empty-inline"><p>No workflow executions have been recorded yet.</p></div> : (
          <div className="workflow-history-list">
            {executions.map((execution) => (
              <article className="workflow-history-row" key={execution.execution_id}>
                <div className="workflow-history-main"><strong>{execution.job_name}</strong><span>{formatDate(execution.started_at, scheduler?.timezone)} · {execution.trigger}</span></div>
                <span className={`workflow-job-badge ${execution.status}`}>{execution.status}</span>
                <span>{execution.duration_seconds == null ? "—" : `${execution.duration_seconds}s`}</span>
                {execution.result_summary && <p>{execution.result_summary}</p>}
                {execution.error && <p className="workflow-error">{execution.error}</p>}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}

function formatDate(value, timeZone) {
  return value ? new Date(value).toLocaleString(undefined, timeZone ? { timeZone } : undefined) : "—";
}

export default WorkflowDashboard;
