import { useCallback, useEffect, useMemo, useState } from 'react';
import { FileText, Loader2, Send } from 'lucide-react';
import {
    Badge,
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    Input,
    Label,
    Textarea,
} from '@/shared/ui/shadcn/new-york';
import { useUser } from '@/app/providers/StoreProvider';
import {
    fetchActivityEmailRecipients,
    fetchDeliveries,
    fetchStrategicRecipients,
    previewRealReport,
    sendRealReport,
    type ActivityEmailTemplate,
    type Delivery,
    type RealReportPreview,
} from '@/entities/RouteActivityEmails';

interface GenerateReportDialogProps {
    template: ActivityEmailTemplate;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

interface Persona {
    user_id: number;
    first_name: string;
    last_name: string;
}

/** Cómo se lee cada estado de un envío. Nunca «entregado». */
const ESTADO: Record<Delivery['status'], string> = {
    pending: 'Pending',
    claimed: 'Sending',
    accepted_by_provider: 'Accepted by the mail provider (delivery not confirmed)',
    retryable_failure: 'Not sent — will be retried',
    permanent_failure: 'Not sent — the provider refused it',
    skipped: 'Not sent — nothing to send',
    unknown_outcome: 'Uncertain outcome — needs reconciliation',
};

const hoyLocal = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function hora(valor: string | null, zona: string | null): string {
    if (!valor) return '—';
    return new Date(valor).toLocaleString(undefined, zona ? { timeZone: zona } : undefined);
}

function mensajeDeError(error: unknown, porDefecto: string): string {
    const detalle = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (typeof detalle === 'string') return detalle;
    if (detalle && typeof detalle === 'object' && 'message' in detalle) {
        return String((detalle as { message: unknown }).message);
    }
    return porDefecto;
}

/**
 * «Generate report» y «Send now» (RTE-MAIL-CP4-02).
 *
 * Generar trae el reporte con **datos reales** de una persona o un mando y un
 * día, con la plantilla guardada; no escribe ni envía nada. Enviar es una
 * segunda acción, confirmada, al destinatario configurado (nunca a una
 * dirección escrita) y sólo cuando el reporte ya tocaba: el uso principal es
 * recuperar un envío automático que no salió. El servidor decide si se puede;
 * aquí sólo se enseña su respuesta y su motivo.
 */
export function GenerateReportDialog({ template, open, onOpenChange }: GenerateReportDialogProps) {
    const { hasUserPermission } = useUser();
    const puedeEnviar = hasUserPermission('route.activityemails.send');
    const estrategico = template.group === 'strategic';

    const [personas, setPersonas] = useState<Persona[]>([]);
    const [filtro, setFiltro] = useState('');
    const [destinatario, setDestinatario] = useState<number | null>(null);
    const [dia, setDia] = useState(hoyLocal());
    const [vista, setVista] = useState<RealReportPreview | null>(null);
    const [historial, setHistorial] = useState<Delivery[]>([]);
    const [generando, setGenerando] = useState(false);
    const [confirmar, setConfirmar] = useState(false);
    const [motivo, setMotivo] = useState('');
    const [enviando, setEnviando] = useState(false);
    const [resultado, setResultado] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        setVista(null);
        setResultado(null);
        setError(null);
        setConfirmar(false);
        const cargar = estrategico ? fetchStrategicRecipients : fetchActivityEmailRecipients;
        cargar({ page: 1, pageSize: 100, q: filtro || undefined, includeSelf: true })
            .then((p) => setPersonas(p.results))
            .catch(() => setError('The recipients could not be loaded.'));
    }, [open, estrategico, filtro]);

    const cargarHistorial = useCallback(async () => {
        if (!destinatario) return;
        try {
            setHistorial(await fetchDeliveries({
                report_type: template.template_type, recipient_user_id: destinatario, operational_date: dia,
            }));
        } catch {
            setHistorial([]);
        }
    }, [destinatario, dia, template.template_type]);

    const generar = async () => {
        if (!destinatario) return;
        setGenerando(true);
        setError(null);
        setResultado(null);
        setConfirmar(false);
        try {
            setVista(await previewRealReport({
                report_type: template.template_type, recipient_user_id: destinatario, operational_date: dia,
            }));
            await cargarHistorial();
        } catch (err) {
            setVista(null);
            setError(mensajeDeError(err, 'The report could not be generated.'));
        } finally {
            setGenerando(false);
        }
    };

    const enviar = async () => {
        if (!destinatario) return;
        setEnviando(true);
        setError(null);
        try {
            const r = await sendRealReport({
                report_type: template.template_type,
                recipient_user_id: destinatario,
                operational_date: dia,
                reason: motivo.trim() || undefined,
            });
            setResultado(`${ESTADO[r.status]}${r.destination_masked ? ` · ${r.destination_masked}` : ''}`);
            setConfirmar(false);
            // La vista previa ya no vale: ahora dice «ya enviado» y no ofrece
            // volver a mandarlo.
            setVista(await previewRealReport({
                report_type: template.template_type, recipient_user_id: destinatario, operational_date: dia,
            }));
            await cargarHistorial();
        } catch (err) {
            setError(mensajeDeError(err, 'The report could not be sent.'));
        } finally {
            setEnviando(false);
        }
    };

    const nombre = useMemo(
        () => personas.find((p) => p.user_id === destinatario),
        [personas, destinatario],
    );
    const idBase = `gen-${template.template_type}`;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] overflow-y-auto sm:max-w-[760px]">
                <DialogHeader>
                    <DialogTitle>{`Generate report · ${template.label}`}</DialogTitle>
                    <DialogDescription>
                        Real data, with the saved template. Generating does not save or send anything.
                        Real activity notes are never included.
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-3 sm:grid-cols-3">
                    <div className="space-y-1.5 sm:col-span-2">
                        <Label htmlFor={`${idBase}-who`}>{estrategico ? 'Manager' : 'Person'}</Label>
                        <Input
                            aria-label="Filter recipients"
                            placeholder="Filter by name or email"
                            value={filtro}
                            onChange={(e) => setFiltro(e.target.value)}
                        />
                        <select
                            id={`${idBase}-who`}
                            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                            value={destinatario ?? ''}
                            onChange={(e) => {
                                setDestinatario(e.target.value ? Number(e.target.value) : null);
                                setVista(null);
                            }}
                        >
                            <option value="">Choose…</option>
                            {personas.map((p) => (
                                <option key={p.user_id} value={p.user_id}>{`${p.first_name} ${p.last_name}`}</option>
                            ))}
                        </select>
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor={`${idBase}-day`}>Operational day</Label>
                        <Input
                            id={`${idBase}-day`}
                            type="date"
                            value={dia}
                            onChange={(e) => {
                                setDia(e.target.value);
                                setVista(null);
                            }}
                        />
                    </div>
                </div>

                <div>
                    <Button type="button" disabled={!destinatario || generando} onClick={generar}>
                        {generando ? <Loader2 className="mr-2 size-4 animate-spin" /> : <FileText className="mr-2 size-4" />}
                        Generate report
                    </Button>
                </div>

                {error && (
                    <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm">{error}</p>
                )}

                {vista && (
                    <section className="space-y-3" aria-label="Report preview">
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={vista.provisional ? 'outline' : 'secondary'}>
                                {vista.provisional ? 'Partial' : 'Final'}
                            </Badge>
                            {vista.coverage !== null && (
                                <Badge variant="outline">{`${vista.coverage} people covered`}</Badge>
                            )}
                            <Badge variant="outline">
                                {`${vista.activity_count} ${vista.activity_count === 1 ? 'activity' : 'activities'}`}
                            </Badge>
                        </div>
                        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                            <dt className="text-muted-foreground">Recipient</dt>
                            <dd>{`${vista.recipient_name}${vista.destination_masked ? ` · ${vista.destination_masked}` : ''}`}</dd>
                            <dt className="text-muted-foreground">Time zone</dt>
                            <dd>{vista.time_zone ?? 'Unknown'}</dd>
                            <dt className="text-muted-foreground">Data until (cutoff)</dt>
                            <dd>{hora(vista.cutoff_at, vista.time_zone)}</dd>
                            <dt className="text-muted-foreground">Due</dt>
                            <dd>{hora(vista.due_at, vista.time_zone)}</dd>
                            <dt className="text-muted-foreground">Generated</dt>
                            <dd>{hora(vista.generated_at, vista.time_zone)}</dd>
                        </dl>
                        {vista.reason_message && (
                            <p className="rounded-md border bg-muted/40 p-3 text-sm">{vista.reason_message}</p>
                        )}
                        {vista.subject && (
                            <div className="space-y-1">
                                <p className="text-sm"><span className="font-semibold">Subject: </span>{vista.subject}</p>
                                <div className="max-h-[40vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-mono text-xs">
                                    {vista.body}
                                </div>
                            </div>
                        )}

                        {puedeEnviar && (
                            <div className="space-y-2 rounded-md border p-3">
                                {!vista.can_send && (
                                    <p className="text-sm text-muted-foreground">{vista.blocked_message}</p>
                                )}
                                {!confirmar && (
                                    <Button type="button" disabled={!vista.can_send} onClick={() => setConfirmar(true)}>
                                        <Send className="mr-2 size-4" />
                                        Send now
                                    </Button>
                                )}
                                {confirmar && (
                                    <div className="space-y-2" role="group" aria-label="Confirm sending">
                                        <p className="text-sm">
                                            {`Send “${template.label}” for ${vista.operational_date} to `}
                                            <strong>{nombre ? `${nombre.first_name} ${nombre.last_name}` : vista.recipient_name}</strong>
                                            {` (${vista.destination_masked ?? 'configured address'}), with data until `}
                                            {hora(vista.cutoff_at, vista.time_zone)}
                                            . If the scheduled send runs later it will not send it again.
                                        </p>
                                        <Label htmlFor={`${idBase}-reason`}>Reason (optional)</Label>
                                        <Textarea
                                            id={`${idBase}-reason`}
                                            rows={2}
                                            maxLength={300}
                                            value={motivo}
                                            onChange={(e) => setMotivo(e.target.value)}
                                        />
                                        <div className="flex gap-2">
                                            <Button type="button" variant="outline" onClick={() => setConfirmar(false)}>Cancel</Button>
                                            <Button type="button" disabled={enviando} onClick={enviar}>
                                                {enviando && <Loader2 className="mr-2 size-4 animate-spin" />}
                                                Confirm and send
                                            </Button>
                                        </div>
                                    </div>
                                )}
                                {resultado && <p role="status" className="text-sm">{resultado}</p>}
                            </div>
                        )}

                        {historial.length > 0 && (
                            <div className="space-y-1">
                                <p className="text-sm font-medium">History for this day</p>
                                <ul className="space-y-1 text-sm">
                                    {historial.map((h) => (
                                        <li key={h.id} className="rounded-md border px-3 py-2">
                                            {`${ESTADO[h.status]} · ${h.source} · attempt ${h.attempt_count}`}
                                            {h.last_attempt_at ? ` · ${hora(h.last_attempt_at, vista.time_zone)}` : ''}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </section>
                )}
            </DialogContent>
        </Dialog>
    );
}
