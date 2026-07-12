"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/**
 * Keeps page filters in the URL's query string instead of component-local
 * state, so the browser's own history handles "remember my filters" for
 * free: clicking into a stock and hitting Back restores the exact URL
 * (filters and all) instead of remounting the page with hardcoded defaults.
 *
 * Uses router.replace (not push) so changing a filter never adds its own
 * history entry -- only real navigations (e.g. clicking a ticker) do, which
 * is what makes Back land on "the page as you left it" rather than
 * stepping back through every filter tweak one at a time.
 */
export function useQueryState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const getParam = useCallback(
    (key: string): string | null => searchParams.get(key),
    [searchParams]
  );

  const setParams = useCallback(
    (updates: Record<string, string | number | boolean | null | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === undefined || value === "") {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams]
  );

  return { getParam, setParams };
}
