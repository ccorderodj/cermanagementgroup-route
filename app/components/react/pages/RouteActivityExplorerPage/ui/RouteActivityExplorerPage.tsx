import { ActivityExplorerPanel } from '@/widgets/RouteActivityExplorer';

/**
 * Activity Explorer de administración (`/admin/route/activity`).
 *
 * La lógica —pestañas, bajada de nivel, lectura vigente, H-1— vive en
 * `ActivityExplorerPanel`, compartida con la actividad propia del supervisor
 * (`/route/activity`). Aquí sólo la cabecera de administración.
 */
export function RouteActivityExplorerPage() {
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

    return (
        <div className="flex flex-col p-4 md:p-6">
            <ActivityExplorerPanel scope="admin" header={encabezado} />
        </div>
    );
}

export default RouteActivityExplorerPage;
