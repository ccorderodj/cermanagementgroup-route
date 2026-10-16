import { useEffect, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import {
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/shared/ui/shadcn/new-york';
import {
    fetchActivityEmailTestTargets,
    sendActivityEmailTest,
    type ActivityEmailTemplate,
    type ActivityEmailTestResult,
    type ActivityEmailTestTargets,
} from '@/entities/RouteActivityEmails';

interface TestSendDialogProps {
    template: ActivityEmailTemplate;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

/** Lo que significa cada resultado, sin prometer más de lo que se sabe. */
const RESULTADO: Record<ActivityEmailTestResult['outcome'], string> = {
    accepted_by_provider:
        'Accepted by the mail provider. Delivery is not confirmed: check the test inbox (and its spam folder).',
    not_sent_development_backend:
        'Not sent: no mail provider is configured, so the message stayed in the server log.',
    captured_by_test_backend: 'Captured by the test mailbox of the automated tests. Nothing left the server.',
};

function mensajeDeError(error: unknown): string {
    const data = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
    const detalle = data?.data?.detail;
    if (typeof detalle === 'string') return detalle;
    if (detalle && typeof detalle === 'object' && 'message' in detalle) {
        return String((detalle as { message: unknown }).message);
    }
    return 'The test email could not be sent.';
}

/**
 * Prueba controlada de una plantilla (RTE-MAIL-TEST-01).
 *
 * Manda el texto **guardado** con datos ficticios a una dirección de prueba
 * autorizada: la propia o una de la lista del servidor. No se escribe un destino
 * libre. El resultado distingue «aceptado por el proveedor» de «no salió del
 * servidor»; nunca dice «entregado».
 */
export function TestSendDialog({ template, open, onOpenChange }: TestSendDialogProps) {
    const [targets, setTargets] = useState<ActivityEmailTestTargets | null>(null);
    const [to, setTo] = useState('');
    const [sending, setSending] = useState(false);
    const [result, setResult] = useState<ActivityEmailTestResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        setResult(null);
        setError(null);
        fetchActivityEmailTestTargets()
            .then((t) => {
                setTargets(t);
                setTo((actual) => actual || t.recipients[0] || '');
            })
            .catch(() => setError('The test recipients could not be loaded.'));
    }, [open]);

    const send = async () => {
        setSending(true);
        setError(null);
        setResult(null);
        try {
            setResult(await sendActivityEmailTest(template.template_type, to));
        } catch (err) {
            setError(mensajeDeError(err));
        } finally {
            setSending(false);
        }
    };

    const idBase = `test-${template.template_type}`;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[520px]">
                <DialogHeader>
                    <DialogTitle>{`Send a test of “${template.label}”`}</DialogTitle>
                    <DialogDescription>
                        The saved text with fictional sample data, marked [TEST]. It goes only to an approved test
                        address and does not change any recipient setting.
                    </DialogDescription>
                </DialogHeader>

                {targets && !targets.provider_configured && (
                    <p className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
                        No mail provider is configured yet: the test will not leave the server.
                    </p>
                )}

                {targets && targets.recipients.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                        There is no approved test address: your account has no valid email.
                    </p>
                )}

                {targets && targets.recipients.length > 0 && (
                    <fieldset className="space-y-2">
                        <legend className="mb-1 text-sm font-medium">Test recipient</legend>
                        {targets.recipients.map((r, i) => (
                            <label key={r} htmlFor={`${idBase}-${i}`} className="flex items-center gap-2 text-sm">
                                <input
                                    id={`${idBase}-${i}`}
                                    type="radio"
                                    name={idBase}
                                    value={r}
                                    checked={to === r}
                                    onChange={() => setTo(r)}
                                    className="size-4 accent-primary"
                                />
                                <span className="break-all">{r}</span>
                            </label>
                        ))}
                        <p className="text-xs text-muted-foreground">
                            {`Up to ${targets.limit} tests every ${targets.window_minutes} minutes. Every test is audited.`}
                        </p>
                    </fieldset>
                )}

                {result && (
                    <p role="status" className="rounded-md border bg-muted/40 p-3 text-sm">
                        {RESULTADO[result.outcome]}
                    </p>
                )}
                {error && (
                    <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm">
                        {error}
                    </p>
                )}

                <DialogFooter className="gap-2 sm:gap-2">
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                        Close
                    </Button>
                    <Button type="button" disabled={!to || sending} onClick={send}>
                        {sending ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Send className="mr-2 size-4" />}
                        Send test
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
