/** The SurgeSight mark: two swells, the second fainter. */
export function Logo({ className = 'size-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--primary)" />
      <path d="M7 18c3.5-5 7-5 9-1.6s5.5 3.4 9-1.6" fill="none" stroke="var(--primary-foreground)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M7 23.5c3.5-3.6 7-3.6 9-.9s5.5 2.7 9-.9" fill="none" stroke="var(--primary-foreground)" strokeOpacity=".55" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}
