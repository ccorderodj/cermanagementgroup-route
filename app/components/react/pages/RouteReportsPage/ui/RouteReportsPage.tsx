import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { useUser } from '@/app/providers/StoreProvider';
import { formatPeriod } from '@/entities/RouteActivityExplorer';
import {
    downloadReportExcel,
    fetchReport,
    type ReportRange,
    type ReportView,
} from '@/entities/RouteReports';
import {
    ReportsBreakdown,
    ReportsKpis,
    ReportsTimeline,
    ReportsToolbar,
} from '@/features/RouteReports';

/**
 * Reports (RTE09): la pantalla del V0.7, tal cual.
 *
 * Cabecera con *Export Excel*, la barra con *All Supervisors* por defecto y las
 * pestañas Week / Month / Year, los cuatro KPIs y dos tarjetas: *By day / week /
 * month* y *Activity breakdown*. **Sin acordeón** —el V0.7 de Reports no lo
 * tiene— y **sin navegación entre periodos**: se ve el periodo en curso, que
 * decide el servidor.
 *
 * Nada se calcula aquí: millas, tiempo, grupos y coste llegan hechos. La
 * pantalla sólo formatea.
 *
 * En pantallas estrechas el V0.7 pasa los KPIs a dos columnas y las tarjetas a
 * una (`@media(max-width:1050px)`); en móvil la barra se apila y **conserva** el
 * selector de supervisor.
 */
export function RouteReportsPage() {
    const { hasUserPermission } = useUser();
    const puedeExportar = hasUserPermission('route.reports.export');

    const [rango, setRango] = useState<ReportRange>('week');
    /** `null`: *All Supervisors*, el valor por defecto del V0.7. */
    const [supervisor, setSupervisor] = useState<number | null>(null);

    const [datos, setDatos] = useState<ReportView | null>(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(false);
    const [exportando, setExportando] = useState(false);
    const [errorExport, setErrorExport] = useState<string | null>(null);

    const vivo = useRef(true);
    useEffect(() => () => { vivo.current = false; }, []);

    /** La lectura vigente: una respuesta vieja no pisa a la nueva. */
    const lecturaVigente = useRef(0);

    const releer = useCallback(async () => {
        lecturaVigente.current += 1;
        const mia = lecturaVigente.current;
        setCargando(true);
        try {
            const cuerpo = await fetchReport({ range: rango, supervisorUserId: supervisor });
            if (!vivo.current || mia !== lecturaVigente.current) return;
            setDatos(cuerpo);
            setError(false);
        } catch {
            if (vivo.current && mia === lecturaVigente.current) setError(true);
        } finally {
            if (vivo.current && mia === lecturaVigente.current) setCargando(false);
        }
    }, [rango, supervisor]);

    useEffect(() => { releer(); }, [releer]);

    /**
     * Sólo se pinta lo que corresponde a la selección actual: al cambiar de
     * supervisor o de rango, los datos anteriores no se presentan como los
     * nuevos mientras llegan, ni si la lectura falla (la lección de H-1).
     */
    const vigentes = datos
        && datos.range === rango
        && (datos.supervisor_user_id ?? null) === supervisor
        ? datos
        : null;

    const exportar = async () => {
        setExportando(true);
        setErrorExport(null);
        try {
            await downloadReportExcel({ range: rango, supervisorUserId: supervisor });
        } catch {
            setErrorExport('The Excel file could not be generated. Try again.');
        } finally {
            setExportando(false);
        }
    };

    const nombre = supervisor == null
        ? 'All Supervisors'
        : (datos?.supervisors.find((s) => s.user_id === supervisor)?.name ?? '');
    const periodo = vigentes
        ? `${formatPeriod(rango, vigentes.start, vigentes.end)}${
            rango === 'week' ? `, ${vigentes.start.slice(0, 4)}` : ''
        }`
        : '';

    return (
        <div className="flex flex-col p-4 md:p-6">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        CER Route
                    </div>
                    <h1 className="text-xl font-semibold text-foreground md:text-2xl">
                        Reports
                    </h1>
                    <p className="text-xs text-muted-foreground md:text-sm">
                        Consolidated operational analysis
                    </p>
                </div>
                {puedeExportar && (
                    <Button onClick={exportar} disabled={exportando || !vigentes}>
                        {exportando ? 'Exporting…' : 'Export Excel'}
                    </Button>
                )}
            </div>

            {errorExport && (
                <p className="mb-3 text-xs text-destructive">{errorExport}</p>
            )}

            <ReportsToolbar
                supervisors={datos?.supervisors ?? []}
                supervisorUserId={supervisor}
                onSupervisorChange={setSupervisor}
                range={rango}
                onRangeChange={setRango}
                legend={periodo ? `${nombre} · ${periodo}` : nombre}
            />

            {!vigentes && cargando && (
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Loading reports…
                </p>
            )}
            {!vigentes && !cargando && error && (
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Reports could not be read. It will retry on its own.
                </p>
            )}

            {vigentes && (
                <>
                    {error && (
                        <p className="mb-3 text-xs text-muted-foreground">
                            Could not refresh just now. Showing the last known state.
                        </p>
                    )}
                    <ReportsKpis summary={vigentes.summary} />
                    <div className="grid gap-4 min-[1051px]:grid-cols-2">
                        <ReportsTimeline
                            groupedBy={vigentes.grouped_by}
                            groups={vigentes.groups}
                        />
                        <ReportsBreakdown rows={vigentes.breakdown} />
                    </div>
                </>
            )}
        </div>
    );
}

export default RouteReportsPage;
