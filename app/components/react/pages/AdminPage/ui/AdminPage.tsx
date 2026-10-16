import { ArrowRight, LayoutGrid } from 'lucide-react';
import {
    Badge,
    Card,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/shared/ui/shadcn/new-york';
import { useApp } from '@/app/providers/StoreProvider';
import {
    administrationNavigation,
    businessNavigation,
} from '@/app/providers/maincontent/config/navigation';
import { useVisibleNavigation } from '@/app/providers/maincontent/lib/useVisibleNavigation';

/**
 * Inicio autenticado: el trabajo de negocio que este usuario puede abrir.
 *
 * Las tarjetas salen de `businessNavigation`, la misma lista que pinta el menú
 * lateral y con el mismo filtro de permisos. Una aplicación de dominio no toca
 * esta página: añade su grupo a la navegación y aparece aquí.
 *
 * La administración (compañía, acceso, plataforma) vive en el menú de usuario.
 */
const AdminPage = () => {
    const { appData } = useApp();
    const business = useVisibleNavigation(businessNavigation);
    const hasAdministration = useVisibleNavigation(administrationNavigation).length > 0;

    const modules = business.flatMap((group) => (
        group.items && group.items.length > 0
            ? group.items.map((item) => ({ title: item.title, group: group.title, url: item.url }))
            : [{ title: group.title, group: group.title, url: group.url }]
    ));

    return (
        <div className="flex flex-1 flex-col gap-6 p-6" data-testid="AdminPage">
            <Card className="border-none bg-gradient-to-r from-cer-blue via-cer-blue to-cer-cyan text-white shadow-lg">
                <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <Badge
                            variant="secondary"
                            className="bg-white/15 text-white hover:bg-white/20"
                        >
                            {appData?.app_title || 'CER Application'}
                        </Badge>
                    </div>
                    {/* El titulo de la pagina, y por eso un `h1` de verdad.
                        `CardTitle` es un `<div>` compartido por todas las
                        tarjetas: convertirlo en encabezado pondria un `h1`
                        dentro de cada tarjeta. */}
                    <h1 className="text-2xl font-semibold leading-none tracking-tight">
                        {appData?.company_name || appData?.brand_label || 'CER Management Group'}
                    </h1>
                    {appData?.brand_tagline && (
                        <CardDescription className="text-white/80">
                            {appData.brand_tagline}
                        </CardDescription>
                    )}
                </CardHeader>
            </Card>

            <section className="space-y-3">
                <div className="flex items-center gap-2">
                    <LayoutGrid className="h-5 w-5 text-primary" aria-hidden="true" />
                    <h2 className="text-lg font-semibold">Your work</h2>
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {modules.map((item) => (
                        <a key={`${item.group}-${item.title}`} href={item.url} className="block">
                            <Card className="h-full border-border transition-colors hover:border-primary/50 hover:bg-accent/40">
                                <CardHeader className="space-y-2">
                                    <div className="flex items-center gap-3">
                                        <CardTitle className="text-base">{item.title}</CardTitle>
                                        <ArrowRight className="ml-auto h-4 w-4 text-muted-foreground" aria-hidden="true" />
                                    </div>
                                    <CardDescription>{item.group}</CardDescription>
                                </CardHeader>
                            </Card>
                        </a>
                    ))}
                </div>
            </section>

            {modules.length === 0 && (
                <div
                    className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground"
                    data-testid="AdminPageNoModules"
                >
                    No business modules are available to you yet.
                </div>
            )}

            {hasAdministration && (
                <p className="text-sm text-muted-foreground">
                    Company, access control and platform settings are in your account menu, at the top right.
                </p>
            )}
        </div>
    );
};

export default AdminPage;
