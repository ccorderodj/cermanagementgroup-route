import { useCallback, useEffect, useRef, useState } from 'react';
import { useIsMobile } from '@/shared/lib/hooks/useMobile/useMobile';
import {
    ExplorerActivityCards,
    ExplorerDaySummary,
    ExplorerFilterBar,
    ExplorerGroupList,
} from '@/features/RouteActivityExplorer';
import {
    fetchExplorer,
    type ExplorerGroup,
    type ExplorerRange,
    type ExplorerView,
} from '@/entities/RouteActivityExplorer';

/**
 * Activity Explorer — la historia operativa registrada.
 *
 * El mecanismo de la jerarquía es el de la línea base
 * ----------------------------------------------------
 * `Year → Month → Week → Day → Activity` no se dibuja como un árbol ni como un
 * acordeón: V0.7 lo hace con **pestañas de rango** y **filas que bajan un
 * nivel**. El año agrupa por mes y cada fila dice `View month`; el mes agrupa
 * por semana; la semana por día; y el día enseña las paradas. Subir de nuevo es
 * pulsar una pestaña, que es lo que la línea base ofrece como vuelta.
 *
 * Inventar un acordeón habría sido más "moderno" y habría roto §2.4, que manda
 * tomar el mecanismo visible del mockup y no suponerlo.
 *
 * Qué cambia en móvil, y por qué sólo eso
 * ----------------------------------------
 * El mockup tiene un ámbito móvil explícito para esta pantalla: la barra de
 * filtros se apila y **los campos de supervisor y fecha no se muestran**
 * (`.app.device-mobile .fields-inline { display: none }`). Lo demás es la misma
 * jerarquía con la misma información, reflujada. No hay una arquitectura de
 * información distinta para móvil aquí —a diferencia de Today / Live, que sí la
 * tiene— así que no se inventa una.
 *
 * Sólo lectura
 * ------------
 * No hay editar, ni corregir, ni borrar. RTE08 es exploración histórica (PR-06);
 * cualquier capacidad de corrección es otro checkpoint.
 */

/** El nivel al que baja cada rango, según `groupRows()` del mockup. */
const BAJA_A: Record<string, ExplorerRange> = {
    month: 'month',
    week: 'week',
    day: 'day',
};

function hoyLocal(): string {
    const d = new Date();
    const mes = String(d.getMonth() + 1).padStart(2, '0');
    const dia = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mes}-${dia}`;
}

export function RouteActivityExplorerPage() {
    const esMovil = useIsMobile();

    const [rango, setRango] = useState<ExplorerRange>('day');
    const [fecha, setFecha] = useState<string>(hoyLocal);
    const [supervisor, setSupervisor] = useState<number | null>(null);

    const [datos, setDatos] = useState<ExplorerView | null>(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(false);

    const vivo = useRef(true);
    useEffect(() => () => { vivo.current = false; }, []);

    /**
     * Cuál es la lectura vigente. Sin esto hay un defecto real, encontrado por
     * el test de navegador de este checkpoint: cambiar la fecha y pulsar un
     * rango enseguida lanza dos lecturas, y si la **primera** contesta después
     * se pinta el nivel viejo mientras la pestaña marca el nuevo.
     *
     * Es el mismo problema que la captura de odómetro: no basta con comprobar
     * que el componente sigue montado, hay que comprobar que la respuesta que
     * llega es la que se está esperando.
     */
    const lecturaVigente = useRef(0);

    /**
     * Relee el nivel actual. Un fallo **no vacía la pantalla**.
     *
     * FR-09 lo pide con el ejemplo que importa: un error de red no es "ese año
     * no tuvo actividad". Si ya hay datos se conservan y se avisa; convertir un
     * fallo de lectura en un periodo vacío sería afirmar algo que nadie sabe.
     */
    const releer = useCallback(async () => {
        lecturaVigente.current += 1;
        const mia = lecturaVigente.current;
        setCargando(true);
        try {
            const cuerpo = await fetchExplorer({
                range: rango,
                date: fecha,
                supervisorUserId: supervisor,
            });
            if (!vivo.current || mia !== lecturaVigente.current) return;
            setDatos(cuerpo);
            setError(false);
            // El servidor decide qué supervisor queda seleccionado cuando la
            // pantalla todavía no lo sabe. El alcance es suyo, no de aquí.
            if (supervisor == null && cuerpo.supervisor_user_id != null) {
                setSupervisor(cuerpo.supervisor_user_id);
            }
        } catch {
            if (vivo.current && mia === lecturaVigente.current) setError(true);
        } finally {
            if (vivo.current && mia === lecturaVigente.current) setCargando(false);
        }
    }, [rango, fecha, supervisor]);

    useEffect(() => { releer(); }, [releer]);

    const bajarNivel = (grupo: ExplorerGroup) => {
        const destino = datos?.grouped_by ? BAJA_A[datos.grouped_by] : null;
        if (!destino) return;
        setFecha(grupo.drill_date);
        setRango(destino);
    };

    const encabezado = (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    CER Route
                </div>
                <h1 className="text-xl font-semibold text-foreground md:text-2xl">
                    Activity
                </h1>
                <p className="text-xs text-muted-foreground md:text-sm">
                    Explore operational history by supervisor and period
                </p>
            </div>
            <a
                href="/admin/route/today"
                className="inline-flex h-9 items-center rounded-md border border-border bg-card px-3 text-sm font-medium text-foreground"
            >
                Back to Today
            </a>
        </div>
    );

    const aviso = error && datos && (
        <p className="mb-3 text-xs text-muted-foreground">
            Could not refresh just now. Showing the last known state.
        </p>
    );

    const barra = (
        <ExplorerFilterBar
            supervisors={datos?.supervisors ?? []}
            supervisorUserId={supervisor ?? datos?.supervisor_user_id ?? null}
            onSupervisorChange={setSupervisor}
            date={fecha}
            onDateChange={setFecha}
            range={rango}
            onRangeChange={setRango}
            showFields={!esMovil}
        />
    );

    if (cargando && !datos) {
        return (
            <div className="flex flex-col p-4 md:p-6">
                {encabezado}
                {barra}
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Loading recorded activity…
                </p>
            </div>
        );
    }

    if (error && !datos) {
        return (
            <div className="flex flex-col p-4 md:p-6">
                {encabezado}
                {barra}
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Activity history could not be read. It will retry on its own.
                </p>
            </div>
        );
    }

    return (
        <div className="flex flex-col p-4 md:p-6">
            {encabezado}
            {aviso}
            {barra}

            {/*
              * En el día **no** hay título de periodo sobre el resumen: la
              * línea base pasa de la barra de filtros directamente a las
              * mini-estadísticas. Lo había añadido y la comparación con la
              * captura del mockup lo delató — §17 prohíbe añadidos visuales, y
              * la fecha ya está en su selector.
              */}
            {datos && datos.range === 'day' && (
                <>
                    {datos.summary && <ExplorerDaySummary summary={datos.summary} />}
                    <ExplorerActivityCards activities={datos.activities} />
                </>
            )}

            {datos && datos.range !== 'day' && datos.grouped_by && (
                <ExplorerGroupList
                    range={datos.range}
                    start={datos.start}
                    end={datos.end}
                    groupedBy={datos.grouped_by}
                    groups={datos.groups}
                    onDrill={bajarNivel}
                />
            )}
        </div>
    );
}

export default RouteActivityExplorerPage;
