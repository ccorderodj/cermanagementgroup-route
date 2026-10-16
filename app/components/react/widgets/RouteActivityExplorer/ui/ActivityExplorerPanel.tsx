import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useIsMobile } from '@/shared/lib/hooks/useMobile/useMobile';
import { useUser } from '@/app/providers/StoreProvider';
import {
    ExplorerActivityCards,
    ExplorerDaySummary,
    ExplorerFilterBar,
    ExplorerGroupList,
} from '@/features/RouteActivityExplorer';
import {
    fetchExplorer,
    fetchMyActivity,
    type ExplorerGroup,
    type ExplorerRange,
    type ExplorerView,
} from '@/entities/RouteActivityExplorer';

/**
 * Activity Explorer — la historia operativa registrada, para dos audiencias.
 *
 * - `admin` (`/admin/route/activity`): con selector de supervisor, contra
 *   `GET /api/activity-explorer` y `route.activity.read`.
 * - `self` (`/route/activity`, RTE08 personal): la actividad **propia**, sin
 *   selector, contra `GET /api/activity-explorer/me`. El sujeto lo pone el
 *   servidor con la sesión; aquí no hay nada que elegir.
 *
 * Es el mismo componente para que las dos vistas no diverjan: mismas pestañas,
 * misma bajada de nivel, mismo resumen y mismas tarjetas.
 *
 * El mecanismo de la jerarquía es el de la línea base
 * ----------------------------------------------------
 * `Year → Month → Week → Day → Activity` no se dibuja como un árbol ni como un
 * acordeón: V0.7 lo hace con **pestañas de rango** y **filas que bajan un
 * nivel**. El año agrupa por mes y cada fila dice `View month`; el mes agrupa
 * por semana; la semana por día; y el día enseña las paradas. Subir de nuevo es
 * pulsar una pestaña, que es lo que la línea base ofrece como vuelta.
 *
 * Qué cambia en móvil, y por qué sólo eso
 * ----------------------------------------
 * El mockup oculta en móvil los campos de la barra (`.fields-inline`). H-1
 * autoriza **una** excepción para el administrador: el selector de supervisor
 * sí se muestra. La fecha sigue oculta en móvil en las dos vistas.
 *
 * Sólo lectura
 * ------------
 * No hay editar, ni corregir, ni borrar. Es exploración histórica (PR-06).
 */

/** El nivel al que baja cada rango, según `groupRows()` del mockup. */
const BAJA_A: Record<string, ExplorerRange> = {
    month: 'month',
    week: 'week',
    day: 'day',
};

interface ActivityExplorerPanelProps {
    scope: 'admin' | 'self';
    /** Lo que va encima de la barra: la cabecera de la vista de administración. */
    header?: ReactNode;
}

export function ActivityExplorerPanel({ scope, header = null }: ActivityExplorerPanelProps) {
    const esMovil = useIsMobile();
    const propia = scope === 'self';
    const { hasUserPermission } = useUser();

    const [rango, setRango] = useState<ExplorerRange>('day');
    /**
     * El dia ancla. Arranca en `null` a proposito: el dia de negocio lo decide
     * el servidor, igual que el supervisor.
     *
     * Antes se inicializaba con `new Date()` del navegador, y eso abre la
     * pantalla en el dia equivocado siempre que el calendario del dispositivo
     * y el dia de negocio del tenant no coincidan -- un desfase horario, o
     * sencillamente que uno de los dos ya cruzo la medianoche. El sintoma es
     * el peor posible: `No recorded activity on this day` sobre una jornada
     * que si tuvo actividad.
     */
    const [fecha, setFecha] = useState<string | null>(null);
    /** Sólo en `admin`. En `self` se queda en `null`: no hay a quién elegir. */
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
     */
    const lecturaVigente = useRef(0);

    /**
     * Relee el nivel actual. Un fallo **no vacía la pantalla**: un error de red
     * no es "ese año no tuvo actividad" (FR-09).
     */
    const releer = useCallback(async () => {
        lecturaVigente.current += 1;
        const mia = lecturaVigente.current;
        setCargando(true);
        try {
            const cuerpo = propia
                ? await fetchMyActivity({ range: rango, date: fecha })
                : await fetchExplorer({ range: rango, date: fecha, supervisorUserId: supervisor });
            if (!vivo.current || mia !== lecturaVigente.current) return;
            setDatos(cuerpo);
            setError(false);
            // El servidor decide qué supervisor queda seleccionado cuando la
            // pantalla todavía no lo sabe. El alcance es suyo, no de aquí.
            if (!propia && supervisor == null && cuerpo.supervisor_user_id != null) {
                setSupervisor(cuerpo.supervisor_user_id);
            }
            // Y el dia, por el mismo motivo. En la primera lectura el rango es
            // `day`, asi que `start` es exactamente el dia de negocio vigente.
            if (fecha == null) {
                setFecha(cuerpo.start);
            }
        } catch {
            if (vivo.current && mia === lecturaVigente.current) setError(true);
        } finally {
            if (vivo.current && mia === lecturaVigente.current) setCargando(false);
        }
    }, [propia, rango, fecha, supervisor]);

    useEffect(() => { releer(); }, [releer]);

    /**
     * Los datos que se pueden pintar **como actuales**.
     *
     * - `admin`: los del supervisor seleccionado (H-1, FR2.6). Cambiar la fecha
     *   o el rango no cuenta: siguen siendo datos de la misma persona, y
     *   conservarlos durante un fallo es lo que FR-09 pide. Sin cambios.
     * - `self`: además, los del **rango y periodo** seleccionados (RTE08
     *   personal, FR-02.4): al cambiar de periodo, el anterior no se presenta
     *   bajo la pestaña nueva mientras llega, ni si la lectura falla.
     */
    const delSupervisor = datos
        && (supervisor == null || datos.supervisor_user_id === supervisor);
    const delPeriodo = datos
        && datos.range === rango
        && (fecha == null || (datos.start <= fecha && fecha <= datos.end));
    const vigentes = delSupervisor && (!propia || delPeriodo) ? datos : null;

    const bajarNivel = (grupo: ExplorerGroup) => {
        const destino = datos?.grouped_by ? BAJA_A[datos.grouped_by] : null;
        if (!destino) return;
        setFecha(grupo.drill_date);
        setRango(destino);
    };

    const aviso = error && vigentes && (
        <p className="mb-3 text-xs text-muted-foreground">
            Could not refresh just now. Showing the last known state.
        </p>
    );

    const barra = (
        <ExplorerFilterBar
            supervisors={datos?.supervisors ?? []}
            supervisorUserId={supervisor ?? datos?.supervisor_user_id ?? null}
            onSupervisorChange={setSupervisor}
            date={fecha ?? datos?.start ?? ''}
            onDateChange={setFecha}
            range={rango}
            onRangeChange={setRango}
            showDate={!esMovil}
            showSupervisor={!propia}
        />
    );

    if (cargando && !vigentes) {
        return (
            <>
                {header}
                {barra}
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Loading recorded activity…
                </p>
            </>
        );
    }

    if (error && !vigentes) {
        return (
            <>
                {header}
                {barra}
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Activity history could not be read. It will retry on its own.
                </p>
            </>
        );
    }

    return (
        <>
            {header}
            {aviso}
            {barra}

            {/*
              * En el día **no** hay título de periodo sobre el resumen: la
              * línea base pasa de la barra de filtros directamente a las
              * mini-estadísticas.
              */}
            {vigentes && vigentes.range === 'day' && (
                <>
                    {vigentes.summary && <ExplorerDaySummary summary={vigentes.summary} />}
                    <ExplorerActivityCards
                        activities={vigentes.activities}
                        mapEnabled={!propia && hasUserPermission('route.activity.map.read')}
                    />
                </>
            )}

            {vigentes && vigentes.range !== 'day' && vigentes.grouped_by && (
                <ExplorerGroupList
                    range={vigentes.range}
                    start={vigentes.start}
                    end={vigentes.end}
                    groupedBy={vigentes.grouped_by}
                    groups={vigentes.groups}
                    onDrill={bajarNivel}
                />
            )}
        </>
    );
}
