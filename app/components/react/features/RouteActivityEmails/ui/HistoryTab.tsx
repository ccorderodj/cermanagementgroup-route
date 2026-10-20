import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import {
    Badge,
    Button,
    Input,
    Label,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import {
    ACTIVITY_EMAIL_TYPES,
    DELIVERY_TRIGGERS,
    fetchDeliveryHistory,
    type ActivityEmailType,
    type DeliveryHistory,
    type DeliveryTrigger,
} from '@/entities/RouteActivityEmails';
import {
    DELIVERY_STATUS_LABEL, EMAIL_TYPE_LABEL, SOURCE_TO_TRIGGER, TRIGGER_LABEL,
} from '../lib/labels';

const PAGE_SIZE = 20;
const SELECT = 'h-9 w-full rounded-md border border-input bg-background px-2 text-sm';

function hora(valor: string | null, zona: string | null): string {
    if (!valor) return '—';
    return new Date(valor).toLocaleString(undefined, zona ? { timeZone: zona } : undefined);
}

function retraso(segundos: number | null): string | null {
    if (segundos === null || segundos < 120) return null;
    const minutos = Math.round(segundos / 60);
    return minutos < 60 ? `${minutos} min late` : `${Math.floor(minutos / 60)} h ${minutos % 60} min late`;
}

/**
 * Delivery History (RTE-MAIL-CLOSE-01): cada correo real que tocaba o se pidió,
 * con su disparador, corte, vencimiento, intento, estado y motivo, y sus
 * reenvíos debajo. Lo mismo que guarda `activity_email_delivery`, acotado por
 * el servidor a quien mira. Sin asunto, cuerpo, notas ni direcciones.
 */
export function HistoryTab() {
    const [filas, setFilas] = useState<DeliveryHistory[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [desde, setDesde] = useState('');
    const [hasta, setHasta] = useState('');
    const [tipo, setTipo] = useState<ActivityEmailType | ''>('');
    const [disparador, setDisparador] = useState<DeliveryTrigger | ''>('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const cargar = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchDeliveryHistory({
                page,
                pageSize: PAGE_SIZE,
                dateFrom: desde,
                dateTo: hasta,
                reportType: tipo || undefined,
                trigger: disparador || undefined,
            });
            setFilas(data.results);
            setTotal(data.count);
        } catch {
            setError('The delivery history could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, [page, desde, hasta, tipo, disparador]);

    useEffect(() => {
        cargar();
    }, [cargar]);

    /** Cambiar un filtro vuelve a la primera página. */
    const filtrar = (cambiar: () => void) => {
        cambiar();
        setPage(1);
    };
    const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const estado = (h: DeliveryHistory) => (
        <div className="space-y-1">
            <Badge variant={h.status === 'accepted_by_provider' ? 'secondary' : 'outline'}>
                {DELIVERY_STATUS_LABEL[h.status]}
            </Badge>
            {h.reason_message && <p className="text-xs text-muted-foreground">{h.reason_message}</p>}
            {h.next_attempt_at && (
                <p className="text-xs text-muted-foreground">{`Next retry: ${hora(h.next_attempt_at, h.time_zone)}`}</p>
            )}
        </div>
    );

    const reenvios = (h: DeliveryHistory) => h.resends.map((r) => (
        <p key={r.id} className="text-xs text-muted-foreground">
            {`Resend #${r.sequence} · ${DELIVERY_STATUS_LABEL[r.status]} · ${hora(r.created_at, h.time_zone)}`}
        </p>
    ));

    return (
        <section className="space-y-4" aria-label="Delivery history">
            <p className="text-sm text-muted-foreground">
                Every real activity email that was due or requested, with what triggered it and what happened.
                Times are shown in the recipient&apos;s time zone.
            </p>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <div className="space-y-1">
                    <Label htmlFor="hist-from">From</Label>
                    <Input id="hist-from" type="date" value={desde} onChange={(e) => filtrar(() => setDesde(e.target.value))} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="hist-to">To</Label>
                    <Input id="hist-to" type="date" value={hasta} onChange={(e) => filtrar(() => setHasta(e.target.value))} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="hist-type">Email</Label>
                    <select
                        id="hist-type"
                        className={SELECT}
                        value={tipo}
                        onChange={(e) => filtrar(() => setTipo(e.target.value as ActivityEmailType | ''))}
                    >
                        <option value="">All</option>
                        {ACTIVITY_EMAIL_TYPES.map((t) => <option key={t} value={t}>{EMAIL_TYPE_LABEL[t]}</option>)}
                    </select>
                </div>
                <div className="space-y-1">
                    <Label htmlFor="hist-trigger">Trigger</Label>
                    <select
                        id="hist-trigger"
                        className={SELECT}
                        value={disparador}
                        onChange={(e) => filtrar(() => setDisparador(e.target.value as DeliveryTrigger | ''))}
                    >
                        <option value="">All</option>
                        {DELIVERY_TRIGGERS.map((t) => <option key={t} value={t}>{TRIGGER_LABEL[t]}</option>)}
                    </select>
                </div>
            </div>

            {loading && filas.length === 0 && (
                <div className="flex justify-center py-8">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
                </div>
            )}
            {error && (
                <div role="alert" className="flex items-center gap-3 text-sm text-destructive">
                    {error}
                    <Button type="button" variant="outline" size="sm" onClick={cargar}>Retry</Button>
                </div>
            )}
            {!loading && !error && filas.length === 0 && (
                <p className="rounded-md border p-4 text-sm text-muted-foreground">No deliveries match these filters.</p>
            )}

            {filas.length > 0 && (
                <>
                    <div className="hidden md:block">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Day</TableHead>
                                    <TableHead>Email</TableHead>
                                    <TableHead>Recipient</TableHead>
                                    <TableHead>Trigger</TableHead>
                                    <TableHead>Cutoff / due</TableHead>
                                    <TableHead>Attempt</TableHead>
                                    <TableHead>Status</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filas.map((h) => (
                                    <TableRow key={h.id}>
                                        <TableCell className="whitespace-nowrap">{h.operational_date}</TableCell>
                                        <TableCell>{EMAIL_TYPE_LABEL[h.report_type]}</TableCell>
                                        <TableCell>{h.recipient_name}</TableCell>
                                        <TableCell>{TRIGGER_LABEL[SOURCE_TO_TRIGGER[h.source]]}</TableCell>
                                        <TableCell className="text-xs">
                                            <p>{hora(h.cutoff_at, h.time_zone)}</p>
                                            <p className="text-muted-foreground">{h.time_zone ?? 'Time zone unknown'}</p>
                                        </TableCell>
                                        <TableCell className="text-xs">
                                            <p>{hora(h.last_attempt_at, h.time_zone)}</p>
                                            {retraso(h.delay_seconds) && (
                                                <p className="text-muted-foreground">{retraso(h.delay_seconds)}</p>
                                            )}
                                            {h.attempt_count > 1 && <p className="text-muted-foreground">{`${h.attempt_count} attempts`}</p>}
                                        </TableCell>
                                        <TableCell>
                                            {estado(h)}
                                            {reenvios(h)}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>

                    <ul className="space-y-3 md:hidden">
                        {filas.map((h) => (
                            <li key={h.id} className="space-y-1 rounded-md border p-3 text-sm">
                                <p className="font-medium">{`${EMAIL_TYPE_LABEL[h.report_type]} · ${h.operational_date}`}</p>
                                <p>{`${h.recipient_name} · ${TRIGGER_LABEL[SOURCE_TO_TRIGGER[h.source]]}`}</p>
                                <p className="text-xs text-muted-foreground">
                                    {`Cutoff ${hora(h.cutoff_at, h.time_zone)} · Attempt ${hora(h.last_attempt_at, h.time_zone)}`}
                                </p>
                                {estado(h)}
                                {reenvios(h)}
                            </li>
                        ))}
                    </ul>

                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                        <span>{`${total} deliver${total === 1 ? 'y' : 'ies'}`}</span>
                        <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                                Previous
                            </Button>
                            <span>{`Page ${page} of ${paginas}`}</span>
                            <Button type="button" variant="outline" size="sm" disabled={page >= paginas || loading} onClick={() => setPage((p) => p + 1)}>
                                Next
                            </Button>
                        </div>
                    </div>
                </>
            )}
        </section>
    );
}
