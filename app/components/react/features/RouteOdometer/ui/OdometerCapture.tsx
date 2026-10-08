import { useCallback, useEffect, useRef, useState } from 'react';
import {
    Button, Input, Label, Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue, Textarea,
} from '@/shared/ui/shadcn/new-york';
import { normalizeApiError } from '@/shared/api';
import { useUser } from '@/app/providers/StoreProvider';
import {
    findStagedOdometerPhoto,
    markStagedOdometerPhotoFailed,
    odometerPhotoKey,
    removeStagedOdometerPhoto,
    stageOdometerPhoto,
    type PendingOdometerPhoto,
} from '@/shared/lib/offlineQueue';
import {
    confirmOdometerReading,
    ODOMETER_EXCEPTION_REASONS,
    ODOMETER_REASON_LABELS,
    readingAsNumber,
    requestOdometerException,
    uploadOdometerPhoto,
    type OdometerEnd,
    type OdometerEvidence,
    type OdometerExceptionReason,
} from '@/entities/RouteOdometer';

/**
 * Capturar la lectura del cuentakilómetros.
 *
 * Se renderiza **debajo** del contexto del viaje que el supervisor ya eligió,
 * no encima de él: el plan sigue a la vista mientras resuelve la foto, y al
 * terminar vuelve exactamente a ese mismo flujo sin volver a elegir nada.
 *
 * El camino normal es foto y confirmación
 * ----------------------------------------
 * Si el OCR sugiere algo, se ofrece como borrador editable. Si no sugiere nada
 * —que es lo que hace el despliegue por defecto— el supervisor teclea lo que
 * ve, y **eso sigue siendo evidencia fotográfica**: no pide permiso a nadie.
 * Esta pantalla no llama "manual" a ese caso, porque llamarlo así empujaría a
 * la gente hacia la excepción sin necesitarla.
 *
 * Teclear sin foto es otra cosa
 * ------------------------------
 * No hay botón de "escribir a mano" suelto. Hay "no puedo hacer la foto", que
 * abre una solicitud con motivo y espera a un administrador. Mientras espera,
 * el supervisor puede seguir trabajando en lo que no sea conducir — pero no
 * puede salir, y la pantalla lo dice con esas palabras.
 */

interface OdometerCaptureProps {
    sessionId: number;
    end: OdometerEnd;
    evidence: OdometerEvidence;
    /** Se llama cuando el extremo queda resuelto y el flujo puede continuar. */
    onResolved: () => void | Promise<void>;
    /** Se llama al pedir la excepción, para que la pantalla se recargue. */
    onChanged?: () => void | Promise<void>;
    onCancel?: () => void;
}

const TITULOS: Record<OdometerEnd, string> = {
    start: 'Starting odometer',
    end: 'Ending odometer',
};

export function OdometerCapture(props: OdometerCaptureProps) {
    const {
        sessionId, end, evidence, onResolved, onChanged, onCancel,
    } = props;

    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lectura, setLectura] = useState('');
    const [sugerencia, setSugerencia] = useState<number | null>(
        readingAsNumber(evidence.ocr_detected_reading),
    );
    const [tieneFoto, setTieneFoto] = useState(
        evidence.captured_at !== null && evidence.captured_at !== undefined,
    );
    const [pidiendoExcepcion, setPidiendoExcepcion] = useState(false);
    const [motivo, setMotivo] = useState<OdometerExceptionReason | ''>('');
    const [nota, setNota] = useState('');
    const archivo = useRef<HTMLInputElement>(null);
    /**
     * Si lo que hay en el campo lo puso el OCR o lo tecleó la persona.
     *
     * Decide qué pasa al rehacer la foto, y la diferencia importa: una
     * sugerencia pertenece a **la foto de la que salió** y no puede sobrevivir
     * a su reemplazo, mientras que un número que el supervisor tecleó mirando
     * el salpicadero sigue describiendo el mismo odómetro. Borrarle lo que
     * escribió porque repitió la foto le haría teclearlo otra vez sin motivo.
     */
    const lecturaEsSugerida = useRef(false);
    /**
     * El número de la captura en curso.
     *
     * Dos subidas pueden solaparse —el botón se deshabilita, pero una
     * reconexión o un reintento del navegador no pasan por el botón— y la
     * respuesta de la primera puede llegar **después** de la segunda. Sin este
     * contador, el OCR de la foto descartada escribiría su sugerencia sobre la
     * foto nueva: exactamente lo que FR-05 prohíbe. La respuesta que no
     * corresponde a la captura actual se descarta.
     */
    const capturaActual = useRef(0);

    const { userLogged } = useUser();
    /**
     * La clave de la foto en espera de **esta** tarea.
     *
     * `null` mientras no se sepa quién es el usuario —la cookie se lee en un
     * efecto del proveedor, así que el primer render no la tiene—. Sin clave no
     * se guarda nada: una foto en un almacén sin dueño podría acabar
     * enseñándosele a otro supervisor que comparta el teléfono.
     */
    const clave = userLogged
        ? odometerPhotoKey(userLogged.user_id, sessionId, end)
        : null;
    /** La foto que el aparato tiene y el servidor todavía no. */
    const [enEspera, setEnEspera] = useState<PendingOdometerPhoto | null>(null);

    const fallo = (err: unknown) => setError(normalizeApiError(err).message);

    /**
     * Sube la foto y reconcilia lo que quede guardado en el aparato.
     *
     * Separada de `subirFoto` porque la ejecutan dos caminos: la captura nueva
     * y el reintento de una que quedó en espera. El `captura` que recibe es lo
     * que permite descartar una respuesta que llega después de que el
     * supervisor haya rehecho la foto.
     */
    const intentarSubida = useCallback(async (
        archivoAEnviar: File,
        captura: number,
        claveDeLaFoto: string | null,
    ) => {
        try {
            const resultado = await uploadOdometerPhoto(sessionId, end, archivoAEnviar);
            if (capturaActual.current !== captura) return;

            // El servidor la tiene: **ahora** se puede retirar la copia local.
            // Antes de este punto, el aparato es el único sitio donde existe.
            if (claveDeLaFoto) {
                await removeStagedOdometerPhoto(claveDeLaFoto).catch(() => {});
            }
            setEnEspera(null);

            const sugerido = readingAsNumber(resultado.ocr_suggestion);
            setSugerencia(sugerido);
            // La sugerencia se ofrece como borrador editable, nunca como hecho:
            // quien confirma es la persona que está mirando el salpicadero.
            if (sugerido !== null) {
                setLectura(String(sugerido));
                lecturaEsSugerida.current = true;
            }
            setTieneFoto(true);
        } catch (err) {
            if (capturaActual.current !== captura) return;
            if (claveDeLaFoto) {
                const mensaje = normalizeApiError(err).message;
                await markStagedOdometerPhotoFailed(claveDeLaFoto, mensaje).catch(() => {});
                const pendiente = await findStagedOdometerPhoto(claveDeLaFoto)
                    .catch(() => undefined);
                // Si la foto sigue guardada, lo que se enseña es eso y no un
                // error pelado: el supervisor no tiene que volver a hacerla.
                if (pendiente) setEnEspera(pendiente);
            }
            fallo(err);
        } finally {
            if (capturaActual.current === captura) setBusy(false);
        }
    }, [sessionId, end]);

    const subirFoto = async (foto: File) => {
        const captura = capturaActual.current + 1;
        capturaActual.current = captura;

        setBusy(true);
        setError(null);
        // Lo de la foto anterior se va **antes** de subir la nueva, no al
        // recibir la respuesta: mientras la subida está en vuelo, la pantalla
        // ya no puede estar enseñando una sugerencia de una foto que el
        // supervisor acaba de reemplazar.
        setSugerencia(null);
        if (lecturaEsSugerida.current) {
            setLectura('');
            lecturaEsSugerida.current = false;
        }

        // Durabilidad **antes** de la red (FR-06). Se espera la escritura: es
        // lo que convierte "el aparato tiene la foto" en un hecho en vez de una
        // intención. Lanzarlo en paralelo con el POST dejaría una ventana en la
        // que Android puede recrear la página y la foto no está en ningún sitio.
        if (clave) {
            try {
                await stageOdometerPhoto({
                    id: clave,
                    sessionId,
                    end,
                    blob: foto,
                    fileName: foto.name || 'odometer.jpg',
                    contentType: foto.type || 'image/jpeg',
                    capturedAt: new Date().toISOString(),
                });
            } catch {
                // Cuota llena, modo privado, almacenamiento bloqueado. No se
                // interrumpe la captura por esto: se pierde la red de
                // seguridad, no la foto que se está subiendo ahora mismo.
            }
        }

        await intentarSubida(foto, captura, clave);
    };

    /** Reintenta la que quedó guardada, sin volver a pedirle la foto a nadie. */
    const reintentarEnEspera = useCallback(async (pendiente: PendingOdometerPhoto) => {
        const captura = capturaActual.current + 1;
        capturaActual.current = captura;
        setBusy(true);
        setError(null);
        const archivoGuardado = new File([pendiente.blob], pendiente.fileName, {
            type: pendiente.contentType,
        });
        await intentarSubida(archivoGuardado, captura, pendiente.id);
    }, [intentarSubida]);

    /**
     * Qué estado se restaura cuando la página vuelve a nacer (FR-08).
     *
     * Tres casos y **ninguno se inventa**:
     *
     * 1. el servidor ya tiene la foto —`captured_at` lo dice— y entonces la
     *    verdad es del dominio: se retira la copia local, que ya no protege
     *    nada y sólo ocuparía espacio en el teléfono;
     * 2. hay una foto guardada y el servidor no la tiene: se enseña como
     *    pendiente y se reintenta, **sin** afirmar que esté subida;
     * 3. no hay ninguna de las dos: el estado normal de "haz la foto".
     */
    useEffect(() => {
        if (!clave) return undefined;
        let vivo = true;

        (async () => {
            if (tieneFoto) {
                await removeStagedOdometerPhoto(clave).catch(() => {});
                return;
            }
            const pendiente = await findStagedOdometerPhoto(clave).catch(() => undefined);
            if (!vivo || !pendiente) return;
            setEnEspera(pendiente);
            await reintentarEnEspera(pendiente);
        })();

        return () => { vivo = false; };
    }, [clave, tieneFoto, reintentarEnEspera]);

    /**
     * Y cuando vuelve la cobertura, se reintenta sin que nadie pulse nada.
     *
     * Es la mitad de FR-06 que el supervisor nota: pierde la red en el
     * aparcamiento, hace la foto, y para cuando sale a la calle ya está subida.
     */
    useEffect(() => {
        if (!enEspera || busy) return undefined;
        // `catch` vacío porque `intentarSubida` ya trata sus errores y deja la
        // foto guardada: aquí no queda nada que decidir.
        const alVolverLaRed = () => { reintentarEnEspera(enEspera).catch(() => {}); };
        window.addEventListener('online', alVolverLaRed);
        return () => window.removeEventListener('online', alVolverLaRed);
    }, [enEspera, busy, reintentarEnEspera]);

    const confirmar = async () => {
        setBusy(true);
        setError(null);
        try {
            await confirmOdometerReading(sessionId, end, lectura.trim());
            await onResolved();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    const pedirExcepcion = async () => {
        if (!motivo) return;
        setBusy(true);
        setError(null);
        try {
            await requestOdometerException(sessionId, end, motivo, nota);
            setPidiendoExcepcion(false);
            await onChanged?.();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    /**
     * El cierre no espera a nadie, y por eso aquí hay dos reglas y no una.
     *
     * Pedida la excepción, el servidor la aprueba al instante en el extremo de
     * cierre, así que lo normal es ver `exception_approved`. Pero una jornada
     * que pidió la suya antes de esta corrección se quedó en
     * `exception_requested`, y el servidor también la deja teclear: la lectura
     * de cierre es obligatoria para terminar el día, y tratar ese estado como
     * "espera" dejaría al supervisor sin poder teclear ni cerrar.
     *
     * En el inicio no se toca: ahí la aprobación protege que nadie salga a
     * conducir sin evidencia, y esperar es el comportamiento correcto.
     */
    const esCierre = end === 'end';
    const aprobada = evidence.status === 'exception_approved'
        || (esCierre && evidence.status === 'exception_requested');
    const esperando = !esCierre && evidence.status === 'exception_requested';
    const puedeConfirmar = (tieneFoto || aprobada)
        && lectura.trim() !== ''
        && Number.isFinite(Number(lectura));

    const aviso = (
        <p className="text-center text-xs text-muted-foreground">
            {esCierre
                ? 'Your workday stays open until this reading is recorded.'
                : 'You can keep doing work that does not involve driving, but you '
                  + 'cannot start a trip until this reading is recorded.'}
        </p>
    );

    const entradaDeFoto = (
        <input
            ref={archivo}
            type="file"
            accept="image/*"
            // Abre la cámara trasera en el móvil, que es donde se usa esto. En
            // escritorio degrada a un selector de archivo normal.
            capture="environment"
            className="hidden"
            data-testid="OdometerPhotoInput"
            onChange={(e) => {
                const foto = e.target.files?.[0];
                if (foto) subirFoto(foto);
                e.target.value = '';
            }}
        />
    );

    // ── Esperando a que un administrador decida ─────────────────────────────
    if (esperando) {
        return (
            <section
                data-testid="OdometerCapture"
                className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5"
            >
                <p className="text-center text-base font-medium text-foreground">
                    {TITULOS[end]}
                </p>
                <p className="text-center text-sm text-foreground">
                    Your request to enter the reading without a photo is waiting
                    for review.
                </p>
                {aviso}
                <Button
                    variant="outline"
                    className="h-12 w-full"
                    disabled={busy}
                    onClick={() => archivo.current?.click()}
                >
                    Take the photo after all
                </Button>
                {entradaDeFoto}
                {error && (
                    <p className="text-center text-sm text-destructive">{error}</p>
                )}
                {onCancel && (
                    <Button variant="ghost" disabled={busy} onClick={onCancel}>
                        Not now
                    </Button>
                )}
            </section>
        );
    }

    // ── Pidiendo la excepción ───────────────────────────────────────────────
    if (pidiendoExcepcion) {
        return (
            <section
                data-testid="OdometerExceptionRequest"
                className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
            >
                <p className="text-base font-medium text-foreground">
                    Why can&apos;t you take the photo?
                </p>
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-reason">Reason</Label>
                    <Select
                        value={motivo}
                        onValueChange={(v) => setMotivo(v as OdometerExceptionReason)}
                    >
                        <SelectTrigger id="odometer-reason" className="h-12">
                            <SelectValue placeholder="Choose one" />
                        </SelectTrigger>
                        <SelectContent>
                            {ODOMETER_EXCEPTION_REASONS.map((codigo) => (
                                <SelectItem key={codigo} value={codigo}>
                                    {ODOMETER_REASON_LABELS[codigo]}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-note">
                        Anything to add
                        <span className="ml-1 text-muted-foreground">(optional)</span>
                    </Label>
                    <Textarea
                        id="odometer-note"
                        value={nota}
                        rows={2}
                        onChange={(e) => setNota(e.target.value)}
                    />
                </div>
                <p className="text-xs text-muted-foreground">
                    {esCierre
                        ? 'Next you will enter the reading yourself. Your workday '
                          + 'stays open until you confirm it.'
                        : 'Someone with admin access reviews this. Until it is '
                          + 'approved and you enter the reading, you cannot start '
                          + 'a trip.'}
                </p>
                {error && (
                    <p className="text-center text-sm text-destructive">{error}</p>
                )}
                <Button
                    size="lg"
                    className="h-14 w-full"
                    disabled={busy || !motivo}
                    onClick={pedirExcepcion}
                >
                    Send request
                </Button>
                <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => setPidiendoExcepcion(false)}
                >
                    Back
                </Button>
            </section>
        );
    }

    // ── Camino normal, y la entrada manual ya autorizada ────────────────────
    return (
        <section
            data-testid="OdometerCapture"
            className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
        >
            <div className="text-center">
                <p className="text-base font-medium text-foreground">
                    {TITULOS[end]}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                    {aprobada
                        ? 'Approved: enter the reading you can see on the vehicle.'
                        : 'Take a photo of the odometer, then confirm the reading.'}
                </p>
            </div>

            {/*
              * La foto está en el aparato y el servidor todavía no la tiene.
              *
              * Lo que dice este bloque es literalmente eso. No dice "subida",
              * porque no lo está, y no dice "error", porque el supervisor no
              * ha perdido nada ni tiene que rehacer la foto: lo único que falta
              * es cobertura. FR-08 prohíbe afirmar una persistencia que no ha
              * ocurrido, y es la clase de mentira que cuesta una evidencia.
              */}
            {!aprobada && enEspera !== null && !tieneFoto && (
                <div
                    data-testid="OdometerPhotoPending"
                    className="rounded-md border border-border bg-muted/40 p-3"
                >
                    <p className="text-center text-sm text-foreground">
                        Your photo is saved on this phone. It has not reached the
                        server yet.
                    </p>
                    <p className="mt-1 text-center text-xs text-muted-foreground">
                        You do not need to take it again. It uploads by itself
                        when you have signal.
                    </p>
                    <Button
                        variant="outline"
                        className="mt-3 h-12 w-full"
                        disabled={busy}
                        data-testid="OdometerPhotoRetry"
                        onClick={() => reintentarEnEspera(enEspera)}
                    >
                        {busy ? 'Uploading…' : 'Try to upload now'}
                    </Button>
                </div>
            )}

            {!aprobada && (
                <>
                    <Button
                        size="lg"
                        // En espera la captura deja de ser la acción principal:
                        // la foto ya está hecha y lo que falta es subirla.
                        variant={tieneFoto || enEspera !== null ? 'outline' : 'default'}
                        className="h-14 w-full text-base"
                        disabled={busy}
                        onClick={() => archivo.current?.click()}
                    >
                        {tieneFoto || enEspera !== null ? 'Retake photo' : 'Take photo'}
                    </Button>
                    {entradaDeFoto}
                </>
            )}

            {(tieneFoto || aprobada) && (
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-reading">
                        {aprobada ? 'Reading (no photo)' : 'Reading on the photo'}
                    </Label>
                    <Input
                        id="odometer-reading"
                        data-testid="OdometerReadingInput"
                        className="h-14 text-center text-2xl"
                        // `decimal` levanta el teclado numérico del móvil sin
                        // impedir el punto de las décimas.
                        inputMode="decimal"
                        value={lectura}
                        onChange={(e) => {
                            // Lo que teclea la persona deja de ser del OCR, y
                            // por tanto sobrevive a que rehaga la foto.
                            lecturaEsSugerida.current = false;
                            setLectura(e.target.value);
                        }}
                        // `0` no: en un campo centrado y grande, el cero gris
                        // del placeholder se lee como una lectura detectada, y
                        // FR-04 prohíbe exactamente eso. Los guiones no se
                        // pueden confundir con un número.
                        placeholder="--"
                    />
                    {sugerencia !== null && (
                        <p className="text-xs text-muted-foreground">
                            {`Suggested from the photo: ${sugerencia} — check it against the vehicle before confirming.`}
                        </p>
                    )}
                </div>
            )}

            {error && (
                <p className="text-center text-sm text-destructive">{error}</p>
            )}

            {(tieneFoto || aprobada) && (
                <Button
                    size="lg"
                    className="h-14 w-full text-lg"
                    disabled={busy || !puedeConfirmar}
                    onClick={confirmar}
                >
                    Confirm reading
                </Button>
            )}

            {!aprobada && !tieneFoto && (
                <>
                    {aviso}
                    <Button
                        variant="ghost"
                        className="h-12 w-full"
                        disabled={busy}
                        onClick={() => setPidiendoExcepcion(true)}
                    >
                        I can&apos;t take a photo
                    </Button>
                </>
            )}

            {onCancel && (
                <Button variant="ghost" disabled={busy} onClick={onCancel}>
                    Not now
                </Button>
            )}
        </section>
    );
}
