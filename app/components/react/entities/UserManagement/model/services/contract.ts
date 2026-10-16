/**
 * A qué contrato de administración de usuarios se habla.
 *
 * El mismo router vive en dos rutas y la diferencia no es cosmética: por
 * `/route/users` el servidor sólo acepta los dos roles de producto de CER Route
 * —para cualquiera, Superadmin incluido— y por `/users` sigue el contrato del
 * núcleo, intacto.
 *
 * Por eso la pantalla tiene que decir **desde qué producto** administra. No es
 * una preferencia de presentación: llamar al contrato equivocado devuelve el
 * catálogo entero del tenant, que es justo lo que CER encontró al revisar
 * `CER Route > Users` con un Superadmin.
 *
 * Quien no lo diga habla con el núcleo, que es el comportamiento que ya existía.
 */

export type UserManagementContract = 'core' | 'cer-route';

export const contractBasePath = (contrato?: UserManagementContract): string => (
    contrato === 'cer-route' ? '/route/users' : '/users'
);
