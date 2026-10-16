import * as React from 'react';
import { AlertTriangle, X } from 'lucide-react';
import {
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/shared/ui/shadcn/new-york';

/**
 * Confirmación para una acción que no se deshace.
 *
 * Existe porque el addendum RTE02-A01 pide que borrar se confirme y que, si
 * está bloqueado, el motivo se explique en lenguaje normal. Antes no había
 * ningún diálogo de confirmación destructiva en todo el frontend, así que vive
 * en `features/Common`: lo van a necesitar vehículos, supervisores, valores de
 * lista y usuarios, y tres copias acabarían diciendo tres cosas distintas.
 *
 * `blockedReason` invierte el diálogo: en vez de pedir confirmación, explica
 * por qué no se puede y ofrece sólo cerrar. Es el mismo componente a propósito
 * —el administrador abre la misma acción y el diálogo le dice qué pasa— en vez
 * de un botón que no responde o que desaparece sin explicación.
 *
 * El servidor sigue siendo la autoridad. Esto es experiencia de usuario: si la
 * regla cambiara y la interfaz se quedara desactualizada, la petición seguiría
 * fallando con 409 y su motivo (invariante 8 de AGENTS.md).
 */

interface ConfirmDestructiveDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title: string;
    description: React.ReactNode;
    confirmLabel?: string;
    /** Si viene, no se ofrece confirmar: se explica por qué no se puede. */
    blockedReason?: string | null;
    busy?: boolean;
    onConfirm: () => void;
}

export function ConfirmDestructiveDialog(props: ConfirmDestructiveDialogProps) {
    const {
        open,
        onOpenChange,
        title,
        description,
        confirmLabel = 'Delete',
        blockedReason,
        busy,
        onConfirm,
    } = props;

    const bloqueado = Boolean(blockedReason);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[460px]">
                <DialogHeader>
                    <DialogTitle className="inline-flex items-center gap-2">
                        <AlertTriangle className="size-4 text-destructive" />
                        {bloqueado ? 'Action unavailable' : title}
                    </DialogTitle>
                    <DialogDescription>
                        {bloqueado ? blockedReason : description}
                    </DialogDescription>
                </DialogHeader>

                <DialogFooter className="gap-2 sm:gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                    >
                        <X className="mr-2 size-4" />
                        {bloqueado ? 'Close' : 'Cancel'}
                    </Button>

                    {!bloqueado && (
                        <Button
                            type="button"
                            variant="destructive"
                            disabled={busy}
                            onClick={onConfirm}
                        >
                            {busy ? 'Working…' : confirmLabel}
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
