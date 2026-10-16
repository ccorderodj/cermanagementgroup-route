import {
    type ChangeEvent, useCallback, useEffect, useMemo, useState,
} from 'react';
import { Loader2, Search, X } from 'lucide-react';
import {
    Badge,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Input,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useUser } from '@/app/providers/StoreProvider';
import { fetchFeatureMap, type FeatureMapItem } from '@/entities/Permissions';

/**
 * Mapa de capacidades del sistema.
 *
 * Esta pantalla es de **lectura**. Un permiso no es un dato que alguien
 * redacte: se deriva de lo que la aplicación sabe hacer, y se siembra con el
 * catálogo. Ofrecer aquí un CRUD invitaría a crear permisos que ningún
 * endpoint comprueba —quedarían inertes— o a borrar los que sí se usan.
 *
 * Para cambiar quién tiene cada capacidad se va a Roles & Permissions.
 */
export const SecurityPermissionsPanel = () => {
    const dispatch = useAppDispatch();
    const { hasUserPermission } = useUser();

    const canRead = hasUserPermission('permissions.read');

    const [items, setItems] = useState<FeatureMapItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [filter, setFilter] = useState('');

    const load = useCallback(async () => {
        setIsLoading(true);
        setError('');
        try {
            setItems(await dispatch(fetchFeatureMap()).unwrap());
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not load the feature map');
        } finally {
            setIsLoading(false);
        }
    }, [dispatch]);

    useEffect(() => {
        if (canRead) load();
    }, [canRead, load]);

    const byModule = useMemo(() => {
        const needle = filter.trim().toLowerCase();
        const matching = needle
            ? items.filter((i) => i.name.toLowerCase().includes(needle)
                || (i.description || '').toLowerCase().includes(needle))
            : items;

        const groups = new Map<string, FeatureMapItem[]>();
        matching.forEach((item) => {
            const list = groups.get(item.module) || [];
            list.push(item);
            groups.set(item.module, list);
        });
        return [...groups.entries()]
            .map(([module, actions]) => ({
                module,
                actions: actions.sort((a, b) => a.action.localeCompare(b.action)),
            }))
            .sort((a, b) => a.module.localeCompare(b.module));
    }, [items, filter]);

    if (!canRead) {
        return (
            <p className="p-6 text-sm text-muted-foreground">
                You do not have permission to view the feature map.
            </p>
        );
    }

    return (
        <div className="flex flex-1 flex-col gap-5 p-6">
            <div>
                <h2 className="text-2xl font-bold tracking-tight">System Features</h2>
                <p className="text-muted-foreground">
                    Everything the system can do, and which roles can do it.
                    To change who has access, go to Roles &amp; Permissions.
                </p>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="relative w-full sm:w-[360px]">
                <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    className="h-9 pl-8 pr-8"
                    placeholder="Search features..."
                    value={filter}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setFilter(e.target.value)}
                />
                {filter && (
                    <button
                        type="button"
                        onClick={() => setFilter('')}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2"
                        aria-label="Clear search"
                    >
                        <X className="size-4 text-muted-foreground" />
                    </button>
                )}
            </div>

            {isLoading && items.length === 0 ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
                    {byModule.map(({ module, actions }) => (
                        <Card key={module}>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base capitalize">{module}</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2.5">
                                {actions.map((item) => (
                                    <div
                                        key={item.id}
                                        className="border-b border-border/60 pb-2.5 last:border-0 last:pb-0"
                                    >
                                        <div className="text-sm font-medium capitalize">
                                            {item.action || item.name}
                                        </div>
                                        <div className="mb-1.5 text-xs text-muted-foreground">
                                            {item.name}
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                            {item.roles.length === 0 ? (
                                                <span className="text-xs text-muted-foreground">
                                                    No role
                                                </span>
                                            ) : item.roles.map((role) => (
                                                <Badge
                                                    key={role.name}
                                                    variant={role.category === 'management' ? 'default' : 'secondary'}
                                                    className="capitalize"
                                                >
                                                    {role.name}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            <p className="text-xs text-muted-foreground">
                {items.length} features across {byModule.length} modules.
            </p>
        </div>
    );
};

export default SecurityPermissionsPanel;
