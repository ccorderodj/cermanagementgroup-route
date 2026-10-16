"use client"

import * as React from "react"
import { createPortal } from "react-dom"

import { cn } from "@/shared/lib/utils/utils"
import { buttonVariants } from "../Button/Button"

/* -----------------------------------------------------------------------------
 * Small utilities (shadcn-ish)
 * -------------------------------------------------------------------------- */

function composeEventHandlers<E>(
    theirHandler: ((event: E) => void) | undefined,
    ourHandler: (event: E) => void
) {
    return (event: E) => {
        theirHandler?.(event)
        // @ts-expect-error - works for SyntheticEvent/DOM events
        if (event?.defaultPrevented) return
        ourHandler(event)
    }
}

/**
 * Minimal "Slot" to support shadcn `asChild` pattern WITHOUT Radix.
 * Fixes: "className does not exist in type Partial<unknown> & Attributes"
 */
type SlotProps = {
    children: React.ReactElement<any>
} & Record<string, any>

function Slot({ children, ...props }: SlotProps) {
    const child = React.Children.only(children)

    return React.cloneElement(child, {
        ...props,
        className: cn(child.props?.className, props.className),
        style: { ...(child.props?.style ?? {}), ...(props.style ?? {}) },
    })
}

/* -----------------------------------------------------------------------------
 * Focus trap helpers
 * -------------------------------------------------------------------------- */

const FOCUSABLE =
    'a[href],area[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),iframe,object,embed,[contenteditable="true"],[tabindex]:not([tabindex="-1"])'

function getFocusable(container: HTMLElement) {
    return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true"
    )
}

/* -----------------------------------------------------------------------------
 * Context
 * -------------------------------------------------------------------------- */

type AlertDialogContextValue = {
    open: boolean
    setOpen: (next: boolean) => void
    titleId: string | null
    descriptionId: string | null
    setTitleId: (id: string | null) => void
    setDescriptionId: (id: string | null) => void
}

const AlertDialogContext = React.createContext<AlertDialogContextValue | null>(
    null
)

function useAlertDialog() {
    const ctx = React.useContext(AlertDialogContext)
    if (!ctx) throw new Error("AlertDialog components must be used within <AlertDialog />")
    return ctx
}

/* -----------------------------------------------------------------------------
 * Root (controlled/uncontrolled like shadcn wrappers)
 * -------------------------------------------------------------------------- */

type AlertDialogProps = {
    children: React.ReactNode
    open?: boolean
    defaultOpen?: boolean
    onOpenChange?: (open: boolean) => void
}

const AlertDialog = ({
    children,
    open,
    defaultOpen,
    onOpenChange,
}: AlertDialogProps) => {
    const [uncontrolledOpen, setUncontrolledOpen] = React.useState<boolean>(
        defaultOpen ?? false
    )

    const isControlled = open !== undefined
    const actualOpen = isControlled ? (open as boolean) : uncontrolledOpen

    const setOpen = React.useCallback(
        (next: boolean) => {
            if (!isControlled) setUncontrolledOpen(next)
            onOpenChange?.(next)
        },
        [isControlled, onOpenChange]
    )

    const [titleId, setTitleId] = React.useState<string | null>(null)
    const [descriptionId, setDescriptionId] = React.useState<string | null>(null)

    const value = React.useMemo<AlertDialogContextValue>(
        () => ({
            open: actualOpen,
            setOpen,
            titleId,
            descriptionId,
            setTitleId,
            setDescriptionId,
        }),
        [actualOpen, setOpen, titleId, descriptionId]
    )

    return <AlertDialogContext.Provider value={value}>{children}</AlertDialogContext.Provider>
}

type AsChildProps = { asChild?: boolean }

/* -----------------------------------------------------------------------------
 * Trigger
 * -------------------------------------------------------------------------- */

type AlertDialogTriggerProps = React.ComponentPropsWithoutRef<"button"> & AsChildProps

const AlertDialogTrigger = React.forwardRef<
    HTMLButtonElement,
    AlertDialogTriggerProps
>(({ asChild, onClick, className, ...props }, ref) => {
    const { setOpen } = useAlertDialog()
    const Comp: any = asChild ? Slot : "button"

    return (
        <Comp
            ref={ref}
            className={className}
            onClick={composeEventHandlers(onClick, () => setOpen(true))}
            {...props}
        />
    )
})
AlertDialogTrigger.displayName = "AlertDialogTrigger"

/* -----------------------------------------------------------------------------
 * Portal
 * -------------------------------------------------------------------------- */

const AlertDialogPortal = ({ children }: { children: React.ReactNode }) => {
    const [mounted, setMounted] = React.useState(false)
    React.useEffect(() => setMounted(true), [])
    if (!mounted) return null
    return createPortal(children, document.body)
}
AlertDialogPortal.displayName = "AlertDialogPortal"

/* -----------------------------------------------------------------------------
 * Overlay
 * IMPORTANT FIXES FOR NESTED MODALS (e.g. inside shadcn Dialog):
 * - pointer-events-auto: overrides body { pointer-events: none }
 * - higher z-index than the parent dialog (shadcn Dialog uses z-50)
 * - does NOT close on click (AlertDialog behavior)
 * -------------------------------------------------------------------------- */

type AlertDialogOverlayProps = React.HTMLAttributes<HTMLDivElement>

const AlertDialogOverlay = React.forwardRef<HTMLDivElement, AlertDialogOverlayProps>(
    ({ className, ...props }, ref) => {
        const { open } = useAlertDialog()
        if (!open) return null

        return (
            <div
                ref={ref}
                aria-hidden="true"
                data-state="open"
                className={cn(
                    "fixed inset-0 z-[60] bg-black/80 pointer-events-auto",
                    "data-[state=open]:animate-in data-[state=closed]:animate-out",
                    "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                    className
                )}
                {...props}
                // AlertDialog should not close on overlay click; just absorb it.
                onMouseDown={composeEventHandlers(props.onMouseDown, (e) => e.preventDefault())}
                onClick={composeEventHandlers(props.onClick, (e) => e.preventDefault())}
            />
        )
    }
)
AlertDialogOverlay.displayName = "AlertDialogOverlay"

/* -----------------------------------------------------------------------------
 * Content (portal + focus trap + escape + scroll lock)
 * IMPORTANT FIXES FOR NESTED MODALS:
 * - pointer-events-auto (body may be pointer-events: none)
 * - higher z-index than overlay
 * -------------------------------------------------------------------------- */

type AlertDialogContentProps = React.HTMLAttributes<HTMLDivElement>

const AlertDialogContent = React.forwardRef<HTMLDivElement, AlertDialogContentProps>(
    ({ className, onKeyDown, ...props }, ref) => {
        const { open, setOpen, titleId, descriptionId } = useAlertDialog()
        const localRef = React.useRef<HTMLDivElement | null>(null)

        React.useImperativeHandle(ref, () => localRef.current as HTMLDivElement)

        React.useEffect(() => {
            if (!open) return

            const prevActive = document.activeElement as HTMLElement | null

            // lock scroll (if nested, it will just keep it locked)
            const prevOverflow = document.body.style.overflow
            document.body.style.overflow = "hidden"

            // focus first focusable (or content)
            const node = localRef.current
            if (node) {
                const focusables = getFocusable(node)
                    ; (focusables[0] ?? node).focus()
            }

            const onDocKeyDown = (e: KeyboardEvent) => {
                if (e.key === "Escape") {
                    e.preventDefault()
                    setOpen(false)
                    return
                }

                if (e.key !== "Tab") return
                const node = localRef.current
                if (!node) return

                const focusables = getFocusable(node)
                if (focusables.length === 0) {
                    e.preventDefault()
                    node.focus()
                    return
                }

                const first = focusables[0]
                const last = focusables[focusables.length - 1]
                const active = document.activeElement as HTMLElement | null

                if (!e.shiftKey && active === last) {
                    e.preventDefault()
                    first.focus()
                } else if (e.shiftKey && (active === first || active === node)) {
                    e.preventDefault()
                    last.focus()
                }
            }

            document.addEventListener("keydown", onDocKeyDown)
            return () => {
                document.removeEventListener("keydown", onDocKeyDown)
                document.body.style.overflow = prevOverflow
                prevActive?.focus?.()
            }
        }, [open, setOpen])

        if (!open) return null

        return (
            <AlertDialogPortal>
                <AlertDialogOverlay />
                <div
                    ref={localRef}
                    role="alertdialog"
                    aria-modal="true"
                    aria-labelledby={titleId ?? undefined}
                    aria-describedby={descriptionId ?? undefined}
                    tabIndex={-1}
                    data-state="open"
                    className={cn(
                        "fixed left-[50%] top-[50%] z-[70] pointer-events-auto grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4",
                        "border bg-background p-6 shadow-lg duration-200 sm:rounded-lg",
                        "data-[state=open]:animate-in data-[state=closed]:animate-out",
                        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                        "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
                        "data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]",
                        "data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]",
                        className
                    )}
                    onKeyDown={onKeyDown}
                    // prevent clicks from bubbling out
                    onMouseDown={(e) => e.stopPropagation()}
                    onClick={(e) => e.stopPropagation()}
                    {...props}
                />
            </AlertDialogPortal>
        )
    }
)
AlertDialogContent.displayName = "AlertDialogContent"

/* -----------------------------------------------------------------------------
 * Header / Footer
 * -------------------------------------------------------------------------- */

const AlertDialogHeader = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div className={cn("flex flex-col space-y-2 text-center sm:text-left", className)} {...props} />
)
AlertDialogHeader.displayName = "AlertDialogHeader"

const AlertDialogFooter = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
        {...props}
    />
)
AlertDialogFooter.displayName = "AlertDialogFooter"

/* -----------------------------------------------------------------------------
 * Title / Description (register ids for aria)
 * -------------------------------------------------------------------------- */

type AlertDialogTitleProps = React.HTMLAttributes<HTMLHeadingElement>

const AlertDialogTitle = React.forwardRef<HTMLHeadingElement, AlertDialogTitleProps>(
    ({ className, id, ...props }, ref) => {
        const { setTitleId } = useAlertDialog()
        const autoId = React.useId()
        const resolvedId = id ?? `alert-dialog-title-${autoId}`

        React.useEffect(() => {
            setTitleId(resolvedId)
            return () => setTitleId(null)
        }, [resolvedId, setTitleId])

        return (
            <h2 ref={ref} id={resolvedId} className={cn("text-lg font-semibold", className)} {...props} />
        )
    }
)
AlertDialogTitle.displayName = "AlertDialogTitle"

type AlertDialogDescriptionProps = React.HTMLAttributes<HTMLParagraphElement>

const AlertDialogDescription = React.forwardRef<
    HTMLParagraphElement,
    AlertDialogDescriptionProps
>(({ className, id, ...props }, ref) => {
    const { setDescriptionId } = useAlertDialog()
    const autoId = React.useId()
    const resolvedId = id ?? `alert-dialog-description-${autoId}`

    React.useEffect(() => {
        setDescriptionId(resolvedId)
        return () => setDescriptionId(null)
    }, [resolvedId, setDescriptionId])

    return (
        <p
            ref={ref}
            id={resolvedId}
            className={cn("text-sm text-muted-foreground", className)}
            {...props}
        />
    )
})
AlertDialogDescription.displayName = "AlertDialogDescription"

/* -----------------------------------------------------------------------------
 * Action / Cancel (close on click, supports asChild)
 * -------------------------------------------------------------------------- */

type AlertDialogActionProps = React.ComponentPropsWithoutRef<"button"> & AsChildProps

const AlertDialogAction = React.forwardRef<HTMLButtonElement, AlertDialogActionProps>(
    ({ asChild, className, onClick, ...props }, ref) => {
        const { setOpen } = useAlertDialog()
        const Comp: any = asChild ? Slot : "button"

        return (
            <Comp
                ref={ref}
                className={cn(buttonVariants(), className)}
                onClick={composeEventHandlers(onClick, () => setOpen(false))}
                {...props}
            />
        )
    }
)
AlertDialogAction.displayName = "AlertDialogAction"

type AlertDialogCancelProps = React.ComponentPropsWithoutRef<"button"> & AsChildProps

const AlertDialogCancel = React.forwardRef<HTMLButtonElement, AlertDialogCancelProps>(
    ({ asChild, className, onClick, ...props }, ref) => {
        const { setOpen } = useAlertDialog()
        const Comp: any = asChild ? Slot : "button"

        return (
            <Comp
                ref={ref}
                className={cn(buttonVariants({ variant: "outline" }), "mt-2 sm:mt-0", className)}
                onClick={composeEventHandlers(onClick, () => setOpen(false))}
                {...props}
            />
        )
    }
)
AlertDialogCancel.displayName = "AlertDialogCancel"

export {
    AlertDialog,
    AlertDialogPortal,
    AlertDialogOverlay,
    AlertDialogTrigger,
    AlertDialogContent,
    AlertDialogHeader,
    AlertDialogFooter,
    AlertDialogTitle,
    AlertDialogDescription,
    AlertDialogAction,
    AlertDialogCancel,
}