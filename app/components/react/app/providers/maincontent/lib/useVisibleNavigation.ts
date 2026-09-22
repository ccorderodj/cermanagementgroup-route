import { useMemo } from 'react';
import { useUser } from '@/app/providers/StoreProvider';
import type { INavMainItem, INavMainSubItem } from '@/widgets/Sidebar';

export type VisibleNavItem = INavMainItem & { items: INavMainSubItem[] };

/**
 * Los destinos que este usuario puede abrir, agrupados, sin grupos vacíos.
 *
 * Es un hook y no una función dentro de `NavMainModern` porque ahora hay dos
 * menús —el lateral de negocio y el de usuario con la administración— y un
 * permiso tiene que aplicarse exactamente igual en los dos. Con dos copias del
 * filtro bastaría que una se desviara para que un enlace apareciera en un menú
 * y no en el otro.
 *
 * Esto es experiencia de usuario, no seguridad: la cookie `user_data` de la que
 * salen los permisos es editable desde el navegador. La puerta real está en el
 * backend, que exige el mismo permiso para servir la página.
 */
export function useVisibleNavigation(items: INavMainItem[]): VisibleNavItem[] {
    const { userLogged, hasUserPermission } = useUser();

    return useMemo(
        () => items
            .map((item) => ({
                ...item,
                items: (item.items ?? []).filter((subItem) => {
                    if (subItem.platformOnly) {
                        return Boolean(userLogged?.is_superuser);
                    }
                    if (!subItem.requiredPermission) {
                        return true;
                    }
                    return hasUserPermission(subItem.requiredPermission);
                }),
            }))
            // Un grupo que se ha quedado sin ítems es peor que no mostrarlo.
            .filter((item) => item.items.length > 0),
        [items, userLogged, hasUserPermission],
    );
}
