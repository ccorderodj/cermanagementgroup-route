import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ArrowDownCircle, ArrowUpCircle, Clock, Loader2, ShieldCheck,
} from 'lucide-react';
import {
    Badge,
    Button,
    Checkbox,
    Separator,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useUser } from '@/app/providers/StoreProvider';
import {
    fetchRolePermissions,
    putRolePermissions,
    type RoleEntity,
    type RolePermissionCatalogItem,
    type RolePermissionPendingRequest,
} from '@/entities/Roles';

interface RolePermissionsPanelProps {
    role: RoleEntity | null;
    onSaved?: (permissionCount: number) => void;
}

/**
 * Permisos de un rol, agrupados por módulo.
 *
 * El backend devuelve el catálogo completo con los concedidos ya marcados
 * (`/roles/{id}/permissions`), así que aquí no hay que cruzar dos listados.
 *
 * OJO con el flujo: enviar NO aplica el cambio. Por segregación de deberes, el
 * backend crea una solicitud que debe aprobar **otro** administrador desde
 * Permission Requests; hasta entonces los permisos quedan inactivos. La
 * interfaz lo dice explícitamente para no prometer algo que no ocurre.
 */
export function RolePermissionsPanel({ role, onSaved }: RolePermissionsPanelProps) {
    const dispatch = useAppDispatch();
    const { hasUserPermission } = useUser();

    const [catalog, setCatalog] = useState<RolePermissionCatalogItem[]>([]);
    const [pending, setPending] = useState<RolePermissionPendingRequest | null>(null);
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const canEdit = hasUserPermission('rolepermissions.update');

    const load = useCallback(async (roleId: number) => {
        setIsLoading(true);
        setError(null);
        try {
            const view = await dispatch(fetchRolePermissions(roleId)).unwrap();
            setCatalog(view.permissions);
            setPending(view.pending_request ?? null);
            setSelected(new Set(view.permissions.filter((i) => i.granted).map((i) => i.id)));
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not load permissions');
        } finally {
            setIsLoading(false);
        }
    }, [dispatch]);

    useEffect(() => {
        if (role?.id) {
            load(role.id);
        } else {
            setCatalog([]);
            setPending(null);
            setSelected(new Set());
        }
    }, [role?.id, load]);

    const byModule = useMemo(() => {
        const groups = new Map<string, RolePermissionCatalogItem[]>();
        catalog.forEach((item) => {
            const list = groups.get(item.module) || [];
            list.push(item);
            groups.set(item.module, list);
        });
        return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
    }, [catalog]);

    /**
     * Lo que está a punto de enviarse, separado en las dos actividades:
     * conceder y revocar. Se muestran aparte porque no son lo mismo — revocar
     * quita acceso a gente que hoy lo tiene.
     */
    const draft = useMemo(() => {
        const granted = new Set(catalog.filter((i) => i.granted).map((i) => i.id));
        const nameOf = (id: number) => catalog.find((i) => i.id === id)?.name ?? String(id);

        const toGrant = [...selected].filter((id) => !granted.has(id)).map(nameOf).sort();
        const toRevoke = [...granted].filter((id) => !selected.has(id)).map(nameOf).sort();

        return { toGrant, toRevoke };
    }, [catalog, selected]);

    const isDirty = draft.toGrant.length > 0 || draft.toRevoke.length > 0;

    const toggle = (id: number) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleModule = (items: RolePermissionCatalogItem[], allOn: boolean) => {
        setSelected((prev) => {
            const next = new Set(prev);
            items.forEach((i) => (allOn ? next.delete(i.id) : next.add(i.id)));
            return next;
        });
    };

    const save = async () => {
        if (!role) return;
        setIsSaving(true);
        setError(null);
        try {
            const view = await dispatch(putRolePermissions({
                roleId: role.id,
                permissionIds: [...selected],
            })).unwrap();
            setCatalog(view.permissions);
            setPending(view.pending_request ?? null);
            setSelected(new Set(view.permissions.filter((i) => i.granted).map((i) => i.id)));
            onSaved?.(view.permissions.filter((i) => i.granted).length);
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not submit the change');
        } finally {
            setIsSaving(false);
        }
    };

    if (!role) {
        return (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 text-center">
                <ShieldCheck className="size-8 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">
                    Select a role to review its permissions
                </p>
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col">
            <div className="flex items-start justify-between gap-3 pb-3">
                <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold capitalize">{role.name}</h3>
                    <p className="truncate text-sm text-muted-foreground">
                        {role.description || 'No description'}
                    </p>
                </div>
                <Badge variant="secondary" className="shrink-0">
                    {selected.size} of {catalog.length}
                </Badge>
            </div>

            <Separator />

            {error && (
                <p className="pt-3 text-sm text-destructive">{error}</p>
            )}

            {pending && (
                <div className="mt-3 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm">
                    <div className="flex items-start gap-2">
                        <Clock className="mt-0.5 size-4 shrink-0 text-warning" />
                        <span>
                            This role has a change <strong>waiting for approval</strong>.
                            A management role must review it in Permission Requests
                            before it takes effect.
                        </span>
                    </div>
                    {(pending.to_grant.length > 0 || pending.to_revoke.length > 0) && (
                        <div className="mt-2 space-y-1 pl-6">
                            {pending.to_grant.length > 0 && (
                                <div className="flex items-start gap-1.5 text-xs">
                                    <ArrowUpCircle className="mt-0.5 size-3.5 shrink-0 text-success" />
                                    <span>
                                        <span className="font-semibold text-success">Grant</span>
                                        {' '}
                                        {pending.to_grant.join(', ')}
                                    </span>
                                </div>
                            )}
                            {pending.to_revoke.length > 0 && (
                                <div className="flex items-start gap-1.5 text-xs">
                                    <ArrowDownCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                                    <span>
                                        <span className="font-semibold text-destructive">Revoke</span>
                                        {' '}
                                        {pending.to_revoke.join(', ')}
                                    </span>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-1 items-center justify-center py-10">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <div className="flex-1 space-y-5 overflow-y-auto py-4 pr-1">
                    {byModule.map(([module, items]) => {
                        const allOn = items.every((i) => selected.has(i.id));
                        return (
                            <section key={module}>
                                <div className="mb-2 flex items-center justify-between">
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                                        {module}
                                    </h4>
                                    {canEdit && (
                                        <button
                                            type="button"
                                            className="text-xs font-medium text-primary hover:underline"
                                            onClick={() => toggleModule(items, allOn)}
                                        >
                                            {allOn ? 'Clear all' : 'Select all'}
                                        </button>
                                    )}
                                </div>
                                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                                    {items.map((item) => (
                                        <label
                                            key={item.id}
                                            htmlFor={`perm-${item.id}`}
                                            className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 hover:bg-accent"
                                        >
                                            <Checkbox
                                                id={`perm-${item.id}`}
                                                checked={selected.has(item.id)}
                                                disabled={!canEdit || isSaving}
                                                onCheckedChange={() => toggle(item.id)}
                                            />
                                            <span className="text-sm capitalize">{item.action || item.name}</span>
                                        </label>
                                    ))}
                                </div>
                            </section>
                        );
                    })}
                </div>
            )}

            {canEdit && (
                <>
                    <Separator />
                    {isDirty && (
                        <div className="space-y-1.5 pt-3">
                            {draft.toGrant.length > 0 && (
                                <div className="flex items-start gap-1.5 text-xs">
                                    <ArrowUpCircle className="mt-0.5 size-3.5 shrink-0 text-success" />
                                    <span>
                                        <span className="font-semibold text-success">
                                            Granting {draft.toGrant.length}
                                        </span>
                                        {' — '}
                                        {draft.toGrant.join(', ')}
                                    </span>
                                </div>
                            )}
                            {draft.toRevoke.length > 0 && (
                                <div className="flex items-start gap-1.5 text-xs">
                                    <ArrowDownCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                                    <span>
                                        <span className="font-semibold text-destructive">
                                            Revoking {draft.toRevoke.length}
                                        </span>
                                        {' — '}
                                        {draft.toRevoke.join(', ')}
                                    </span>
                                </div>
                            )}
                        </div>
                    )}

                    <div className="flex items-center justify-end gap-2 pt-3">
                        <span className="mr-auto text-xs text-muted-foreground">
                            {isDirty ? 'Submitted for approval, not applied directly.' : ''}
                        </span>
                        <Button
                            type="button"
                            variant="outline"
                            disabled={!isDirty || isSaving}
                            onClick={() => setSelected(new Set(catalog.filter((i) => i.granted).map((i) => i.id)))}
                        >
                            Discard
                        </Button>
                        <Button
                            type="button"
                            disabled={!isDirty || isSaving || Boolean(pending)}
                            onClick={save}
                        >
                            {isSaving && <Loader2 className="mr-2 size-4 animate-spin" />}
                            Submit for approval
                        </Button>
                    </div>
                </>
            )}
        </div>
    );
}
