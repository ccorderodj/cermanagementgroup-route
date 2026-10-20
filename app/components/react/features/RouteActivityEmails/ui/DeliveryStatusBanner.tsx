import { useCallback, useEffect, useState } from 'react';
import { MailCheck, MailWarning, RefreshCw } from 'lucide-react';
import { Button } from '@/shared/ui/shadcn/new-york';
import {
    fetchOperationalStatus,
    type DispatchRun,
    type OperationalStatus,
} from '@/entities/RouteActivityEmails';
import { EMAIL_TYPE_LABEL } from '../lib/labels';

/** Cuánto tiempo sin pasada hace sospechar de cada reloj. */
const SOSPECHA_MINUTOS: Record<DispatchRun['source'], number> = { schedule: 5, reconcile: 20 };

const RELOJ: Record<DispatchRun['source'], string> = {
    schedule: 'In-app scheduler',
    reconcile: 'DigitalOcean job',
};

function hace(valor: string): string {
    const minutos = Math.max(0, Math.round((Date.now() - new Date(valor).getTime()) / 60000));
    if (minutos < 1) return 'less than a minute ago';
    if (minutos < 60) return `${minutos} min ago`;
    const horas = Math.round(minutos / 60);
    return horas < 48 ? `${horas} h ago` : new Date(valor).toLocaleString();
}

function modoAutomatico(estado: OperationalStatus): string {
    if (!estado.automation_enabled) return 'Off';
    return estado.dry_run ? 'Dry run (counts only, sends nothing)' : 'On';
}

function pasada(runs: DispatchRun[], source: DispatchRun['source']): string {
    const r = runs.find((x) => x.source === source);
    if (!r) return `${RELOJ[source]}: not observed yet (not verified)`;
    const viejo = (Date.now() - new Date(r.finished_at).getTime()) / 60000 > SOSPECHA_MINUTOS[source];
    const fallo = r.outcome === 'failed' ? ' — the last pass failed' : '';
    return `${RELOJ[source]}: last pass ${hace(r.finished_at)}${fallo}${viejo ? ' (overdue)' : ''}`;
}

/**
 * El estado del envío, **leído del servidor** (RTE-MAIL-CLOSE-01): proveedor,
 * interruptores, tipos activos y la última pasada vista de cada reloj. Sustituye
 * al aviso fijo «envío automático pendiente», que decía lo mismo pasara lo que
 * pasara. «Aceptado por el proveedor» nunca se presenta como entregado.
 */
export function DeliveryStatusBanner() {
    const [estado, setEstado] = useState<OperationalStatus | null>(null);
    const [error, setError] = useState(false);

    const cargar = useCallback(async () => {
        setError(false);
        try {
            setEstado(await fetchOperationalStatus());
        } catch {
            setError(true);
        }
    }, []);

    useEffect(() => {
        cargar();
    }, [cargar]);

    if (error) {
        return (
            <div role="status" className="flex items-center gap-3 rounded-md border p-3 text-sm">
                The delivery status could not be loaded.
                <Button type="button" variant="outline" size="sm" onClick={cargar}>Retry</Button>
            </div>
        );
    }
    if (!estado) return null;

    const verificado = estado.provider_status === 'verified';
    const automatico = modoAutomatico(estado);
    const tipos = estado.real_send_types.length
        ? estado.real_send_types.map((t) => EMAIL_TYPE_LABEL[t]).join(', ')
        : 'none';
    const Icono = verificado ? MailCheck : MailWarning;

    return (
        <section
            aria-label="Delivery status"
            className="flex items-start gap-2 rounded-md border border-primary/20 bg-primary/5 p-3 text-sm"
        >
            <Icono className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="min-w-0 flex-1 space-y-1">
                <p>
                    <span className="font-medium">Mail provider: </span>
                    {verificado
                        ? `Verified${estado.provider_verified_at ? ` (${new Date(estado.provider_verified_at).toLocaleString()})` : ''}`
                        : `Not verified (${estado.provider_status.replace(/_/g, ' ')}) — run Verify in Platform Settings`}
                </p>
                <p>
                    <span className="font-medium">Automatic delivery: </span>
                    {automatico}
                    <span className="font-medium"> · Real sending enabled for: </span>
                    {tipos}
                </p>
                <p className="text-muted-foreground">
                    {`${pasada(estado.runs, 'schedule')} · ${pasada(estado.runs, 'reconcile')}`}
                </p>
                <p className="text-xs text-muted-foreground">
                    “Accepted by the mail provider” means Microsoft took the message; it does not confirm it reached the inbox.
                </p>
            </div>
            <Button type="button" variant="ghost" size="icon" aria-label="Refresh delivery status" onClick={cargar}>
                <RefreshCw className="size-4" />
            </Button>
        </section>
    );
}
