import * as React from 'react';
import * as PopoverPrimitive from '@radix-ui/react-popover';
import { cn } from '@/shared/lib/utils/utils';

// Extend Radix UI's Popover props
type PopoverImproveProps = React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Root> & {
    closeAutomatically?: boolean;
};

// Create a wrapper component that doesn't need forwardRef
const PopoverImprove: React.FC<PopoverImproveProps> = ({ children, closeAutomatically = false, ...props }) => {
    const [open, setOpen] = React.useState(false);
    const contentRef = React.useRef<HTMLDivElement>(null);

    // Handle automatic closing
    React.useEffect(() => {
        if (!closeAutomatically || !open) return;

        const handleClick = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (contentRef.current?.contains(target)) {
                let shouldClose = false;

                // Check for CommandItem
                if (target.closest('[role="option"]')) {
                    shouldClose = true;
                }

                // Check for Calendar day selection
                if (target.closest('[role="gridcell"]') ||
                    target.closest('.rdp-day') ||
                    target.closest('.react-day-picker__day') ||
                    target.closest('button[data-day]') ||
                    target.closest('[data-selected="true"]')) {
                    // Make sure it's actually a button/clickable element
                    const clickableElement = target.closest('button, [role="button"]');
                    if (clickableElement) {
                        shouldClose = true;
                    }
                }

                // Check for data-autoclose attribute
                if (target.closest('[data-autoclose="true"]')) {
                    shouldClose = true;
                }

                // Check for any button inside calendar
                if (target.closest('.rdp-day_button') || target.closest('[class*="day"]')) {
                    shouldClose = true;
                }

                if (shouldClose) {
                    setTimeout(() => setOpen(false), 50);
                }
            }
        };

        // Use mousedown instead of click to catch the event earlier
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [closeAutomatically, open]);

    // Enhance children with ref - fixed spread issue
    const enhancedChildren = React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
            if (child.type === PopoverImproveContent) {
                // Clone the element with additional props
                return React.cloneElement(child, {
                    ref: contentRef,
                    ...(child.props || {}) // Ensure props is an object
                } as any);
            }
        }
        return child;
    });

    return (
        <PopoverPrimitive.Root open={open} onOpenChange={setOpen} {...props}>
            {enhancedChildren}
        </PopoverPrimitive.Root>
    );
};
PopoverImprove.displayName = 'PopoverImprove';

const PopoverImproveTrigger = PopoverPrimitive.Trigger;
const PopoverImproveAnchor = PopoverPrimitive.Anchor;

type PopoverImproveContentProps = React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>;

const PopoverImproveContent = React.forwardRef<
    React.ElementRef<typeof PopoverPrimitive.Content>,
    PopoverImproveContentProps
>(({ className, align = 'center', sideOffset = 4, ...props }, ref) => (
    <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
            ref={ref}
            align={align}
            sideOffset={sideOffset}
            className={cn(
                'z-50 w-72 rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
                className,
            )}
            {...props}
        />
    </PopoverPrimitive.Portal>
));
PopoverImproveContent.displayName = PopoverPrimitive.Content.displayName;

export {
    PopoverImprove,
    PopoverImproveTrigger,
    PopoverImproveContent,
    PopoverImproveAnchor,
};