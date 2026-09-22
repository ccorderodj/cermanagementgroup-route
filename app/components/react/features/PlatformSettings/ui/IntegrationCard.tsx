import { KeyRound, Loader2, ShieldCheck } from 'lucide-react';
import {
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/shared/ui/shadcn/new-york';
import type { Integration } from '@/entities/PlatformSettings';
import { integrationStatus, when } from '../lib/presentation';

interface IntegrationCardProps {
    integration: Integration;
    verifying: boolean;
    onOpenGuide: (step: number) => void;
    onVerify: () => void;
}

const TREINTA_DIAS = 30 * 24 * 60 * 60 * 1000;

export const IntegrationCard = ({ integration, verifying, onOpenGuide, onVerify }: IntegrationCardProps) => {
    const estado = integrationStatus(integration.status);
    const proveedor = integration.providers.find((p) => p.key === integration.provider);
    const verificable = ['configured', 'verified', 'failing'].includes(integration.status);
    const sinEmpezar = integration.status === 'not_configured';

    return (
        <Card
            id={`integration-${integration.key}`}
            data-testid={`integration-${integration.key}`}
            data-status={integration.status}
            className="flex scroll-mt-20 flex-col"
        >
            <CardHeader className="pb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <CardTitle className="text-base">{integration.title}</CardTitle>
                    <div className="flex flex-wrap items-center gap-1.5">
                        {integration.required && <Badge variant="outline">Required</Badge>}
                        {integration.open_decision && <Badge variant="outline">{integration.open_decision}</Badge>}
                        <Badge variant={estado.tone}>{estado.label}</Badge>
                    </div>
                </div>
                <CardDescription>{integration.summary}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
                <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[8rem_1fr]">
                    <dt className="text-muted-foreground">Provider</dt>
                    <dd>{proveedor?.title ?? 'None chosen'}</dd>
                    {integration.secrets.length > 0 && (
                        <>
                            <dt className="text-muted-foreground">Credentials</dt>
                            <dd className="flex flex-col gap-0.5">
                                {integration.secrets.map((s) => {
                                    const caduca = s.expires_at ? new Date(s.expires_at).getTime() : null;
                                    const pronto = caduca !== null && caduca - Date.now() < TREINTA_DIAS;
                                    return (
                                        <span key={s.name} className="flex flex-wrap items-center gap-1.5 text-xs">
                                            <KeyRound className="size-3 text-muted-foreground" aria-hidden="true" />
                                            {s.label}
                                            <span className={s.present ? 'text-muted-foreground' : 'text-destructive'}>
                                                {s.present ? 'stored' : 'not set'}
                                            </span>
                                            {s.expires_at && (
                                                <span className={pronto ? 'font-medium text-destructive' : 'text-muted-foreground'}>
                                                    {`· expires ${when(s.expires_at)}`}
                                                </span>
                                            )}
                                        </span>
                                    );
                                })}
                            </dd>
                        </>
                    )}
                    <dt className="text-muted-foreground">Verified</dt>
                    <dd>{integration.verified_at ? when(integration.verified_at) : 'Not yet'}</dd>
                </dl>

                {integration.missing.length > 0 && integration.status !== 'verified' && (
                    <ul className="list-disc pl-5 text-xs text-muted-foreground">
                        {integration.missing.slice(0, 3).map((m) => <li key={m}>{m}</li>)}
                    </ul>
                )}

                <div className="mt-auto flex flex-wrap gap-2 pt-1">
                    <Button
                        type="button"
                        size="sm"
                        variant={sinEmpezar ? 'default' : 'outline'}
                        onClick={() => onOpenGuide(sinEmpezar ? 0 : 2)}
                        data-testid={`open-guide-${integration.key}`}
                    >
                        {sinEmpezar ? 'Set up' : 'Edit configuration'}
                    </Button>
                    {!sinEmpezar && (
                        <Button type="button" size="sm" variant="ghost" onClick={() => onOpenGuide(1)}>
                            How to get credentials
                        </Button>
                    )}
                    {verificable && (
                        <Button
                            type="button"
                            size="sm"
                            variant={integration.status === 'verified' ? 'ghost' : 'default'}
                            onClick={onVerify}
                            disabled={verifying}
                            data-testid={`verify-${integration.key}`}
                        >
                            {verifying ? (
                                <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
                            ) : (
                                <ShieldCheck className="mr-2 size-4" aria-hidden="true" />
                            )}
                            {integration.status === 'verified' ? 'Verify again' : 'Verify'}
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    );
};
