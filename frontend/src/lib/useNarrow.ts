import { useEffect, useState } from "react";

/** 屏幕宽度是否小于给定值（默认 768：手机）。随窗口大小与屏幕旋转更新。 */
export function useNarrow(max = 768): boolean {
  const q = () => window.matchMedia(`(max-width: ${max - 1}px)`).matches;
  const [narrow, setNarrow] = useState(q);
  useEffect(() => {
    const m = window.matchMedia(`(max-width: ${max - 1}px)`);
    const f = () => setNarrow(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, [max]);
  return narrow;
}
