import { useCallback, useEffect, useMemo, useState } from 'react';
import { PlusCircledIcon } from '@radix-ui/react-icons';
import { Loader2, X } from 'lucide-react';
import { useUser } from '@/app/providers/StoreProvider';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    Badge,
    Button,
    Card,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/shared/ui/shadcn/new-york';
import { fetchRoles, type RoleEntity } from '@/entities/Roles';
import SecurityRoleForm from './SecurityRoleForm';
import { RolePermissionsPanel } from './RolePermissionsPanel';

/**
 * Roles y sus permisos en una sola pantalla.
 *
 * `role_permission` es una tabla puente: quien administra piensa en "qué puede
 * hacer este rol", no en "qué vínculos rol-permiso existen". Por eso la lista y
 * el detalle conviven aquí, y el backend entrega el rol ya con su conteo de
 * permisos y su catálogo.
 *
 * La lista se pide completa (`GET /roles`) en vez de paginada: los roles de una
 * cuenta son unas pocas filas, y paginar un maestro-detalle solo estorba.
 */
const ROLE_ITEM_CLASSES = 'flex w-full items-center justify-between gap-2 rounded-md px-3 py-2.5 text-left transition-colors';

export const SecurityRolesPanel = () => {
    const dispatch = useAppDispatch();
    const { hasUserPermission } = useUser();

    const canRead = hasUserPermission('roles.read');
    const canCreate = hasUserPermission('roles.create');

    const [roles, setRoles] = useState<RoleEntity[]>([]);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [isOpenPopup, setOpenPopup] = useState(false);

    const load = useCallback(async () => {
        setIsLoading(true);
        setError('');
        try {
            const data = await dispatch(fetchRoles()).unwrap();
            setRoles(data);
            setSelectedId((current) => current ?? data[0]?.id ?? null);
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not load roles');
        } finally {
            setIsLoading(false);
        }
    }, [dispatch]);

    useEffect(() => {
        if (canRead) load();
    }, [canRead, load]);

    const selectedRole = useMemo(
        () => roles.find((r) => r.id === selectedId) ?? null,
        [roles, selectedId],
    );

    /**
     * Los roles se agrupan por categoría porque no son intercambiables: los de
     * dirección/gestión son los únicos que pueden aprobar cambios de permisos.
     */
    const grouped = useMemo(() => ([
        { key: 'management', label: 'Direction & Management', items: roles.filter((r) => r.category === 'management') },
        { key: 'operative', label: 'Operative', items: roles.filter((r) => r.category !== 'management') },
    ].filter((g) => g.items.length > 0)), [roles]);

    const handleCreated = (created: RoleEntity) => {
        setOpenPopup(false);
        load().then(() => setSelectedId(created.id));
    };

    // Refleja el nuevo conteo sin volver a pedir toda la lista.
    const handlePermissionsSaved = (permissionCount: number) => {
        setRoles((prev) => prev.map((r) => (
            r.id === selectedId ? { ...r, permission_count: permissionCount } : r
        )));
    };

    if (!canRead) {
        return (
            <p className="p-6 text-sm text-muted-foreground">
                You do not have permission to view roles.
            </p>
        );
    }

    return (
        <div className="flex flex-1 flex-col gap-5 p-6">
            <Dialog open={isOpenPopup} onOpenChange={setOpenPopup}>
                <DialogContent className="sm:max-w-[520px]">
                    <DialogHeader>
                        <DialogTitle>New role</DialogTitle>
                        <DialogDescription>
                            Create the role first, then assign its permissions.
                        </DialogDescription>
                    </DialogHeader>
                    <SecurityRoleForm getData={handleCreated} onError={setError} disabled={!canCreate} />
                    <Button type="button" variant="outline" onClick={() => setOpenPopup(false)}>
                        <X className="mr-2 size-4" />
                        Close
                    </Button>
                </DialogContent>
            </Dialog>

            <div className="flex items-start justify-between gap-3">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Roles &amp; Permissions</h2>
                    <p className="text-muted-foreground">
                        Define what each role can do across the system.
                    </p>
                </div>
                {canCreate && (
                    <Button onClick={() => setOpenPopup(true)}>
                        New role
                        <PlusCircledIcon className="ml-2 size-4" />
                    </Button>
                )}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="grid flex-1 grid-cols-1 gap-5 lg:grid-cols-[minmax(240px,300px)_1fr]">
                <Card className="flex flex-col overflow-hidden p-2">
                    {isLoading && roles.length === 0 ? (
                        <div className="flex items-center justify-center py-10">
                            <Loader2 className="size-5 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {grouped.map((group) => (
                                <div key={group.key}>
                                    <p className="px-3 pb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                                        {group.label}
                                    </p>
                                    <ul className="space-y-1">
                                        {group.items.map((role) => {
                                            const isSelected = role.id === selectedId;
                                            return (
                                                <li key={role.id}>
                                                    <button
                                                        type="button"
                                                        onClick={() => setSelectedId(role.id)}
                                                        className={`${ROLE_ITEM_CLASSES} ${
                                                            isSelected
                                                                ? 'bg-primary text-primary-foreground'
                                                                : 'hover:bg-accent'
                                                        }`}
                                                    >
                                                        <span className="min-w-0">
                                                            <span className="block truncate text-sm font-semibold capitalize">
                                                                {role.name}
                                                            </span>
                                                            <span className={`block truncate text-xs ${
                                                                isSelected ? 'text-primary-foreground/70' : 'text-muted-foreground'
                                                            }`}
                                                            >
                                                                {role.description || 'No description'}
                                                            </span>
                                                        </span>
                                                        <Badge
                                                            variant={isSelected ? 'secondary' : 'outline'}
                                                            className="shrink-0"
                                                        >
                                                            {role.permission_count ?? 0}
                                                        </Badge>
                                                    </button>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    )}
                </Card>

                <Card className="p-5">
                    <RolePermissionsPanel role={selectedRole} onSaved={handlePermissionsSaved} />
                </Card>
            </div>
        </div>
    );
};

export default SecurityRolesPanel;
