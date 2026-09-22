import { useEffect, useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import { History, Loader2, Play, RefreshCw } from 'lucide-react';
import {
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    fetchCheckHistory,
    fetchPlatformDiagnostics,
    getPlatformCheckHistory,
    getPlatformChecks,
    getPlatformReadiness,
    getPlatformSettingsError,
    getPlatformSettingsIsLoading,
    runAllChecks,
    runCheck,
    type Check,
    type CheckRun,
} from '@/entities/PlatformSettings';
import { CHECK_KIND, checkStatus, checkTrigger, when } from '../lib/presentation';
import { ReadinessStrip } from './ReadinessStrip';

const ORDEN = ['integration', 'integrity', 'infrastructure', 'platform'];

const HistoryTable = ({ runs }: { runs?: CheckRun[] }) => {
    if (!runs) {
        return (
            <p className="flex items-center gap-2 p-3 text-xs">
                <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                Loading history…
            </p>
        );
    }
    if (runs.length === 0) {
        return <p className="p-3 text-xs text-muted-foreground">It has never been checked.</p>;
    }
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead className="text-right">Took</TableHead>
                    <TableHead>Detail</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {runs.map((r, i) => (
                    <TableRow key={r.id ?? `${r.checked_at}-${i}`}>
                        <TableCell className="whitespace-nowrap text-xs tabular-nums">{when(r.checked_at)}</TableCell>
                        <TableCell>
                            <Badge variant={checkStatus(r.status).tone}>{checkStatus(r.status).label}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{checkTrigger(r.trigger).label}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums">
                            {r.duration_ms != null ? `${r.duration_ms} ms` : '—'}
                        </TableCell>
                        <TableCell className="min-w-[16rem] text-xs">{r.detail}</TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
};

/**
 * Diagnostics: ¿funciona lo configurado, y sigue protegida la evidencia?
 *
 * Comprobar abre conexiones reales, así que es un botón y no algo que ocurra al
 * abrir la pantalla. Lo que no está configurado no está «caído»: se enseña como
 * tal, con el enlace a Settings.
 */
export const DiagnosticsPanel = () => {
    const dispatch = useAppDispatch();
    const checks = useSelector(getPlatformChecks);
    const readiness = useSelector(getPlatformReadiness);
    const history = useSelector(getPlatformCheckHistory);
    const isLoading = useSelector(getPlatformSettingsIsLoading);
    const loadError = useSelector(getPlatformSettingsError);

    const [running, setRunning] = useState<string | null>(null);
    const [openHistory, setOpenHistory] = useState<string | null>(null);
    const [actionError, setActionError] = useState('');

    useEffect(() => {
        dispatch(fetchPlatformDiagnostics());
    }, [dispatch]);

    const grupos = useMemo(() => {
        const mapa = new Map<string, Check[]>();
        checks.forEach((c) => mapa.set(c.kind, [...(mapa.get(c.kind) ?? []), c]));
        return [...mapa.entries()].sort((a, b) => ORDEN.indexOf(a[0]) - ORDEN.indexOf(b[0]));
    }, [checks]);

    const runAll = async () => {
        setRunning('all');
        setActionError('');
        const accion = await dispatch(runAllChecks());
        setRunning(null);
        if (runAllChecks.rejected.match(accion)) setActionError(accion.payload ?? 'Could not run the checks.');
    };

    const runOne = async (key: string) => {
        setRunning(key);
        setActionError('');
        const accion = await dispatch(runCheck(key));
        setRunning(null);
        if (runCheck.rejected.match(accion)) {
            setActionError(accion.payload ?? `Could not run ${key}.`);
        } else if (openHistory === key) {
            dispatch(fetchCheckHistory(key));
        }
    };

    const toggleHistory = (key: string) => {
        if (openHistory === key) {
            setOpenHistory(null);
            return;
        }
        setOpenHistory(key);
        dispatch(fetchCheckHistory(key));
    };

    if (loadError && checks.length === 0) {
        return (
            <Card>
                <CardContent className="p-6 text-sm text-destructive">{loadError}</CardContent>
            </Card>
        );
    }

    if (isLoading && checks.length === 0) {
        return (
            <Card>
                <CardContent className="flex items-center gap-2 p-6 text-sm">
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    Loading diagnostics…
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="flex flex-col gap-4">
            <ReadinessStrip readiness={readiness} surface="diagnostics" />

            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-muted-foreground">
                    Checks open real connections. Scheduled checks also run on their own; see the policy in Settings.
                </p>
                <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => dispatch(fetchPlatformDiagnostics())} disabled={isLoading}>
                        <RefreshCw className={`mr-2 size-4 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
                        Refresh
                    </Button>
                    <Button type="button" size="sm" onClick={runAll} disabled={running !== null} data-testid="run-all-checks">
                        {running === 'all' ? (
                            <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
                        ) : (
                            <Play className="mr-2 size-4" aria-hidden="true" />
                        )}
                        {running === 'all' ? 'Running all checks…' : 'Run all checks'}
                    </Button>
                </div>
            </div>

            {actionError && <p className="text-sm text-destructive" role="alert">{actionError}</p>}

            {grupos.map(([kind, lista]) => (
                <Card key={kind} id={`check-group-${kind}`} className="scroll-mt-20">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">{CHECK_KIND[kind] ?? kind}</CardTitle>
                        {kind === 'integrity' && (
                            <CardDescription>
                                The controls that keep signatures and evidence from being rewritten.
                            </CardDescription>
                        )}
                    </CardHeader>
                    <CardContent className="p-0">
                        <ul className="divide-y divide-border">
                            {lista.map((c) => {
                                const estado = checkStatus(c.status);
                                const enCurso = running === c.key || running === 'all';
                                const runs = history[c.key];
                                return (
                                    <li key={c.key} data-testid={`check-${c.key}`} data-status={c.status} className="flex flex-col gap-2 px-4 py-3 sm:px-6">
                                        <div className="flex flex-wrap items-start justify-between gap-2">
                                            <div className="min-w-0">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-sm font-semibold">{c.title}</span>
                                                    <Badge variant={estado.tone}>{estado.label}</Badge>
                                                </div>
                                                <p className="text-xs text-muted-foreground">{c.summary}</p>
                                            </div>
                                            <div className="flex flex-wrap gap-1.5">
                                                <Button type="button" size="sm" variant="outline" onClick={() => runOne(c.key)} disabled={running !== null}>
                                                    {enCurso ? <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" /> : <Play className="mr-2 size-4" aria-hidden="true" />}
                                                    Run
                                                </Button>
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant="ghost"
                                                    aria-expanded={openHistory === c.key}
                                                    onClick={() => toggleHistory(c.key)}
                                                >
                                                    <History className="mr-2 size-4" aria-hidden="true" />
                                                    History
                                                </Button>
                                            </div>
                                        </div>

                                        {c.detail && <p className="text-sm">{c.detail}</p>}
                                        {kind === 'integration' && c.status === 'not_applicable' && (
                                            <a href={`/admin/platform/settings#integration-${c.key}`} className="text-xs font-medium text-primary underline-offset-4 hover:underline">
                                                Configure in Settings
                                            </a>
                                        )}
                                        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                                            <div className="flex gap-1.5"><dt>Last checked</dt><dd className="tabular-nums text-foreground">{when(c.last_checked_at)}</dd></div>
                                            <div className="flex gap-1.5"><dt>Last healthy</dt><dd className="tabular-nums text-foreground">{when(c.last_success_at)}</dd></div>
                                        </dl>

                                        {openHistory === c.key && (
                                            <div className="overflow-x-auto rounded-md border border-border" data-testid={`history-${c.key}`}>
                                                <HistoryTable runs={runs} />
                                            </div>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
};
