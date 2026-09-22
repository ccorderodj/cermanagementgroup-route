import { useCallback, useState } from 'react';
import { useSelector } from 'react-redux';
import {
    ChevronDown, ChevronRight, LogOut, UserRound,
} from 'lucide-react';
import { useApp, useUser } from '@/app/providers/StoreProvider';
import { administrationNavigation } from '@/app/providers/maincontent/config/navigation';
import { useVisibleNavigation } from '@/app/providers/maincontent/lib/useVisibleNavigation';
import {
    Avatar,
    AvatarFallback,
    AvatarImage,
    Button,
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
    Separator,
    SidebarTrigger,
    ToastAction,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { extractErrorMessage } from '@/shared/lib/utils/utils';
import { logout } from '@/entities/users';
import { fetchPlatformReadiness, getPlatformReadiness } from '@/entities/PlatformSettings';

const SETTINGS_URL = '/admin/platform/settings';

export function AppTopbar() {
    const { appData } = useApp();
    const { userLogged } = useUser();
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const [isLoggingOut, setLoggingOut] = useState(false);

    // La administracion del sistema vive en este menu y no en el lateral
    // (D12-03). Usa el mismo filtro que el menu lateral, asi que un permiso se
    // aplica igual en los dos, y un grupo sin nada visible no se pinta.
    const adminGroups = useVisibleNavigation(administrationNavigation);
    const { pathname } = window.location;

    const firstName = userLogged?.first_name?.trim() || '';
    const lastName = userLogged?.last_name?.trim() || '';
    const fullName = [firstName, lastName].filter(Boolean).join(' ') || userLogged?.username || 'User';
    const avatarFallback = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase() || 'U';
    const avatarSrc = userLogged?.gender ? '/static/img/man-avatar.jpg' : '/static/img/woman-avatar.jpg';

    // `groups` trae los roles del usuario en la compañía activa; el
    // superusuario no necesita rol para tener acceso, así que se rotula aparte.
    const roleLabel = userLogged?.is_superuser
        ? 'Superadmin'
        : (userLogged?.groups?.[0] || 'No role');

    const environmentLabel = appData?.environment_label;

    // El punto de preparación junto a Settings. Se pide al abrir el menú y no
    // al cargar cada página: sólo lo ve la administración de plataforma, y no
    // tiene sentido una consulta más por navegación para quien no lo abre.
    const readiness = useSelector(getPlatformReadiness);
    const onMenuOpenChange = useCallback((open: boolean) => {
        if (open && userLogged?.is_superuser) dispatch(fetchPlatformReadiness());
    }, [dispatch, userLogged?.is_superuser]);
    const gatesAbiertos = readiness?.gates.filter((g) => g.blocks_production && g.status !== 'closed').length ?? 0;

    const logoutEvent = useCallback(async () => {
        setLoggingOut(true);
        try {
            const result = await dispatch(logout());
            if (logout.rejected.match(result)) {
                throw new Error(extractErrorMessage(result, ''));
            }
            window.location.href = '/login';
        } catch (error) {
            setLoggingOut(false);
            toast({
                variant: 'destructive',
                title: 'Could not sign out',
                description: `${error}`,
                action: <ToastAction altText="Try again">Try again</ToastAction>,
            });
        }
    }, [dispatch, toast]);

    return (
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-card/95 px-3 backdrop-blur-sm md:px-5">
            <div className="flex min-w-0 items-center gap-2">
                <SidebarTrigger className="size-8 rounded-lg border border-border text-muted-foreground hover:bg-accent" />
                <Separator orientation="vertical" className="mx-1 hidden h-5 md:block" />
                <span className="hidden truncate text-sm font-semibold tracking-tight md:block">
                    {appData?.company_name || 'Company'}
                </span>

                {/* MODE=DEV no es un entorno de pruebas: el cartel decia
                    "test" y hacia dudar de contra que base se trabajaba (OD-14). */}
                {environmentLabel && (
                    <span className="ml-1 rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-destructive">
                        {environmentLabel}
                    </span>
                )}
            </div>

            <DropdownMenu onOpenChange={onMenuOpenChange}>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="ghost"
                        className="h-12 gap-2.5 rounded-lg px-2 hover:bg-accent"
                    >
                        <Avatar className="h-9 w-9 rounded-full border border-border">
                            <AvatarImage src={avatarSrc} alt={userLogged?.username || 'user'} />
                            <AvatarFallback className="bg-primary text-xs font-semibold text-primary-foreground">
                                {avatarFallback}
                            </AvatarFallback>
                        </Avatar>
                        <div className="hidden text-left leading-tight sm:block">
                            <div className="max-w-[180px] truncate text-sm font-semibold">
                                {fullName}
                            </div>
                            <div className="text-xs capitalize text-muted-foreground">
                                {roleLabel}
                            </div>
                        </div>
                        <ChevronDown className="hidden size-4 text-muted-foreground sm:block" />
                    </Button>
                </DropdownMenuTrigger>

                {/* Altura maxima y scroll propio: con la administracion dentro,
                    el menu puede ser mas alto que una pantalla corta de movil, y
                    sin esto el cierre de sesion quedaria fuera de alcance. */}
                <DropdownMenuContent
                    align="end"
                    className="max-h-[min(36rem,calc(100svh-5rem))] w-64 overflow-y-auto"
                >
                    <DropdownMenuLabel className="font-normal">
                        <div className="text-sm font-semibold">{fullName}</div>
                        <div className="truncate text-xs text-muted-foreground">
                            {userLogged?.email}
                        </div>
                        <div className="mt-1.5 inline-flex rounded-md bg-secondary px-2 py-0.5 text-[11px] font-semibold capitalize text-secondary-foreground">
                            {roleLabel}
                        </div>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {/* Enlaces reales y no botones con window.location: asi el
                        menu admite clic central y abrir en pestana nueva, igual
                        que el lateral (AUD-FE-021). La contrasena se cambia dentro
                        de My Profile, asi que no hace falta una entrada aparte. */}
                    <DropdownMenuItem asChild>
                        <a href="/admin/profile">
                            <UserRound className="mr-2 size-4" />
                            My Profile
                        </a>
                    </DropdownMenuItem>

                    {/* Grupos plegables, no submenus: en una pantalla tactil los
                        submenus se abren mal. Mismo patron que el menu lateral
                        (`NavMainModern`) — un grupo con la pagina activa dentro
                        empieza abierto, y el resto empieza plegado, para que
                        "Organization", "Access control" y "Platform" no
                        obliguen a desplazar el menu entero para llegar a
                        "Log out". */}
                    {adminGroups.map((group) => {
                        const hasActiveChild = group.items.some((item) => pathname === item.url);
                        return (
                            <Collapsible
                                key={group.title}
                                defaultOpen={hasActiveChild}
                                className="group/admin-collapsible"
                            >
                                <DropdownMenuSeparator />
                                <CollapsibleTrigger asChild>
                                    <button
                                        type="button"
                                        className="flex w-full items-center gap-2 rounded-sm px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground outline-none hover:text-foreground focus-visible:text-foreground"
                                    >
                                        {group.icon && <group.icon className="size-3.5" aria-hidden="true" />}
                                        <span className="flex-1 text-left">{group.title}</span>
                                        <ChevronRight className="size-3.5 shrink-0 transition-transform duration-200 group-data-[state=open]/admin-collapsible:rotate-90" />
                                    </button>
                                </CollapsibleTrigger>
                                <CollapsibleContent>
                                    <DropdownMenuGroup aria-label={group.title}>
                                        {group.items.map((item) => {
                                            const isCurrent = pathname === item.url;
                                            return (
                                                <DropdownMenuItem key={item.url} asChild>
                                                    <a
                                                        href={item.url}
                                                        aria-current={isCurrent ? 'page' : undefined}
                                                        className={isCurrent ? 'font-semibold' : undefined}
                                                    >
                                                        {item.title}
                                                        {item.url === SETTINGS_URL && readiness && (
                                                            <span
                                                                data-testid="menu-readiness"
                                                                className={`ml-auto flex items-center gap-1.5 text-[11px] font-medium ${readiness.production_ready ? 'text-green-600' : 'text-destructive'}`}
                                                            >
                                                                <span
                                                                    aria-hidden="true"
                                                                    className={`size-1.5 rounded-full ${readiness.production_ready ? 'bg-green-600' : 'bg-destructive'}`}
                                                                />
                                                                {readiness.production_ready ? 'Ready' : `${gatesAbiertos} open`}
                                                            </span>
                                                        )}
                                                    </a>
                                                </DropdownMenuItem>
                                            );
                                        })}
                                    </DropdownMenuGroup>
                                </CollapsibleContent>
                            </Collapsible>
                        );
                    })}

                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                        onClick={logoutEvent}
                        disabled={isLoggingOut}
                        className="text-destructive focus:text-destructive"
                    >
                        <LogOut className="mr-2 size-4" />
                        {isLoggingOut ? 'Signing out...' : 'Log out'}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </header>
    );
}
