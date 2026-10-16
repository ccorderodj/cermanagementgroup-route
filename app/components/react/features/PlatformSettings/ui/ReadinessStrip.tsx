import { CheckCircle2, CircleDashed, ShieldAlert } from 'lucide-react';
import { Badge, Card, CardContent } from '@/shared/ui/shadcn/new-york';
import type { Gate, Readiness } from '@/entities/PlatformSettings';
import { gateStatus } from '../lib/presentation';

interface ReadinessStripProps {
    readiness?: Readiness;
    /** En Settings los gates de integración llevan a su tarjeta; en Diagnostics, a Settings. */
    surface: 'settings' | 'diagnostics';
}

function destino(gate: Gate, surface: ReadinessStripProps['surface']): string | null {
    if (gate.action === 'settings') {
        return surface === 'settings' ? `#integration-${gate.key}` : `/admin/platform/settings#integration-${gate.key}`;
    }
    if (gate.action === 'diagnostics') {
        return surface === 'diagnostics' ? '#check-group-integrity' : '/admin/platform/diagnostics';
    }
    if (gate.action === 'deployment') {
        return surface === 'settings' ? '#security-posture' : '/admin/platform/settings#security-posture';
    }
    return null;
}

/**
 * ¿Está lista para producción? La respuesta del servidor, tal cual.
 *
 * Los gates que bloquean van primero y separados de los que no: que una
 * integración opcional espere una decisión no impide salir, y mezclarlos haría leer una lista roja entera
 * donde sólo hay dos cosas que resolver.
 */
export const ReadinessStrip = ({ readiness, surface }: ReadinessStripProps) => {
    if (!readiness) return null;

    const bloquean = readiness.gates.filter((g) => g.blocks_production);
    const noBloquean = readiness.gates.filter((g) => !g.blocks_production);
    const abiertos = bloquean.filter((g) => g.status !== 'closed').length;

    return (
        <Card data-testid="readiness-strip">
            <CardContent className="flex flex-col gap-4 p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                        {readiness.production_ready ? (
                            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-green-600" aria-hidden="true" />
                        ) : (
                            <ShieldAlert className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />
                        )}
                        <div>
                            <h2 className="text-base font-semibold" data-testid="readiness-verdict">
                                {readiness.production_ready
                                    ? 'Ready for production'
                                    : 'Not ready for production'}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                {readiness.production_ready
                                    ? 'Every blocking gate is closed and proven.'
                                    : `${abiertos} of ${bloquean.length} blocking gates are not closed yet.`}
                                {readiness.mode !== 'PROD' && ` This deployment runs in ${readiness.mode} mode.`}
                            </p>
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs tabular-nums">
                        <Badge variant="success">{`${readiness.counts.closed ?? 0} closed`}</Badge>
                        <Badge variant="destructive">{`${readiness.counts.open ?? 0} open`}</Badge>
                        <Badge variant="secondary">{`${readiness.counts.waiting_cer ?? 0} waiting for CER`}</Badge>
                    </div>
                </div>

                {[{ titulo: 'Blocks production', gates: bloquean }, { titulo: 'Does not block', gates: noBloquean }]
                    .filter((grupo) => grupo.gates.length > 0)
                    .map((grupo) => (
                        <div key={grupo.titulo} className="flex flex-col gap-2">
                            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                {grupo.titulo}
                            </h3>
                            <ul className="grid gap-2 md:grid-cols-2">
                                {grupo.gates.map((gate) => {
                                    const estado = gateStatus(gate.status);
                                    const href = gate.status === 'closed' ? null : destino(gate, surface);
                                    return (
                                        <li
                                            key={gate.key}
                                            data-testid={`gate-${gate.key}`}
                                            data-status={gate.status}
                                            className="flex items-start gap-3 rounded-md border border-border p-3"
                                        >
                                            {gate.status === 'closed' ? (
                                                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600" aria-hidden="true" />
                                            ) : (
                                                <CircleDashed
                                                    className={`mt-0.5 size-4 shrink-0 ${gate.status === 'open' ? 'text-destructive' : 'text-muted-foreground'}`}
                                                    aria-hidden="true"
                                                />
                                            )}
                                            <div className="min-w-0 flex-1">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-sm font-medium">{gate.title}</span>
                                                    <Badge variant={estado.tone}>{estado.label}</Badge>
                                                    {gate.open_decision && (
                                                        <Badge variant="outline">{gate.open_decision}</Badge>
                                                    )}
                                                </div>
                                                <p className="mt-1 text-xs text-muted-foreground">{gate.detail}</p>
                                                {href && (
                                                    <a href={href} className="mt-1 inline-block text-xs font-medium text-primary underline-offset-4 hover:underline">
                                                        {gate.action === 'diagnostics' ? 'Open Diagnostics' : 'Resolve'}
                                                    </a>
                                                )}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    ))}
            </CardContent>
        </Card>
    );
};
