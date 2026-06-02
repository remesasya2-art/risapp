import { useEffect, useRef, useState } from 'react';

/**
 * Animated number ticker.
 * Returns the current animated value (number) that ticks from 0 to `target`
 * using an ease-out curve over `duration` ms.
 *
 * Usage:
 *   const value = useCountUp(user.balance, 900);
 *   return <span>{fmt(value)}</span>;
 */
export default function useCountUp(target = 0, duration = 900) {
  const [value, setValue] = useState(target);
  const rafRef = useRef(null);
  const fromRef = useRef(target);
  const startRef = useRef(0);

  useEffect(() => {
    const goal = Number(target) || 0;
    // Animate from current displayed value to new goal
    fromRef.current = value;
    startRef.current = 0;

    const tick = (ts) => {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(1, elapsed / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      const next = fromRef.current + (goal - fromRef.current) * eased;
      setValue(next);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(goal);
      }
    };

    if (Math.abs(goal - fromRef.current) < 0.001) {
      setValue(goal);
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return value;
}
