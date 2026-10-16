import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { useUser } from '@/app/providers/StoreProvider';
import { formatGroupLabel } from '@/entities/RouteActivityExplorer';
import {
    REPORT_RANGES,
    downloadReportExcel,
    fetchReport,
    formatReportPeriod,
    type ReportBreakdownRow,
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
 * Reports (RTE09): la pantalla del V0.7, con el periodo histórico y el desglose
 * interactivo de RTE09 E01.
 *
 * Cabecera con *Export Excel*, la barra con *All Supervisors* por defecto, las
 * pestañas Week / Month / Year y el **periodo concreto**, los cuatro KPIs y dos
 * tarjetas: *By day / week / month* y *Activity breakdown*. **Sin acordeón** y
 * **sin flechas** anterior/siguiente: el periodo se elige en su selector.
 *
 * Dos alcances distintos:
 * - el **periodo principal** (supervisor + tipo + periodo concreto) manda en los
 *   KPIs, la tarjeta izquierda y el Excel;
 * - el **subgrupo** elegido en la tarjeta izquierda acota sólo el desglose.
 *
 * Cambiar cualquier parte del periodo principal borra el subgrupo. Nada se
 * calcula aquí: el servidor decide el periodo en curso, los límites y las
 * cifras; la pantalla sólo guarda la selección y formatea.
 *
 * El periodo principal se refleja en la URL (`range`, `date`, `supervisor`)
 * para que una recarga lo conserve. `date` nunca sale del reloj del navegador:
 * es el inicio de una opción que dio el servidor.
 */

interface Seleccion {
    rango: ReportRange;
    /** Inicio del periodo elegido; `null`: el en curso, que decide el servidor. */
    ancla: string | null;
    supervisor: number | null;
}

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

/** La selección guardada en la URL, si es válida. Nunca una fecha inventada. */
function leerUrl(): Seleccion {
    const q = new URLSearchParams(window.location.search);
    const rango = q.get('range');
    const ancla = q.get('date');
    const supervisor = Number(q.get('supervisor'));
    return {
        rango: REPORT_RANGES.includes(rango as ReportRange) ? (rango as ReportRange) : 'week',
        ancla: ancla && FECHA.test(ancla) ? ancla : null,
        supervisor: Number.isInteger(supervisor) && supervisor > 0 ? supervisor : null,
    };
}

function escribirUrl({ rango, ancla, supervisor }: Seleccion): void {
    const q = new URLSearchParams(window.location.search);
    q.set('range', rango);
    if (ancla) q.set('date', ancla);
    else q.delete('date');
    if (supervisor != null) q.set('supervisor', String(supervisor));
    else q.delete('supervisor');
    window.history.replaceState(null, '', `${window.location.pathname}?${q.toString()}`);
}

/**
 * Las filas que se pintan en el desglose: las del periodo entero, las del
 * subgrupo si ya llegaron para **esta** selección, o `null` mientras llegan.
 */
function filasDelDesglose(
    vigentes: ReportView | null,
    grupo: string | null,
    clave: string | null,
    delGrupo: { clave: string; filas: ReportBreakdownRow[] } | null,
): ReportBreakdownRow[] | null {
    if (!vigentes) return null;
    if (!grupo) return vigentes.breakdown;
    return delGrupo?.clave === clave ? delGrupo.filas : null;
}

const ENTERO: Record<ReportRange, string> = {
    week: 'Whole week',
    month: 'Whole month',
    year: 'Whole year',
};

export function RouteReportsPage() {
    const { hasUserPermission } = useUser();
    const puedeExportar = hasUserPermission('route.reports.export');

    const [seleccion, setSeleccion] = useState<Seleccion>(leerUrl);
    const { rango, ancla, supervisor } = seleccion;
    /** Inicio del día / semana / mes elegido en la tarjeta izquierda. */
    const [grupo, setGrupo] = useState<string | null>(null);

    const [datos, setDatos] = useState<ReportView | null>(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(false);
    const [exportando, setExportando] = useState(false);
    const [errorExport, setErrorExport] = useState<string | null>(null);

    /** El desglose del subgrupo, con la clave de la selección que lo pidió. */
    const [desgloseGrupo, setDesgloseGrupo] = useState<
        { clave: string; filas: ReportBreakdownRow[] } | null
    >(null);
    const [errorGrupo, setErrorGrupo] = useState(false);

    const vivo = useRef(true);
    useEffect(() => () => { vivo.current = false; }, []);

    useEffect(() => { escribirUrl(seleccion); }, [seleccion]);

    /** La lectura vigente: una respuesta vieja no pisa a la nueva. */
    const lecturaVigente = useRef(0);

    const releer = useCallback(async () => {
        lecturaVigente.current += 1;
        const mia = lecturaVigente.current;
        setCargando(true);
        try {
            const cuerpo = await fetchReport({ range: rango, supervisorUserId: supervisor, date: ancla });
            if (!vivo.current || mia !== lecturaVigente.current) return;
            setDatos(cuerpo);
            setError(false);
        } catch {
            if (vivo.current && mia === lecturaVigente.current) setError(true);
        } finally {
            if (vivo.current && mia === lecturaVigente.current) setCargando(false);
        }
    }, [rango, ancla, supervisor]);

    useEffect(() => { releer(); }, [releer]);

    /**
     * Sólo se pinta lo que corresponde a la selección actual: al cambiar de
     * supervisor, de rango o de periodo, los datos anteriores no se presentan
     * como los nuevos mientras llegan, ni si la lectura falla (la lección de H-1).
     */
    const vigentes = datos
        && datos.range === rango
        && (datos.supervisor_user_id ?? null) === supervisor
        && (ancla == null || datos.start === ancla)
        ? datos
        : null;

    /** La clave de un desglose: el periodo principal **y** el subgrupo. */
    const claveGrupo = vigentes && grupo
        ? `${rango}|${vigentes.start}|${supervisor ?? 'all'}|${grupo}`
        : null;

    useEffect(() => {
        if (!claveGrupo || !vigentes || !grupo) return undefined;
        let vigente = true;
        setErrorGrupo(false);
        fetchReport({
            range: rango,
            supervisorUserId: supervisor,
            date: vigentes.start,
            group: grupo,
        })
            .then((cuerpo) => {
                if (vigente && vivo.current) {
                    setDesgloseGrupo({ clave: claveGrupo, filas: cuerpo.breakdown });
                }
            })
            .catch(() => {
                if (vigente && vivo.current) setErrorGrupo(true);
            });
        return () => { vigente = false; };
        // `vigentes.start` está dentro de `claveGrupo`.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [claveGrupo]);

    // Cambiar el periodo principal borra el subgrupo: no se arrastra un día,
    // semana o mes elegido a otro periodo.
    const cambiarSupervisor = (valor: number | null) => {
        setGrupo(null);
        setSeleccion((s) => ({ ...s, supervisor: valor }));
    };
    const cambiarRango = (valor: ReportRange) => {
        setGrupo(null);
        // El periodo en curso del nuevo tipo lo decide el servidor.
        setSeleccion((s) => ({ ...s, rango: valor, ancla: null }));
    };
    const cambiarPeriodo = (inicio: string) => {
        setGrupo(null);
        setSeleccion((s) => ({ ...s, ancla: inicio }));
    };

    const exportar = async () => {
        if (!vigentes) return;
        setExportando(true);
        setErrorExport(null);
        try {
            // El periodo principal, nunca el subgrupo del desglose.
            await downloadReportExcel({
                range: rango,
                supervisorUserId: supervisor,
                date: vigentes.start,
            });
        } catch {
            setErrorExport('The Excel file could not be generated. Try again.');
        } finally {
            setExportando(false);
        }
    };

    const nombre = supervisor == null
        ? 'All Supervisors'
        : (datos?.supervisors.find((s) => s.user_id === supervisor)?.name ?? '');
    const periodo = vigentes ? formatReportPeriod(rango, vigentes.start, vigentes.end) : '';

    const grupoElegido = vigentes && grupo
        ? vigentes.groups.find((g) => g.start === grupo) ?? null
        : null;
    const alcance = grupoElegido && vigentes
        ? `Showing ${formatGroupLabel(vigentes.grouped_by, { ...grupoElegido, drill_date: grupoElegido.start })} only`
        : `Showing ${ENTERO[rango].toLowerCase()}`;
    const filasDesglose = filasDelDesglose(vigentes, grupo, claveGrupo, desgloseGrupo);

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
                onSupervisorChange={cambiarSupervisor}
                range={rango}
                onRangeChange={cambiarRango}
                legend={periodo ? `${nombre} · ${periodo}` : nombre}
                periods={vigentes?.periods ?? []}
                periodStart={vigentes?.start ?? null}
                onPeriodChange={cambiarPeriodo}
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
                            selectedStart={grupo}
                            onSelect={setGrupo}
                        />
                        {errorGrupo && grupo ? (
                            <p className="py-8 text-center text-sm text-muted-foreground">
                                The breakdown for this selection could not be read. Try again.
                            </p>
                        ) : (
                            <ReportsBreakdown
                                rows={filasDesglose ?? []}
                                scope={alcance}
                                loading={filasDesglose == null}
                            />
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

export default RouteReportsPage;
