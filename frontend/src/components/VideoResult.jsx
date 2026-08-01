export default function VideoResult({ result, apiBase }) {
  const { summary, reps, annotated_video_url, side_analyzed } = result;

  return (
    <div className="result-panel">
      <video
        key={annotated_video_url}
        controls
        src={`${apiBase}${annotated_video_url}`}
        className="result-video"
      />

      <div className="feedback-panel">
        <h2>Feedback</h2>
        <p className="summary">{summary}</p>
        {side_analyzed && (
          <p className="side-note">Analyzed from your {side_analyzed.toLowerCase()} side.</p>
        )}

        {reps.length > 0 && (
          <ul className="rep-list">
            {reps.map((rep) => (
              <li key={rep.rep_number} className={rep.is_good ? "rep-good" : "rep-bad"}>
                <div className="rep-header">
                  <strong>Rep {rep.rep_number}</strong>
                  <span>{rep.timestamp_seconds != null ? `${rep.timestamp_seconds}s` : ""}</span>
                </div>
                <div className="rep-metrics">
                  Knee angle: {rep.min_knee_angle}° &middot; Torso lean: {rep.torso_angle_at_bottom}°
                </div>
                {rep.is_good ? (
                  <div className="rep-status good">Good form</div>
                ) : (
                  <ul className="issue-list">
                    {rep.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
