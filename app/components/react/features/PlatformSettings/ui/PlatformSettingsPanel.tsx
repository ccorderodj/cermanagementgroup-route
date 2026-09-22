import { useEffect, useState } from 'react';
import { useSelector } from 'react-redux';
import { Loader2, RefreshCw } from 'lucide-react';
import {
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import {
    fetchPlatformSettings,
    getPlatformAudit,
    getPlatformIntegrations,
    getPlatformPolicies,
    getPlatformPosture,
    getPlatformReadiness,
    getPlatformSettingsError,
    getPlatformSettingsIsLoading,
    verifyIntegration,
} from '@/entities/PlatformSettings';
import { checkStatus, when } from '../lib/presentation';
import { EncryptionCard } from './EncryptionCard';
import { IntegrationCard } from './IntegrationCard';
import { IntegrationGuideSheet } from './IntegrationGuideSheet';
import { PolicyCard } from './PolicyCard';
import { ReadinessStrip } from './ReadinessStrip';
import { SecurityPosturePanel } from './SecurityPosturePanel';

/** Notas por política. Una aplicación de dominio añade aquí las suyas. */
const POLICY_NOTES: Record<string, string> = {};

/**
 * Integrations & Settings.
 *
 * Arriba, la respuesta a «¿se puede salir a producción?». Debajo, cada cosa que
 * esa respuesta necesita, en el orden en que se resuelve: los servicios de
 * terceros, la llave que protege sus credenciales, las políticas y la postura.
 */
export const PlatformSettingsPanel = () => {
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const integrations = useSelector(getPlatformIntegrations);
    const policies = useSelector(getPlatformPolicies);
    const posture = useSelector(getPlatformPosture);
    const readiness = useSelector(getPlatformReadiness);
    const audit = useSelector(getPlatformAudit);
    const isLoading = useSelector(getPlatformSettingsIsLoading);
    const error = useSelector(getPlatformSettingsError);

    const [guide, setGuide] = useState<{ key: string; step: number } | null>(null);
    const [verifying, setVerifying] = useState<string | null>(null);

    useEffect(() => {
        dispatch(fetchPlatformSettings());
    }, [dispatch]);

    // El ancla de un enlace (#integration-email) llega antes que las tarjetas.
    const cargado = integrations.length > 0;
    useEffect(() => {
        if (!cargado || !window.location.hash) return;
        document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' });
    }, [cargado]);

    const verify = async (key: string, title: string) => {
        setVerifying(key);
        const accion = await dispatch(verifyIntegration(key));
        setVerifying(null);
        if (verifyIntegration.fulfilled.match(accion)) {
            const { check } = accion.payload;
            toast({
                variant: check.status === 'healthy' ? 'default' : 'destructive',
                title: check.status === 'healthy' ? `${title} verified` : `${title}: ${checkStatus(check.status).label}`,
                description: check.detail ?? undefined,
            });
        } else {
            toast({ variant: 'destructive', title: `Could not verify ${title}`, description: accion.payload });
        }
    };

    if (error && !cargado) {
        return (
            <Card>
                <CardContent className="p-6 text-sm text-destructive">{error}</CardContent>
            </Card>
        );
    }

    if (isLoading && !cargado) {
        return (
            <Card>
                <CardContent className="flex items-center gap-2 p-6 text-sm">
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    Loading integrations and settings…
                </CardContent>
            </Card>
        );
    }

    const abierta = integrations.find((i) => i.key === guide?.key) ?? null;
    const gate = (key: string) => readiness?.gates.find((g) => g.key === key);

    return (
        <div className="flex flex-col gap-6">
            <ReadinessStrip readiness={readiness} surface="settings" />

            <section className="flex flex-col gap-3" aria-labelledby="integrations-title">
                <div className="flex flex-wrap items-end justify-between gap-2">
                    <div>
                        <h2 id="integrations-title" className="text-lg font-semibold tracking-tight">Integrations</h2>
                        <p className="text-sm text-muted-foreground">
                            Each service production depends on. Set it up, then Verify to close its gate.
                        </p>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={() => dispatch(fetchPlatformSettings())} disabled={isLoading}>
                        <RefreshCw className={`mr-2 size-4 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
                        Refresh
                    </Button>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                    {integrations.map((i) => (
                        <IntegrationCard
                            key={i.key}
                            integration={i}
                            verifying={verifying === i.key}
                            onOpenGuide={(step) => setGuide({ key: i.key, step })}
                            onVerify={() => verify(i.key, i.title)}
                        />
                    ))}
                </div>
            </section>

            <EncryptionCard
                masterKey={posture.find((p) => p.key === 'master_key')}
                gate={gate('credential_encryption')}
            />

            <section className="flex flex-col gap-3" aria-labelledby="policies-title">
                <div>
                    <h2 id="policies-title" className="text-lg font-semibold tracking-tight">Policies</h2>
                    <p className="text-sm text-muted-foreground">
                        Limits and schedules. They take effect on every instance within seconds, without a redeploy.
                    </p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                    {policies.map((p) => <PolicyCard key={p.key} policy={p} note={POLICY_NOTES[p.key]} />)}
                </div>
            </section>

            <SecurityPosturePanel posture={posture} mode={readiness?.mode} />

            <Card data-testid="platform-audit">
                <CardHeader className="pb-3">
                    <CardTitle className="text-base">Recent changes</CardTitle>
                    <CardDescription>Every change made here is recorded. Credential values never are.</CardDescription>
                </CardHeader>
                <CardContent>
                    {audit.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No changes yet.</p>
                    ) : (
                        <ul className="divide-y divide-border">
                            {audit.map((a) => (
                                <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2 text-sm">
                                    <span>
                                        <span className="font-mono text-xs">{a.action}</span>
                                        <span className="text-muted-foreground">{` · ${a.target}`}</span>
                                    </span>
                                    <span className="text-xs tabular-nums text-muted-foreground">
                                        {when(a.occurred_at)}
                                        {a.actor_user_id != null && ` · user #${a.actor_user_id}`}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </CardContent>
            </Card>

            <IntegrationGuideSheet
                integration={abierta}
                initialStep={guide?.step ?? 0}
                onOpenChange={(open) => { if (!open) setGuide(null); }}
            />
        </div>
    );
};
