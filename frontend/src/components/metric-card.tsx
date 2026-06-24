type MetricCardProps = {
  label: string;
  value: number | string;
  detail?: string;
};

export function MetricCard({ label, value, detail }: MetricCardProps) {
  return (
    <article className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {detail ? <p className="compact-copy">{detail}</p> : null}
    </article>
  );
}
