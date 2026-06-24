type BrandMarkProps = {
  className?: string;
};

export function BrandMark({ className }: BrandMarkProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <ellipse cx="10" cy="5" rx="5.5" ry="2.5" />
      <path d="M4.5 5v4c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V5" />
      <path d="M4.5 9v4c0 1.4 2.5 2.5 5.5 2.5 1 0 1.9-.1 2.7-.4" />
      <path d="M16.5 14v-1a2.5 2.5 0 1 1 5 0v1" />
      <rect x="15" y="14" width="8" height="6.5" rx="1.6" />
    </svg>
  );
}
