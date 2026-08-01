import { useRef, useState } from "react";

export default function UploadForm({ onUpload, disabled }) {
  const inputRef = useRef(null);
  const [fileName, setFileName] = useState(null);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) setFileName(file.name);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const file = inputRef.current?.files?.[0];
    if (file) onUpload(file);
  };

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <label className="file-drop" htmlFor="video-input">
        <input
          id="video-input"
          type="file"
          accept="video/*"
          ref={inputRef}
          onChange={handleFileChange}
          disabled={disabled}
        />
        <span>{fileName ? fileName : "Click to choose a squat video (MP4, side view)"}</span>
      </label>
      <button type="submit" disabled={disabled || !fileName}>
        {disabled ? "Processing…" : "Analyze My Form"}
      </button>
    </form>
  );
}
