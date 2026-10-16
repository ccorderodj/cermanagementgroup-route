import {
    type ChangeEvent, useCallback, useEffect, useMemo, useState,
} from 'react';
import {
    Loader2, MapPin, PlusCircle, Search, Star, X,
} from 'lucide-react';
import {
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Checkbox,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    Input,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useApp, useUser } from '@/app/providers/StoreProvider';
import {
    fetchOperatingStates,
    fetchOperatingStatesCatalog,
    setMainOperatingState,
    updateOperatingStates,
    type OperatingState,
    type OperatingStateCatalogItem,
} from '@/entities/Regions';

/**
 * Estados donde opera la compañía.
 *
 * `region` es el catálogo de estados de EE.UU.; esta pantalla dice en cuáles
 * opera el tenant, con la sede principal marcada, y — para quien tenga
 * `regions.update` — permite agregar/quitar estados y cambiar cuál es la
 * sede principal. Antes esta edición vivía escondida en Company Profile;
 * ahora Locations es el único lugar donde se administra.
 */
export const OperatingStatesPanel = () => {
    const dispatch = useAppDispatch();
    const { appData } = useApp();
    const { hasUserPermission } = useUser();

    const [states, setStates] = useState<OperatingState[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const [isOpenPopup, setOpenPopup] = useState(false);
    const [catalog, setCatalog] = useState<OperatingStateCatalogItem[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [filter, setFilter] = useState('');
    const [mainStateBusyId, setMainStateBusyId] = useState<number | null>(null);

    const canRead = hasUserPermission('regions.read');
    const canUpdate = hasUserPermission('regions.update');

    const load = useCallback(async () => {
        setIsLoading(true);
        setError('');
        try {
            setStates(await dispatch(fetchOperatingStates()).unwrap());
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not load states');
        } finally {
            setIsLoading(false);
        }
    }, [dispatch]);

    useEffect(() => {
        if (canRead) load();
    }, [canRead, load]);

    const openEditDialog = useCallback(async () => {
        setOpenPopup(true);
        setIsLoadingCatalog(true);
        setError('');
        try {
            const items = await dispatch(fetchOperatingStatesCatalog()).unwrap();
            setCatalog(items);
            setSelectedIds(new Set(items.filter((i) => i.enabled).map((i) => i.id)));
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not load the state catalog');
        } finally {
            setIsLoadingCatalog(false);
        }
    }, [dispatch]);

    const closeDialog = useCallback(() => setOpenPopup(false), []);

    const toggle = useCallback((id: number) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }, []);

    const save = useCallback(async () => {
        setIsSaving(true);
        setError('');
        try {
            const updated = await dispatch(updateOperatingStates([...selectedIds])).unwrap();
            setStates(updated);
            setOpenPopup(false);
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not save operating states');
        } finally {
            setIsSaving(false);
        }
    }, [dispatch, selectedIds]);

    const setAsMain = useCallback(async (stateId: number) => {
        setMainStateBusyId(stateId);
        setError('');
        try {
            setStates(await dispatch(setMainOperatingState(stateId)).unwrap());
        } catch (e) {
            setError(typeof e === 'string' ? e : 'Could not update the main state');
        } finally {
            setMainStateBusyId(null);
        }
    }, [dispatch]);

    const filteredCatalog = useMemo(() => {
        const needle = filter.trim().toLowerCase();
        if (!needle) return catalog;
        return catalog.filter((item) => `${item.name} ${item.code}`.toLowerCase().includes(needle));
    }, [catalog, filter]);

    if (!canRead) {
        return (
            <p className="p-6 text-sm text-muted-foreground">
                You do not have permission to view locations.
            </p>
        );
    }

    const main = states.find((s) => s.is_main);

    return (
        <div className="flex flex-1 flex-col gap-5 p-6">
            <Dialog open={isOpenPopup} onOpenChange={setOpenPopup}>
                <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[520px]">
                    <DialogHeader>
                        <DialogTitle>Operating states</DialogTitle>
                        <DialogDescription>
                            Choose the states where {appData?.company_name || 'the company'} operates.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            className="h-9 pl-8"
                            placeholder="Search states..."
                            value={filter}
                            onChange={(e: ChangeEvent<HTMLInputElement>) => setFilter(e.target.value)}
                        />
                    </div>

                    {isLoadingCatalog ? (
                        <div className="flex items-center justify-center py-10">
                            <Loader2 className="size-5 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <div className="grid max-h-[320px] grid-cols-2 gap-x-4 gap-y-1 overflow-y-auto pr-1">
                            {filteredCatalog.map((item) => (
                                <label
                                    key={item.id}
                                    htmlFor={`state-${item.id}`}
                                    className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 hover:bg-accent"
                                >
                                    <Checkbox
                                        id={`state-${item.id}`}
                                        checked={selectedIds.has(item.id)}
                                        disabled={isSaving}
                                        onCheckedChange={() => toggle(item.id)}
                                    />
                                    <span className="text-sm">{item.name}</span>
                                </label>
                            ))}
                        </div>
                    )}

                    {error && <p className="text-sm text-destructive">{error}</p>}

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={closeDialog}>
                            <X className="mr-2 size-4" />
                            Cancel
                        </Button>
                        <Button type="button" onClick={save} disabled={isSaving || isLoadingCatalog}>
                            {isSaving ? 'Saving...' : 'Save'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <div className="flex items-start justify-between gap-3">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Operating States</h2>
                    <p className="text-muted-foreground">
                        Where {appData?.company_name || 'the company'} currently operates.
                    </p>
                </div>
                {canUpdate && (
                    <Button onClick={openEditDialog}>
                        Edit states
                        <PlusCircle className="ml-2 size-4" />
                    </Button>
                )}
            </div>

            {error && !isOpenPopup && <p className="text-sm text-destructive">{error}</p>}

            {isLoading && states.length === 0 ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                        {states.map((state) => (
                            <Card
                                key={state.id}
                                className={state.is_main ? 'border-primary/40 bg-secondary/40' : ''}
                            >
                                <CardHeader className="pb-3">
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="flex items-center gap-2.5">
                                            <span className="flex size-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
                                                {state.code}
                                            </span>
                                            <div>
                                                <CardTitle className="text-base">{state.name}</CardTitle>
                                                <CardDescription className="text-xs">
                                                    United States
                                                </CardDescription>
                                            </div>
                                        </div>
                                        {state.is_main && (
                                            <Badge className="shrink-0 gap-1">
                                                <Star className="size-3" />
                                                Main
                                            </Badge>
                                        )}
                                    </div>
                                </CardHeader>
                                <CardContent className="flex items-center justify-between gap-2 pt-0">
                                    <p className="text-sm text-muted-foreground">
                                        {state.is_main
                                            ? 'Headquarters and default scope for staff.'
                                            : 'Active operating jurisdiction.'}
                                    </p>
                                    {canUpdate && !state.is_main && (
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            className="shrink-0"
                                            disabled={mainStateBusyId === state.id}
                                            onClick={() => setAsMain(state.id)}
                                        >
                                            {mainStateBusyId === state.id ? 'Saving...' : 'Set as main'}
                                        </Button>
                                    )}
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    <div className="flex items-center gap-2 rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
                        <MapPin className="size-4 shrink-0" />
                        <span>
                            {states.length} operating {states.length === 1 ? 'state' : 'states'}
                            {main ? ` · main location in ${main.name}` : ''}.
                            Client sites and CER offices will be managed separately.
                        </span>
                    </div>
                </>
            )}
        </div>
    );
};

export default OperatingStatesPanel;
