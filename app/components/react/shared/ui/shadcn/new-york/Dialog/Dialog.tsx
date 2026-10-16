import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Cross2Icon } from '@radix-ui/react-icons';

import { cn } from '@/shared/lib/utils/utils';

const Dialog = DialogPrimitive.Root;

const DialogTrigger = DialogPrimitive.Trigger;

const DialogPortal = DialogPrimitive.Portal;

const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
    React.ElementRef<typeof DialogPrimitive.Overlay>,
    React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
    <DialogPrimitive.Overlay
        ref={ref}
        className={cn(
            'fixed inset-0 z-50 bg-black/80  data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            className,
        )}
        {...props}
    />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
    React.ElementRef<typeof DialogPrimitive.Content>,
    React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, onCloseAutoFocus, ...props }, ref) => {
    /* A dónde vuelve el foco al cerrar.
     *
     * Radix lo devuelve al `DialogTrigger`, y en esta aplicación **no hay
     * ninguno**: los dieciocho diálogos se abren poniendo `open` a `true`
     * desde el manejador de un botón. Sin trigger registrado, Radix no tiene
     * a dónde volver y el foco se queda en `<body>`.
     *
     * Para quien navega con teclado eso significa que cerrar un diálogo lo
     * devuelve al principio de la página: cada vez que cancela algo, vuelve a
     * empezar. Se recuerda aquí quién tenía el foco al abrir y se le devuelve.
     *
     * Se captura **durante el render** y no en un efecto porque para cuando
     * corre el efecto Radix ya ha movido el foco dentro del diálogo, y lo que
     * se guardaría entonces sería un control del propio diálogo.
     */
    const disparador = React.useRef<HTMLElement | null>(null);
    if (disparador.current === null && typeof document !== 'undefined') {
        const activo = document.activeElement as HTMLElement | null;
        // `body` no es un destino: devolver el foco ahí es no devolverlo.
        disparador.current = activo && activo !== document.body ? activo : null;
    }

    const devolverElFoco = (event: Event) => {
        const destino = disparador.current;
        // Si el disparador ya no está en el documento —su panel se recargó
        // mientras el diálogo estaba abierto— se deja que Radix haga lo suyo
        // en vez de intentar enfocar un nodo huérfano.
        if (destino && document.contains(destino)) {
            event.preventDefault();
            destino.focus();
        }
    };

    return (
        <DialogPortal>
            <DialogOverlay />
            <DialogPrimitive.Content
                ref={ref}
                onCloseAutoFocus={(event) => {
                    onCloseAutoFocus?.(event);
                    if (!event.defaultPrevented) devolverElFoco(event);
                }}
            className={cn(
                // `max-h` + `overflow-y-auto` van AQUI y no en cada uso.
                // Sin ellos, un formulario mas alto que la ventana se sale
                // por arriba y por abajo —esta centrado con `translate`—
                // y sus botones quedan fuera de alcance sin nada que
                // permita desplazarse. En un movil eso convierte el modal
                // en un callejon sin salida.
                //
                // `svh` y no `vh`: en un movil la barra del navegador se
                // retrae, y `vh` mide la ventana grande, asi que el modal
                // seguiria asomando por debajo del borde real.
                'fixed left-[50%] top-[50%] z-50 flex max-h-[calc(100svh-2rem)] w-full max-w-lg translate-x-[-50%] translate-y-[-50%] flex-col border bg-background shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg',
                className,
            )}
            {...props}
        >
            {/* El contenido se desplaza; el marco no.

                Si el `overflow` estuviera en el propio contenedor, la aspa de
                cerrar —posicionada en absoluto sobre el— se iria hacia arriba
                con el scroll y dejaria de estar donde se la espera justo
                cuando el formulario es largo, que es cuando mas falta hace. */}
            {/* `min-h-0`: un hijo flexible no encoge por debajo de su
                contenido —su `min-height` implicito es `auto`— asi que sin
                esto el bloque conserva su altura entera, desborda el marco
                y `overflow-y-auto` no llega a activarse nunca. El boton de
                guardar acaba fuera de la pantalla sin forma de alcanzarlo.
                Es el mismo `min-*: auto` que obligo a poner `min-w-0` en
                `SidebarInset`. */}
                <div className="grid min-h-0 gap-4 overflow-y-auto p-6">{children}</div>
            <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm bg-background opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
                    <Cross2Icon className="h-4 w-4" />
                    <span className="sr-only">Close</span>
                </DialogPrimitive.Close>
            </DialogPrimitive.Content>
        </DialogPortal>
    );
});
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn(
            'flex flex-col space-y-1.5 text-center sm:text-left',
            className,
        )}
        {...props}
    />
);
DialogHeader.displayName = 'DialogHeader';

const DialogFooter = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn(
            'flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2',
            className,
        )}
        {...props}
    />
);
DialogFooter.displayName = 'DialogFooter';

const DialogTitle = React.forwardRef<
    React.ElementRef<typeof DialogPrimitive.Title>,
    React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
    <DialogPrimitive.Title
        ref={ref}
        className={cn(
            'text-lg font-semibold leading-none tracking-tight',
            className,
        )}
        {...props}
    />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

const DialogDescription = React.forwardRef<
    React.ElementRef<typeof DialogPrimitive.Description>,
    React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
    <DialogPrimitive.Description
        ref={ref}
        className={cn('text-sm text-muted-foreground', className)}
        {...props}
    />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

export {
    Dialog,
    DialogPortal,
    DialogOverlay,
    DialogTrigger,
    DialogClose,
    DialogContent,
    DialogHeader,
    DialogFooter,
    DialogTitle,
    DialogDescription,
};
