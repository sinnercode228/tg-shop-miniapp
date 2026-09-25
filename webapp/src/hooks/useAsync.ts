import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

interface Result<T> {
  token: string;
  data: T | null;
  error: Error | null;
}

/**
 * Minimal data-fetching hook. Re-runs when `key` changes or `reload()` is called,
 * ignores stale responses and keeps the previous data for the same key while reloading.
 */
export function useAsync<T>(fn: () => Promise<T>, key: string): AsyncState<T> {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const token = `${key}#${nonce}`;

  useEffect(() => {
    let alive = true;
    fnRef.current().then(
      (data) => alive && setResult({ token, data, error: null }),
      (e: unknown) =>
        alive &&
        setResult({ token, data: null, error: e instanceof Error ? e : new Error(String(e)) }),
    );
    return () => {
      alive = false;
    };
  }, [token]);

  const sameKey = result !== null && result.token.slice(0, result.token.lastIndexOf('#')) === key;
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return {
    data: sameKey ? result.data : null,
    error: sameKey ? result.error : null,
    loading: result?.token !== token,
    reload,
  };
}
