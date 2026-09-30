/** The SurgeSight mark: a cyclone with a signal arc, white on blue. */
export function Logo({ className = 'size-6' }: { className?: string }) {
  return <img src="/logo.png" alt="" aria-hidden className={`${className} object-contain`} draggable={false} />
}
