"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Load data on mount and whenever `key` changes. `reload` refetches without
 *  clearing the current data, so screens do not flicker after actions. */
export function useLoad<T>(fn: () => Promise<T>, key: string, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(enabled);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const seq = useRef(0);

  const run = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const d = await fnRef.current();
      if (my === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetching on key change is the intent
    void run();
  }, [key, enabled, run]);

  return { data, error, loading, reload: run, setData };
}
