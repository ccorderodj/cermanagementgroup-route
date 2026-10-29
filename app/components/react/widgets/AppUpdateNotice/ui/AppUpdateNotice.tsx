import {
    Component, ErrorInfo, ReactNode, useEffect, useState, useSyncExternalStore,
} from 'react';
import {
    avisarActualizacion,
    esChunkPerdido,
    hayActualizacion,
    suscribirActualizacion,
    vigilarActualizaciones,
} from '@/shared/lib/appUpdate';
import { Button } from '@/shared/ui/shadcn/new-york';

/**
 * Aviso de versión nueva. **No recarga solo**: recargar en mitad de un
 * formulario perdería lo escrito. Lo pendiente de enviar vive en IndexedDB y
 * sobrevive a la recarga; la sesión, en su cookie.
 */
export function AppUpdateNotice() {
    const hay = useSyncExternalStore(suscribirActualizacion, hayActualizacion);
    const [aparcado, setAparcado] = useState(false);

    useEffect(() => vigilarActualizaciones(), []);

    if (!hay || aparcado) return null;

    return (
        <div
            role="status"
            className="fixed top-0 z-[100] w-full p-4 sm:bottom-0 sm:right-0 sm:top-auto md:max-w-[420px]"
        >
            <div className="flex items-center gap-3 rounded-md border bg-background p-4 shadow-lg">
                <p className="flex-1 text-sm">
                    A new version is available. Reload when you finish what you are doing.
                </p>
                <Button size="sm" variant="ghost" onClick={() => setAparcado(true)}>
                    Later
                </Button>
                <Button size="sm" onClick={() => window.location.reload()}>
                    Reload
                </Button>
            </div>
        </div>
    );
}

interface ChunkErrorBoundaryProps {
    children: ReactNode;
}

interface ChunkErrorBoundaryState {
    perdido: boolean;
}

/**
 * Una pestaña abierta antes de un despliegue pide un chunk que ya no existe.
 * En vez de dejar la pantalla en blanco, se avisa de la versión nueva. Los
 * demás errores siguen su camino, como hasta ahora.
 */
export class ChunkErrorBoundary extends Component<ChunkErrorBoundaryProps, ChunkErrorBoundaryState> {
    constructor(props: ChunkErrorBoundaryProps) {
        super(props);
        this.state = { perdido: false };
    }

    static getDerivedStateFromError(error: unknown): ChunkErrorBoundaryState {
        if (esChunkPerdido(error)) return { perdido: true };
        throw error;
    }

    componentDidCatch(error: unknown, _info: ErrorInfo): void {
        if (esChunkPerdido(error)) avisarActualizacion();
    }

    render() {
        const { perdido } = this.state;
        const { children } = this.props;
        return perdido ? null : children;
    }
}
