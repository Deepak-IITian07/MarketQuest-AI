type Tone = "up" | "down" | "neutral";

type Props = {
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
};

export default function MetricTile({ label, value, hint, tone = "neutral" }: Props) {
  return (
    <div className={`metric metric-${tone}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
      {hint && <span className="metric-hint">{hint}</span>}
    </div>
  );
}
