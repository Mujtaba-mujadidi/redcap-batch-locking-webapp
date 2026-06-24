import type { ReactNode } from "react";

type PageHeaderProps = {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: PageHeaderProps) {
  return (
    <section className="workspace-hero workspace-hero-actions">
      <div>
        <p className="mini-label">{eyebrow}</p>
        <h1 className="section-title">{title}</h1>
        {description ? <p className="section-subtitle">{description}</p> : null}
      </div>
      {actions ? <div className="toolbar-actions">{actions}</div> : null}
    </section>
  );
}
