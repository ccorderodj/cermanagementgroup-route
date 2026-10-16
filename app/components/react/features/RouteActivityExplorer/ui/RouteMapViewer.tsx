import { useCallback, useEffect, useRef, useState } from 'react';
import * as L from 'leaflet';
import { Button } from '@/shared/ui/shadcn/new-york';
import { fetchTripMap, type TripMap } from '@/entities/RouteActivityExplorer';
import './RouteMapViewer.scss';

/** Cómo se llama cada punto en la leyenda y en el lector de pantalla. */
const NOMBRE_DEL_PUNTO: Record<string, string> = {
    start_trip: 'Start',
    change_plan: 'Change of plan',
    arrived: 'Arrival',
};

type Estado =
    | { tipo: 'cargando' }
    | { tipo: 'error' }
    | { tipo: 'sin_puntos' }
    | { tipo: 'listo'; mapa: TripMap };

interface RouteMapViewerProps {
    tripId: number;
}

/**
 * El visor de una tarjeta de Activity Admin: los puntos con los que se
 * calculó el millaje del viaje, sobre un mapa base.
 *
 * Lo que enseña y lo que no
 * -------------------------
 * Marcadores **numerados en orden** —salida, cambios de plan, llegada— y
 * **ninguna línea**: el cálculo sólo pidió la distancia, no existe el trazado
 * por carretera, y una recta entre puntos lo fingiría (FR-04). La leyenda lo
 * dice.
 *
 * Coste y limpieza
 * ----------------
 * Este módulo —Leaflet y su CSS incluidos— se carga sólo al pulsar `View
 * Route`; antes no hay ni una petición de teselas. Al cerrar, el mapa se
 * destruye (`map.remove()`).
 *
 * Táctil
 * ------
 * En móvil no se arrastra con un dedo: arrastrar el mapa atraparía el
 * desplazamiento de la página. Se hace zoom con dos dedos o con los botones.
 */
export default function RouteMapViewer({ tripId }: RouteMapViewerProps) {
    const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' });
    const contenedor = useRef<HTMLDivElement | null>(null);

    const cargar = useCallback(async () => {
        setEstado({ tipo: 'cargando' });
        try {
            const mapa = await fetchTripMap(tripId);
            setEstado(mapa.available && mapa.points.length > 0
                ? { tipo: 'listo', mapa }
                : { tipo: 'sin_puntos' });
        } catch {
            setEstado({ tipo: 'error' });
        }
    }, [tripId]);

    useEffect(() => {
        cargar();
    }, [cargar]);

    useEffect(() => {
        if (estado.tipo !== 'listo' || !contenedor.current) return undefined;
        const { points, tiles } = estado.mapa;
        const mapa = L.map(contenedor.current, {
            scrollWheelZoom: false,
            dragging: !L.Browser.mobile,
            attributionControl: true,
        });
        L.tileLayer(tiles.url, {
            attribution: tiles.attribution,
            maxZoom: 19,
            // OSM exige un Referer válido; la página lo restringe a su propio
            // origen, así que se concede sólo a las teselas.
            referrerPolicy: 'strict-origin-when-cross-origin',
        }).addTo(mapa);

        const coordenadas: L.LatLngExpression[] = points.map((p) => [p.latitude, p.longitude]);
        points.forEach((p) => {
            const nombre = NOMBRE_DEL_PUNTO[p.kind] ?? p.kind;
            L.marker([p.latitude, p.longitude], {
                icon: L.divIcon({
                    className: '',
                    html: `<span class="cer-route-pin">${p.sequence}</span>`,
                    iconSize: [26, 26],
                    iconAnchor: [13, 13],
                }),
                title: `${p.sequence} · ${nombre}`,
                alt: `${p.sequence} · ${nombre}`,
                keyboard: true,
            }).bindTooltip(`${p.sequence} · ${nombre}`).addTo(mapa);
        });
        if (coordenadas.length === 1) {
            mapa.setView(coordenadas[0], 15);
        } else {
            // Más margen abajo: ahí va la atribución, y no debe tapar un punto.
            mapa.fitBounds(L.latLngBounds(coordenadas), {
                paddingTopLeft: [28, 28],
                paddingBottomRight: [28, 48],
                maxZoom: 16,
            });
        }
        return () => {
            mapa.remove();
        };
    }, [estado]);

    return (
        <div className="border-t border-border px-3 py-2.5 xl:px-4 xl:py-3.5" id={`route-map-${tripId}`}>
            {estado.tipo === 'cargando' && (
                <p className="text-xs text-muted-foreground" role="status">Loading route points…</p>
            )}
            {estado.tipo === 'error' && (
                <div className="flex flex-wrap items-center gap-2" role="alert">
                    <p className="text-xs text-destructive">The route points could not be loaded.</p>
                    <Button type="button" variant="outline" size="sm" onClick={cargar}>
                        Retry
                    </Button>
                </div>
            )}
            {estado.tipo === 'sin_puntos' && (
                <p className="text-xs text-muted-foreground">
                    Route points are not available for this trip.
                </p>
            )}
            {estado.tipo === 'listo' && (
                <div className="flex flex-col gap-2">
                    <div
                        ref={contenedor}
                        className="h-56 w-full overflow-hidden rounded-md border border-border sm:h-72"
                        role="region"
                        aria-label="Map of the points used to calculate this trip's mileage"
                    />
                    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-foreground">
                        {estado.mapa.points.map((p) => (
                            <li key={p.sequence}>
                                <b className="font-semibold">{p.sequence}</b>
                                {' · '}
                                {NOMBRE_DEL_PUNTO[p.kind] ?? p.kind}
                            </li>
                        ))}
                    </ol>
                    <p className="text-xs text-muted-foreground">
                        Points used to calculate the official miles
                        {estado.mapa.provider === 'tomtom' ? ' (TomTom)' : ''}. Not the route driven: no line is
                        drawn between them.
                    </p>
                </div>
            )}
        </div>
    );
}
