import { Construction } from 'lucide-react';

/**
 * Lo que se enseña donde todavía no hay módulo.
 *
 * Existe para cumplir una regla explícita del proyecto: **una pantalla sin
 * backend dice que no existe, en lugar de enseñar una lista vacía o un botón
 * que no hace nada** (`AGENTS.md`). Una tabla vacía y una función no construida
 * se ven igual, y esa ambigüedad es la que hace que alguien dé por terminado lo
 * que no lo está.
 *
 * No lleva datos de negocio inventados. Dice qué falta y en qué checkpoint
 * llega.
 */

type NotBuiltYetProps = {
    /** Qué módulo falta, en el lenguaje del producto. */
    feature: string;
    /** Checkpoint que lo entrega, para que la espera sea comprobable. */
    checkpoint: string;
};

export function NotBuiltYet({ feature, checkpoint }: NotBuiltYetProps) {
    return (
        <div
            className="rounded-lg border border-dashed border-border bg-muted/30 p-6 text-center"
            data-testid="NotBuiltYet"
        >
            <Construction
                className="mx-auto size-8 text-muted-foreground"
                aria-hidden="true"
            />
            <p className="mt-3 font-medium text-foreground">
                {feature} is not built yet
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
                This screen is scaffolding from RTE02. The module arrives in
                {' '}
                {checkpoint}
                .
            </p>
        </div>
    );
}
