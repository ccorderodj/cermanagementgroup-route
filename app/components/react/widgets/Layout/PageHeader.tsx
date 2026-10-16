import { Fragment } from 'react';
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from '@/shared/ui/shadcn/new-york';

export type PageHeaderCrumb = {
    label: string;
    href?: string;
};

type PageHeaderProps = {
    title: string;
    description?: string;
    breadcrumbs: PageHeaderCrumb[];
};

// Encabezado consistente para las páginas del panel privado: breadcrumb
// hasta Home (/admin) + título + descripción. Ver widgets/Layout/AppTopbar
// para la barra superior y AppSidebar para las mismas rutas/etiquetas.
export function PageHeader({ title, description, breadcrumbs }: PageHeaderProps) {
    return (
        <div className="border-b border-border bg-card px-6 py-5">
            <Breadcrumb>
                <BreadcrumbList>
                    <BreadcrumbItem>
                        <BreadcrumbLink href="/admin">Home</BreadcrumbLink>
                    </BreadcrumbItem>
                    {breadcrumbs.map((crumb, index) => {
                        const isLast = index === breadcrumbs.length - 1;

                        return (
                            <Fragment key={crumb.label}>
                                <BreadcrumbSeparator />
                                <BreadcrumbItem>
                                    {isLast || !crumb.href ? (
                                        <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                                    ) : (
                                        <BreadcrumbLink href={crumb.href}>{crumb.label}</BreadcrumbLink>
                                    )}
                                </BreadcrumbItem>
                            </Fragment>
                        );
                    })}
                </BreadcrumbList>
            </Breadcrumb>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
                {title}
            </h1>
            {description && (
                <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            )}
        </div>
    );
}
