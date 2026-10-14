import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, UserMinus, UserRoundCog } from 'lucide-react';
import {
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    Label,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    Textarea,
} from '@/shared/ui/shadcn/new-york';
import { normalizeRejectedPayload } from '@/shared/api';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    fetchSuccession,
    runSuccession,
    type SuccessionInfo,
    type SuccessionPlan,
} from '@/entities/RouteOrganization';
import type { UserManagementEntity } from '@/entities/UserManagement';

export type SuccessionMode = 'retire' | 'replace';

interface SuccessionDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    user: UserManagementEntity;
    mode: SuccessionMode;
    /** Ejecutada: la lista tiene que recargarse (alguien salió, otros cambiaron). */
    onDone: () => void;
}

/**
 * Retirar o sustituir a un responsable (V1.4, FR-03 / FR-04).
 *
 * Lo que se enseña antes de confirmar **es** el plan del servidor —la misma
 * función que ejecuta—, no una deducción de la pantalla. Confirmar repite la
 * operación con la versión vista: si otro cambió la jerarquía entretanto, el
 * servidor responde 409 y no se escribe nada.
 */
export function SuccessionDialog(props: SuccessionDialogProps) {
    const {
        open, onOpenChange, user, mode, onDone,
    } = props;
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const [info, setInfo] = useState<SuccessionInfo | null>(null);
    const [plan, setPlan] = useState<SuccessionPlan | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [successor, setSuccessor] = useState<string>('');
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open) return;
        setInfo(null);
        setPlan(null);
        setError(null);
        setSuccessor('');
        setReason('');
        dispatch(fetchSuccession(user.id)).unwrap()
            .then((datos) => {
                setInfo(datos);
                if (mode === 'retire') {
                    setPlan(datos.retire_preview ?? null);
                    setError(datos.retire_blocked_reason ?? null);
                }
            })
            .catch((e) => setError(normalizeRejectedPayload(e).message));
    }, [dispatch, mode, open, user.id]);

    /** Elegido el sucesor, el servidor calcula el plan sin escribir. */
    const elegirSucesor = useCallback(async (valor: string) => {
        if (!valor) return;
        setSuccessor(valor);
        setPlan(null);
        setError(null);
        try {
            setPlan(await dispatch(runSuccession({
                operation: 'replace',
                userId: user.id,
                successorUserId: Number(valor),
                dryRun: true,
            })).unwrap());
        } catch (e) {
            setError(normalizeRejectedPayload(e).message);
        }
    }, [dispatch, user.id]);

    const confirmar = useCallback(async () => {
        if (!plan || !info) return;
        setBusy(true);
        try {
            await dispatch(runSuccession({
                operation: mode,
                userId: user.id,
                successorUserId: mode === 'replace' ? Number(successor) : undefined,
                version: info.version,
                reason: reason.trim(),
                dryRun: false,
            })).unwrap();
            toast({
                title: mode === 'retire' ? 'Manager retired' : 'Manager replaced',
                description: `${plan.outgoing.name} left the company; their team was reassigned.`,
            });
            onOpenChange(false);
            onDone();
        } catch (e) {
            setError(normalizeRejectedPayload(e).message);
        } finally {
            setBusy(false);
        }
    }, [dispatch, info, mode, onDone, onOpenChange, plan, reason, successor, toast, user.id]);

    const nombre = info?.outgoing.name || user.username;
    const titulo = mode === 'retire' ? `Retire ${nombre}` : `Replace ${nombre}`;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[640px]">
                <DialogHeader>
                    <DialogTitle className="inline-flex items-center gap-2">
                        {mode === 'retire'
                            ? <UserMinus className="size-4" />
                            : <UserRoundCog className="size-4" />}
                        {titulo}
                    </DialogTitle>
                    <DialogDescription>
                        {mode === 'retire'
                            ? 'Permanent exit without a successor: their direct reports move to their own superior, and they leave this company.'
                            : 'The successor takes this position under the same superior and receives the whole team. The outgoing person leaves this company.'}
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-col gap-4" id="succession-dialog">
                    {info && (
                        <p className="text-sm text-muted-foreground">
                            {`${info.outgoing.position_label} · ${info.direct_reports.length} direct report(s)`}
                        </p>
                    )}

                    {mode === 'replace' && info && (
                        <div className="flex flex-col gap-2">
                            <Label htmlFor="succession-successor">Successor</Label>
                            <Select value={successor} onValueChange={elegirSucesor}>
                                <SelectTrigger id="succession-successor" className="w-full">
                                    <SelectValue placeholder="Choose the successor" />
                                </SelectTrigger>
                                <SelectContent>
                                    {info.successor_candidates.map((c) => (
                                        <SelectItem key={c.user_id} value={String(c.user_id)}>
                                            {c.position_label ? `${c.name} · ${c.position_label}` : c.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            {info.successor_candidates.length === 0 && (
                                <p className="text-xs text-destructive">
                                    Nobody in this company can take this position without breaking the hierarchy.
                                </p>
                            )}
                        </div>
                    )}

                    {plan && (
                        <div className="flex flex-col gap-2 rounded-md border border-border p-3" id="succession-preview">
                            <p className="text-sm font-medium">What will happen</p>
                            {plan.successor && (
                                <p className="text-sm">
                                    {`${plan.successor.name} becomes ${plan.outgoing.position_label}`}
                                    {plan.superior ? ` under ${plan.superior.name}` : ''}
                                    {plan.successor_before ? ` (now ${plan.successor_before})` : ''}
                                    .
                                </p>
                            )}
                            {plan.moves.length === 0 ? (
                                <p className="text-sm text-muted-foreground">Nobody else moves.</p>
                            ) : (
                                <ul className="flex flex-col gap-1">
                                    {plan.moves.map((m) => (
                                        <li key={m.user_id} className="flex flex-wrap items-center gap-1 text-sm">
                                            <span className="font-medium">{m.name}</span>
                                            <span className="text-muted-foreground">{`· ${m.position_label}`}</span>
                                            <ArrowRight className="size-3 text-muted-foreground" />
                                            <span>{m.to_name ?? '—'}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                            <p className="text-sm text-muted-foreground">
                                {`${plan.outgoing.name} will be removed from this company.`}
                            </p>
                        </div>
                    )}

                    {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

                    {plan && (
                        <div className="flex flex-col gap-2">
                            <Label htmlFor="succession-reason">Reason (optional)</Label>
                            <Textarea
                                id="succession-reason"
                                value={reason}
                                maxLength={500}
                                onChange={(e) => setReason(e.target.value)}
                            />
                        </div>
                    )}

                    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            variant="destructive"
                            disabled={!plan || busy}
                            onClick={confirmar}
                        >
                            {mode === 'retire' ? 'Confirm retirement' : 'Confirm replacement'}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
