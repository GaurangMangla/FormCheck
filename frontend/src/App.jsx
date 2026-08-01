import { useState } from "react";
import UploadForm from "./components/UploadForm";
import VideoResult from "./components/VideoResult";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [status, setStatus] = useState("idle"); // idle | uploading | analyzing | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleUpload = async (file) => {
    setStatus("uploading");
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("exercise", "squat");

    try {
      setStatus("analyzing");
      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `Request failed with status ${res.status}`);
      }

      const data = await res.json();
      setResult(data);
      setStatus("done");
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setStatus("error");
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>AI Fitness Form Checker</h1>
        <p className="subtitle">
          Upload a side-view video of your squat. We'll track your joints, flag form issues,
          and show you exactly where they happened.
        </p>
      </header>

      <main>
        <UploadForm onUpload={handleUpload} disabled={status === "uploading" || status === "analyzing"} />

        {status === "uploading" && <p className="status-msg">Uploading video…</p>}
        {status === "analyzing" && <p className="status-msg">Analyzing your form — this can take a moment…</p>}
        {status === "error" && <p className="status-msg error">Error: {error}</p>}

        {status === "done" && result && (
          <VideoResult result={result} apiBase={API_BASE} />
        )}
      </main>

      <footer className="app-footer">
        <p>Built with React, FastAPI, and MediaPipe Pose. For form guidance only — not a substitute for a qualified coach.</p>
      </footer>
    </div>
  );
}
