type ReportExportOverlayProps = {
  isOpen: boolean;
  title: string;
  copy: string;
  stage: string;
  percent: number;
};

export function ReportExportOverlay({
  isOpen,
  title,
  copy,
  stage,
  percent,
}: ReportExportOverlayProps) {
  return (
    <div className="progress-overlay" hidden={!isOpen}>
      <div className="progress-dialog" role="status" aria-live="polite" aria-atomic="true">
        <div className="import-progress-heading">
          <span className="loader-spinner" aria-hidden="true"></span>
          <div>
            <p className="mini-label">Exporting Report</p>
            <h4 className="progress-title">{title}</h4>
          </div>
        </div>
        <p className="compact-copy">{copy}</p>
        <div className="progress-meter" aria-hidden="true">
          <div className="progress-meter-fill" style={{ width: `${percent}%` }}></div>
        </div>
        <p className="progress-stage-copy">{stage}</p>
      </div>
    </div>
  );
}
