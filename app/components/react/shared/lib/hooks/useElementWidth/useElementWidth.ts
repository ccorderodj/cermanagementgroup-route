import { useState, useLayoutEffect, useMemo } from 'react';

const useElementWidth = (elementId: string, offset = 70): [number] => {
    const [elementWidth, setElementWidth] = useState(0);

    useLayoutEffect(() => {
        const updateWidth = () => {
            const element = document.getElementById(elementId);
            if (element) {
                setElementWidth(element.clientWidth - offset);
            }
        };

        const resizeObserver = new ResizeObserver(() => {
            updateWidth();
        });

        const element = document.getElementById(elementId);
        if (element) {
            resizeObserver.observe(element);
        }

        // Initial width calculation
        updateWidth();

        return () => {
            if (element) {
                resizeObserver.unobserve(element);
            }
        };
    }, [elementId, offset]);

    return useMemo(
        () => [
            elementWidth,
        ],
        [elementWidth],
    );
};

export default useElementWidth;
