type PanelStateProps = {
  tone?: "loading" | "error" | "empty";
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export default function PanelState({
  tone = "loading",
  title,
  message,
  actionLabel,
  onAction,
}: PanelStateProps) {
  return (
    <div className={`panel-state panel-state-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {tone === "loading" && <span className="spinner" aria-hidden="true" />}
      <p className="panel-state-title">{title}</p>
      {message && <p className="panel-state-message">{message}</p>}
      {actionLabel && onAction && (
        <button type="button" className="btn" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
