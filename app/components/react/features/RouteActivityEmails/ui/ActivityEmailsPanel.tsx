import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button, Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/shadcn/new-york';
import {
    fetchActivityEmailTemplates,
    type ActivityEmailTemplate,
} from '@/entities/RouteActivityEmails';
import { TemplateEditor } from './TemplateEditor';
import { RecipientsTab } from './RecipientsTab';
import { DeliveryStatusBanner } from './DeliveryStatusBanner';
import { HistoryTab } from './HistoryTab';

/** Los dos grupos de plantillas, en este orden. */
const GRUPOS = [
    {
        group: 'motivational',
        title: 'Motivational Emails',
        description: 'Short, friendly reminders for each person about their own activity.',
    },
    {
        group: 'strategic',
        title: 'Strategic Activity Reports',
        description:
            'Team reports for managers: one block per authorized person and, at the end of the day, '
            + 'the Team Weekly Summary. Real activity notes are not included until the notes policy is approved.',
    },
] as const;

/**
 * Los correos de actividad: Templates, Recipients y Delivery history.
 *
 * Arriba, el estado del envío **leído del servidor** (`DeliveryStatusBanner`):
 * proveedor, interruptores, tipos activos y última pasada de cada reloj.
 *
 * Las dos plantillas siguen montadas al cambiar de pestaña (`forceMount`): un
 * borrador sin guardar no se pierde por mirar los destinatarios, y salir de la
 * página con cambios pendientes pide confirmación al navegador.
 */
export function ActivityEmailsPanel() {
    const [templates, setTemplates] = useState<ActivityEmailTemplate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [dirty, setDirty] = useState<Record<string, boolean>>({});
    const [tab, setTab] = useState('templates');

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setTemplates(await fetchActivityEmailTemplates());
        } catch {
            setError('The templates could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const onDirtyChange = useCallback((type: string, value: boolean) => {
        setDirty((prev) => (prev[type] === value ? prev : { ...prev, [type]: value }));
    }, []);

    const hayCambios = Object.values(dirty).some(Boolean);

    useEffect(() => {
        if (!hayCambios) return undefined;
        const avisar = (e: BeforeUnloadEvent) => {
            e.preventDefault();
            e.returnValue = '';
        };
        window.addEventListener('beforeunload', avisar);
        return () => window.removeEventListener('beforeunload', avisar);
    }, [hayCambios]);

    const onSaved = (saved: ActivityEmailTemplate) => {
        setTemplates((prev) => prev.map((t) => (t.template_type === saved.template_type ? saved : t)));
    };

    return (
        <div className="space-y-4">
            <DeliveryStatusBanner />

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                    <TabsTrigger value="templates">Templates</TabsTrigger>
                    <TabsTrigger value="recipients">Recipients</TabsTrigger>
                    <TabsTrigger value="history">Delivery history</TabsTrigger>
                </TabsList>

                <TabsContent value="templates" forceMount className="data-[state=inactive]:hidden">
                    {loading && templates.length === 0 && (
                        <div className="flex justify-center py-10">
                            <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
                        </div>
                    )}
                    {error && (
                        <div role="alert" className="flex items-center gap-3 text-sm text-destructive">
                            {error}
                            <Button type="button" variant="outline" size="sm" onClick={load}>Retry</Button>
                        </div>
                    )}
                    {!error && templates.length > 0 && GRUPOS.map((g) => (
                        <section key={g.group} className="mb-8 space-y-3" aria-label={g.title}>
                            <div>
                                <h3 className="text-base font-semibold">{g.title}</h3>
                                <p className="text-sm text-muted-foreground">{g.description}</p>
                            </div>
                            <div className="grid gap-4 xl:grid-cols-2">
                                {templates.filter((t) => t.group === g.group).map((t) => (
                                    <TemplateEditor
                                        key={t.template_type}
                                        template={t}
                                        onSaved={onSaved}
                                        onReload={load}
                                        onDirtyChange={onDirtyChange}
                                    />
                                ))}
                            </div>
                        </section>
                    ))}
                </TabsContent>

                <TabsContent value="recipients">
                    <RecipientsTab />
                </TabsContent>

                <TabsContent value="history">
                    <HistoryTab />
                </TabsContent>
            </Tabs>
        </div>
    );
}
