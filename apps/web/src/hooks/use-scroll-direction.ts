import { useState, useEffect } from 'react';

/**
 * Scroll direction hook
 * Returns valid scroll direction ('up' or 'down') and whether we are at the top.
 * Optimized with a threshold to avoid jitter and ensure smooth transitions.
 */
export function useScrollDirection(threshold = 10) {
  const [scrollDir, setScrollDir] = useState<'up' | 'down'>('up');
  const [isAtTop, setIsAtTop] = useState(true);

  useEffect(() => {
    let lastScrollY = window.scrollY;
    let ticking = false;

    const updateScrollDir = () => {
      const scrollY = window.scrollY;

      // Always update 'isAtTop' status
      // Use a small constant (e.g. 5px) to detect if we are strictly at the top
      // This is independent of the threshold for direction change
      const atTop = scrollY < 5;
      setIsAtTop(atTop);

      const diff = scrollY - lastScrollY;
      
      // Update direction if threshold met
      if (Math.abs(diff) >= threshold) {
        // Special rule: if we are near the top (e.g. < 50px), always show the header (direction up)
        // This prevents the header from hiding if the user starts scrolling down from very top quickly
        // but hasn't gone far enough to warrant hiding it yet, or ensures it pops back up.
        if (scrollY < 50) {
            setScrollDir('up');
        } else {
            setScrollDir(diff > 0 ? 'down' : 'up');
        }
        lastScrollY = scrollY > 0 ? scrollY : 0;
      }
      
      ticking = false;
    };

    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(updateScrollDir);
        ticking = true;
      }
    };

    window.addEventListener('scroll', onScroll);

    return () => window.removeEventListener('scroll', onScroll);
  }, [threshold]);

  return { scrollDir, isAtTop };
}
