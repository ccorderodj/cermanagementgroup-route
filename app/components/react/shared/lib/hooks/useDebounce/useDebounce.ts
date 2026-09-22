import { useCallback, useRef } from 'react';

/**
 * Hook that allows you to cancel a previous function call until the delay expires
 * @param callback
 * @param delay - delay in ms
 */
export function useDebounce(callback: (...args: any[]) => void, delay: number) {
    // React 19 exige valor inicial en useRef; tiparlo evita además el cast.
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

    return useCallback((...args: any[]) => {
        if (timer.current) {
            clearTimeout(timer.current);
        }
        timer.current = setTimeout(() => {
            callback(...args);
        }, delay);
    }, [callback, delay]);
}
