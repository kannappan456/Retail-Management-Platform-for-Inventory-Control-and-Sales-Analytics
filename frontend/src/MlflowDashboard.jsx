import { useCallback, useEffect, useState } from "react";
import api from "./services/api";

function MlflowDashboard() {
  const [status, setStatus] = useState(null);
  const [experiments, setExperiments] = useState([]);
  const [models, setModels] = useState(null);
  const [runsByExperiment, setRunsByExperiment] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [statusResponse, experimentResponse, modelResponse] = await Promise.all([
        api.get("/mlflow/status"),
        api.get("/mlflow/experiments"),
        api.get("/mlflow/models"),
      ]);
      setStatus(statusResponse.data);
      setModels(modelResponse.data);
      if (!statusResponse.data.available) {
        setExperiments([]);
        setRunsByExperiment({});
        return;
      }
      if (!experimentResponse.data.available) {
        throw new Error(experimentResponse.data.message || "Unable to load MLflow experiments.");
      }
      const experimentList = experimentResponse.data.experiments || [];
      setExperiments(experimentList);
      const runResponses = await Promise.all(experimentList.map((experiment) =>
        api.get(`/mlflow/experiments/${encodeURIComponent(experiment.experiment_id)}/runs?limit=10`)
      ));
      setRunsByExperiment(Object.fromEntries(experimentList.map((experiment, index) => [
        experiment.experiment_id,
        runResponses[index].data.runs || [],
      ])));
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Unable to load MLflow tracking information.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { Promise.resolve().then(load); }, [load]);

  const formatTimestamp = (value) => value == null
    ? "—"
    : new Date(Number(value)).toLocaleString();
  const formatValue = (value) => typeof value === "number"
    ? value.toLocaleString(undefined, { maximumFractionDigits: 5 })
    : String(value);

  if (loading) return <section className="mlflow-page"><div className="analytics-message" role="status">Loading experiment tracking…</div></section>;
  if (error) return <section className="mlflow-page"><div className="mlflow-heading"><div><h2>MLflow &amp; Model Tracking</h2><p>Experiment runs and model evaluation history.</p></div><button className="secondary-button" onClick={load}>Retry</button></div><div className="analytics-error" role="alert">{error}</div></section>;

  return (
    <section className="mlflow-page" aria-label="MLflow model tracking">
      <div className="mlflow-heading">
        <div><h2>MLflow &amp; Model Tracking</h2><p>Experiment runs, actual evaluation results, and model versions.</p></div>
        <button className="secondary-button" onClick={load}>Refresh</button>
      </div>

      {!status?.available ? (
        <div className="analytics-card mlflow-notice" role="status">
          <h3>Tracking unavailable</h3>
          <p>{status?.message || "MLflow is not configured or could not be reached."}</p>
          <p>Existing forecasting and segmentation continue to work without tracking.</p>
        </div>
      ) : (
        <>
          <div className="mlflow-status-row">
            <span className="analytics-live-badge">Tracking available</span>
            <span className={`mlflow-registry-badge ${status.registry_supported ? "supported" : "unsupported"}`}>
              {status.registry_supported ? "Model Registry available" : "Model Registry unsupported by current backend"}
            </span>
          </div>

          {experiments.length === 0 ? (
            <div className="analytics-card mlflow-notice" role="status">
              <h3>No ShopSense experiments yet</h3>
              <p>Experiments appear after an Admin runs demand forecasting, customer segmentation, or recommendation evaluation.</p>
            </div>
          ) : experiments.map((experiment) => {
            const runs = runsByExperiment[experiment.experiment_id] || [];
            return (
              <article className="analytics-card mlflow-experiment" key={experiment.experiment_id}>
                <div className="mlflow-experiment-heading">
                  <div><h3>{experiment.name}</h3><p>{runs.length} recent run{runs.length === 1 ? "" : "s"}</p></div>
                </div>
                {runs.length === 0 ? (
                  <p className="mlflow-muted">No runs recorded for this experiment.</p>
                ) : runs.map((run) => (
                  <details className="mlflow-run" key={run.run_id}>
                    <summary>
                      <span className="mlflow-run-name">{run.run_name || "Model evaluation"}</span>
                      <span>{formatTimestamp(run.start_time)}</span>
                      <span className="mlflow-run-status">{run.tags["evaluation.status"] || run.status}</span>
                    </summary>
                    <dl className="mlflow-run-meta">
                      <div><dt>Run ID</dt><dd>{run.run_id}</dd></div>
                      <div><dt>Training status</dt><dd>{run.tags["workflow.status"] || run.status}</dd></div>
                      <div><dt>Model</dt><dd>{run.tags["model.name"] || run.tags["model.type"] || "—"}</dd></div>
                      <div><dt>Registry</dt><dd>{run.tags["model.registry.version"] ? `Version ${run.tags["model.registry.version"]}` : run.tags["model.registry.status"] || "Not applicable"}</dd></div>
                    </dl>
                    {run.tags["evaluation.message"] && <p className="mlflow-muted">{run.tags["evaluation.message"]}</p>}
                    <div className="mlflow-data-grid">
                      <div><h4>Parameters</h4>{Object.keys(run.params).length ? <dl>{Object.entries(run.params).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl> : <p className="mlflow-muted">No parameters logged.</p>}</div>
                      <div><h4>Metrics</h4>{Object.keys(run.metrics).length ? <dl>{Object.entries(run.metrics).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{formatValue(value)}</dd></div>)}</dl> : <p className="mlflow-muted">No evaluation metrics were available for this run.</p>}</div>
                    </div>
                  </details>
                ))}
              </article>
            );
          })}

          <section className="analytics-card mlflow-models">
            <h3>Registered models</h3>
            {!models?.registry_supported ? (
              <p className="mlflow-muted">{models?.message || "The configured tracking backend does not support model registration."}</p>
            ) : models.models?.length ? models.models.map((model) => (
              <div className="mlflow-model" key={model.name}>
                <strong>{model.name}</strong>
                {model.versions.map((version) => <span key={`${model.name}-${version.version}`}>Version {version.version} · {version.status} · run {version.run_id}</span>)}
              </div>
            )) : <p className="mlflow-muted">No registered models or versions are available.</p>}
          </section>
        </>
      )}
    </section>
  );
}

export default MlflowDashboard;
