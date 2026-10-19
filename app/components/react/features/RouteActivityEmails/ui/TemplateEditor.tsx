import { useEffect, useState } from 'react';
import {
    Eye, FileText, Loader2, MailX, RotateCcw, Save, Send,
} from 'lucide-react';
import {
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    Input,
    Label,
    Textarea,
} from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog } from '@/features/Common';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useUser } from '@/app/providers/StoreProvider';
import {
    previewActivityEmailTemplate,
    restoreActivityEmailTemplate,
    updateActivityEmailTemplate,
    type ActivityEmailPreview,
    type ActivityEmailTemplate,
} from '@/entities/RouteActivityEmails';
import { readServerProblem, type ServerProblem } from '../lib/errors';
import { TestSendDialog } from './TestSendDialog';
import { GenerateReportDialog } from './GenerateReportDialog';

interface TemplateEditorProps {
    template: ActivityEmailTemplate;
    onSaved: (template: ActivityEmailTemplate) => void;
    onReload: () => void;
    onDirtyChange: (type: string, dirty: boolean) => void;
}

const SIN_PROBLEMA: ServerProblem = { status: null, fields: {}, message: null };

function fecha(valor: string | null): string | null {
    if (!valor) return null;
    return new Date(valor).toLocaleString();
}

/**
 * Una plantilla: asunto, cuerpo, ayuda de variables, vista previa, guardar y
 * restaurar.
 *
 * Cada tarjeta guarda **sólo su plantilla** (`PUT /templates/{tipo}`), así que
 * guardar una no toca la otra. La versión leída viaja con el guardado: si otra
 * persona cambió la plantilla entretanto, el servidor responde 409 y aquí se
 * ofrece recargar en vez de pisar su cambio.
 */
export function TemplateEditor({ template, onSaved, onReload, onDirtyChange }: TemplateEditorProps) {
    const { toast } = useToast();
    const [subject, setSubject] = useState(template.subject);
    const [body, setBody] = useState(template.body);
    const [problem, setProblem] = useState<ServerProblem>(SIN_PROBLEMA);
    const [saving, setSaving] = useState(false);
    const [previewing, setPreviewing] = useState(false);
    const [preview, setPreview] = useState<ActivityEmailPreview | null>(null);
    const [confirmRestore, setConfirmRestore] = useState(false);
    const [restoring, setRestoring] = useState(false);
    const [testOpen, setTestOpen] = useState(false);
    const [reportOpen, setReportOpen] = useState(false);
    const { hasUserPermission } = useUser();
    const puedeGenerar = hasUserPermission('route.activityemails.preview');

    useEffect(() => {
        setSubject(template.subject);
        setBody(template.body);
        setProblem(SIN_PROBLEMA);
    }, [template]);

    const dirty = subject !== template.subject || body !== template.body;

    useEffect(() => {
        onDirtyChange(template.template_type, dirty);
    }, [dirty, onDirtyChange, template.template_type]);

    const idBase = `ae-${template.template_type}`;

    const save = async () => {
        setSaving(true);
        setProblem(SIN_PROBLEMA);
        try {
            const saved = await updateActivityEmailTemplate(template.template_type, {
                subject,
                body,
                version: template.version,
            });
            onSaved(saved);
            toast({
                title: 'Template saved',
                description: 'Configuración guardada. Envío automático pendiente de habilitación.',
            });
        } catch (error) {
            setProblem(readServerProblem(error, 'The template could not be saved.'));
        } finally {
            setSaving(false);
        }
    };

    const runPreview = async () => {
        setPreviewing(true);
        setProblem(SIN_PROBLEMA);
        try {
            setPreview(await previewActivityEmailTemplate(template.template_type, { subject, body }));
        } catch (error) {
            setProblem(readServerProblem(error, 'The preview could not be generated.'));
        } finally {
            setPreviewing(false);
        }
    };

    const restore = async () => {
        setRestoring(true);
        setProblem(SIN_PROBLEMA);
        try {
            const saved = await restoreActivityEmailTemplate(template.template_type, template.version);
            onSaved(saved);
            setConfirmRestore(false);
            toast({ title: 'Default text restored', description: template.label });
        } catch (error) {
            setConfirmRestore(false);
            setProblem(readServerProblem(error, 'The default text could not be restored.'));
        } finally {
            setRestoring(false);
        }
    };

    const conflicto = problem.status === 409;
    const editado = fecha(template.updated_at);

    return (
        <Card role="region" aria-label={template.label} data-testid={`template-${template.template_type}`}>
            <CardHeader className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base">{template.label}</CardTitle>
                    <Badge variant="secondary">{template.schedule_label}</Badge>
                    {template.is_default ? (
                        <Badge variant="outline">Approved default</Badge>
                    ) : (
                        <Badge variant="outline">Customized</Badge>
                    )}
                    {dirty && <Badge variant="outline" className="border-warning/40 bg-warning/10">Unsaved changes</Badge>}
                </div>
                <CardDescription>
                    {editado && template.updated_by_name
                        ? `Last modified by ${template.updated_by_name} on ${editado}.`
                        : 'Using the approved default text.'}
                </CardDescription>
                <p className="flex items-start gap-1.5 text-sm">
                    <MailX className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    {template.send_condition}
                </p>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-1.5">
                    <Label htmlFor={`${idBase}-subject`}>Subject</Label>
                    <Input
                        id={`${idBase}-subject`}
                        value={subject}
                        maxLength={200}
                        aria-invalid={Boolean(problem.fields.subject)}
                        aria-describedby={problem.fields.subject ? `${idBase}-subject-error` : undefined}
                        onChange={(e) => setSubject(e.target.value)}
                    />
                    {problem.fields.subject && (
                        <p id={`${idBase}-subject-error`} role="alert" className="text-sm text-destructive">
                            {problem.fields.subject}
                        </p>
                    )}
                </div>

                <div className="space-y-1.5">
                    <Label htmlFor={`${idBase}-body`}>Body</Label>
                    <Textarea
                        id={`${idBase}-body`}
                        value={body}
                        rows={14}
                        maxLength={5000}
                        className="font-mono text-sm"
                        aria-invalid={Boolean(problem.fields.body)}
                        aria-describedby={`${idBase}-tokens${problem.fields.body ? ` ${idBase}-body-error` : ''}`}
                        onChange={(e) => setBody(e.target.value)}
                    />
                    {problem.fields.body && (
                        <p id={`${idBase}-body-error`} role="alert" className="text-sm text-destructive">
                            {problem.fields.body}
                        </p>
                    )}
                </div>

                <div id={`${idBase}-tokens`} className="rounded-md border bg-muted/40 p-3 text-sm">
                    <p className="mb-2 font-medium">Supported variables</p>
                    <ul className="space-y-1">
                        {template.tokens.map((t) => (
                            <li key={t.token} className="flex flex-wrap items-baseline gap-x-2">
                                <code className="rounded bg-background px-1 text-xs">{`{{${t.token}}}`}</code>
                                <span className="text-muted-foreground">{t.description}</span>
                                {t.required && <Badge variant="outline" className="text-[10px]">Required</Badge>}
                            </li>
                        ))}
                    </ul>
                    <p className="mt-2 text-xs text-muted-foreground">
                        Plain text only: no HTML or links. The subject accepts
                        {' '}
                        {template.subject_tokens.map((t, i) => (
                            <span key={t}>
                                {i > 0 && ', '}
                                <code className="text-xs">{`{{${t}}}`}</code>
                            </span>
                        ))}
                        .
                    </p>
                </div>

                {(problem.message || conflicto) && (
                    <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm">
                        <p>{problem.message}</p>
                        {conflicto && (
                            <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onReload}>
                                Reload the latest version
                            </Button>
                        )}
                    </div>
                )}

                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
                    <Button
                        type="button"
                        variant="ghost"
                        disabled={template.is_default || restoring || saving}
                        onClick={() => setConfirmRestore(true)}
                    >
                        <RotateCcw className="mr-2 size-4" />
                        Restore default
                    </Button>
                    <Button
                        type="button"
                        variant="outline"
                        disabled={dirty}
                        title={dirty ? 'Save your changes first: the test uses the saved text.' : undefined}
                        onClick={() => setTestOpen(true)}
                    >
                        <Send className="mr-2 size-4" />
                        Send test
                    </Button>
                    {puedeGenerar && (
                        <Button
                            type="button"
                            variant="outline"
                            disabled={dirty}
                            title={dirty ? 'Save your changes first: the report uses the saved text.' : undefined}
                            onClick={() => setReportOpen(true)}
                        >
                            <FileText className="mr-2 size-4" />
                            Generate report
                        </Button>
                    )}
                    <Button type="button" variant="outline" disabled={previewing} onClick={runPreview}>
                        {previewing ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Eye className="mr-2 size-4" />}
                        Preview
                    </Button>
                    <Button type="button" disabled={!dirty || saving} onClick={save}>
                        {saving ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}
                        Save changes
                    </Button>
                </div>
            </CardContent>

            <Dialog open={preview !== null} onOpenChange={(open) => !open && setPreview(null)}>
                <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[720px]">
                    <DialogHeader>
                        <DialogTitle>{preview?.sample_label}</DialogTitle>
                        <DialogDescription>
                            Fictional sample data. Nothing is saved or sent.
                        </DialogDescription>
                    </DialogHeader>
                    {preview && (
                        <div className="space-y-3" data-testid="activity-email-preview">
                            <Badge variant="outline" className="border-warning/40 bg-warning/10">{preview.sample_label}</Badge>
                            <p className="text-sm">
                                <span className="font-semibold">Subject: </span>
                                {preview.subject}
                            </p>
                            <div className="max-h-[50vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-mono text-xs">
                                {preview.body}
                            </div>
                        </div>
                    )}
                </DialogContent>
            </Dialog>

            <TestSendDialog template={template} open={testOpen} onOpenChange={setTestOpen} />
            {puedeGenerar && (
                <GenerateReportDialog template={template} open={reportOpen} onOpenChange={setReportOpen} />
            )}

            <ConfirmDestructiveDialog
                open={confirmRestore}
                onOpenChange={setConfirmRestore}
                title={`Restore “${template.label}”?`}
                description={
                    `The custom subject and body of “${template.label}” will be replaced by the approved default text. `
                    + 'The other email and the recipients do not change.'
                }
                confirmLabel="Restore default"
                busy={restoring}
                onConfirm={restore}
            />
        </Card>
    );
}
