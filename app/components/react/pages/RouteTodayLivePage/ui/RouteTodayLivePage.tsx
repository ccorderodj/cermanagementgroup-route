import { useCallback, useEffect, useRef, useState } from 'react';
import { useIsMobile } from '@/shared/lib/hooks/useMobile/useMobile';
import {
    LiveMobileDetail, LiveMobileList, LiveSummary,
    LiveSupervisorDetail, LiveSupervisorTable,
} from '@/features/RouteLive';
import { fetchTodayLive, type LiveToday } from '@/entities/RouteLive';

/**
 * Today / Live — el estado operativo del día.
 *
 * Dos experiencias aprobadas, no una con dos anchos
 * --------------------------------------------------
 * V0.7 define un escritorio con tabla y panel lateral, y un móvil *list-first*
 * donde el detalle es una pantalla completa con vuelta. Son presentaciones
 * distintas y la página **elige** entre ellas: renderizar la de escritorio y
 * dejar que el CSS la estruje es exactamente lo que §2.3 y §14 prohíben.
 *
 * La frescura, y por qué no hay WebSocket
 * ----------------------------------------
 * Se relee cada treinta segundos mientras la pestaña está visible, y **se
 * detiene cuando no lo está**. Es el objetivo de FR-08 y no necesita
 * infraestructura nueva: un sondeo que se para solo cuesta una petición cada
 * medio minuto por administrador mirando, y §5 desaconseja montar WebSockets
 * sólo para esto.
 */
const INTERVALO_DE_REFRESCO_MS = 30_000;

export function RouteTodayLivePage() {
    const esMovil = useIsMobile();

    const [datos, setDatos] = useState<LiveToday | null>(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(false);
    const [seleccionado, setSeleccionado] = useState<number | null>(null);
    const [detalleMovil, setDetalleMovil] = useState<number | null>(null);

    const vivo = useRef(true);
    useEffect(() => () => { vivo.current = false; }, []);

    /**
     * Relee el estado. Un fallo **no vacía la pantalla**.
     *
     * FR-10 lo pide con un ejemplo que vale la pena recordar: un error de red
     * no es "el supervisor no está trabajando". Si ya hay datos se conservan y
     * se avisa de que pueden estar desactualizados; convertir la incertidumbre
     * en un estado de negocio sería afirmar algo que nadie sabe.
     */
    const releer = useCallback(async (silencioso = false) => {
        if (!silencioso) setCargando(true);
        try {
            const cuerpo = await fetchTodayLive();
            if (!vivo.current) return;
            setDatos(cuerpo);
            setError(false);
        } catch {
            if (!vivo.current) return;
            setError(true);
        } finally {
            if (vivo.current && !silencioso) setCargando(false);
        }
    }, []);

    useEffect(() => { releer(); }, [releer]);

    // El sondeo sólo corre con la pestaña visible. Al volver se relee de
    // inmediato en vez de esperar al siguiente turno, que es lo que hace que
    // mirar la pantalla después de un rato enseñe algo actual y no algo viejo.
    useEffect(() => {
        let temporizador: number | undefined;

        const detener = () => {
            if (temporizador !== undefined) window.clearInterval(temporizador);
            temporizador = undefined;
        };
        const arrancar = () => {
            detener();
            temporizador = window.setInterval(() => releer(true), INTERVALO_DE_REFRESCO_MS);
        };
        const alCambiarVisibilidad = () => {
            if (document.visibilityState === 'visible') {
                releer(true);
                arrancar();
            } else {
                detener();
            }
        };

        if (document.visibilityState === 'visible') arrancar();
        document.addEventListener('visibilitychange', alCambiarVisibilidad);
        return () => {
            detener();
            document.removeEventListener('visibilitychange', alCambiarVisibilidad);
        };
    }, [releer]);

    const supervisores = datos?.supervisors ?? [];
    const elegido = supervisores.find((s) => s.user_id === seleccionado)
        ?? supervisores[0]
        ?? null;
    const enDetalleMovil = supervisores.find((s) => s.user_id === detalleMovil) ?? null;

    const encabezado = (
        <div>
            <h1 className="text-xl font-semibold text-foreground">Today / Live</h1>
            <p className="text-sm text-muted-foreground">
                {esMovil
                    ? 'Supervisor status and mileage'
                    : 'Operational status and mileage'}
            </p>
            {error && datos && (
                <p
                    className="mt-2 text-xs text-muted-foreground"
                >
                    Could not refresh just now. Showing the last known state.
                </p>
            )}
        </div>
    );

    if (cargando && !datos) {
        return (
            <div className="flex flex-col gap-5 p-4 md:p-6">
                {encabezado}
                <p className="py-10 text-center text-sm text-muted-foreground">
                    Loading today&apos;s operational state…
                </p>
            </div>
        );
    }

    if (error && !datos) {
        return (
            <div className="flex flex-col gap-5 p-4 md:p-6">
                {encabezado}
                <p
                    className="py-10 text-center text-sm text-muted-foreground"
                >
                    Today / Live could not be read. It will retry on its own.
                </p>
            </div>
        );
    }

    // ── Móvil: lista primero, y el detalle es una pantalla entera ───────────
    if (esMovil) {
        return (
            <div className="flex flex-col gap-4 p-4">
                {enDetalleMovil ? (
                    <LiveMobileDetail
                        supervisor={enDetalleMovil}
                        onBack={() => setDetalleMovil(null)}
                    />
                ) : (
                    <>
                        {encabezado}
                        {datos && <LiveSummary summary={datos.summary} compact />}
                        <LiveMobileList
                            supervisors={supervisores}
                            onSelect={setDetalleMovil}
                        />
                    </>
                )}
            </div>
        );
    }

    // ── Escritorio: resumen, tabla y panel ──────────────────────────────────
    return (
        <div className="flex flex-col gap-5 p-4 md:p-6">
            {encabezado}
            {datos && <LiveSummary summary={datos.summary} />}
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <LiveSupervisorTable
                    supervisors={supervisores}
                    selectedId={elegido?.user_id ?? null}
                    onSelect={setSeleccionado}
                />
                <LiveSupervisorDetail supervisor={elegido} />
            </div>
        </div>
    );
}

export default RouteTodayLivePage;
