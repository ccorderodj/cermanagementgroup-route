import { PageHeader } from '@/widgets/Layout';
import { SecurityUsersPanel } from '@/features/SecurityUsers';

/**
 * Administración de usuarios desde la configuración de CER Route.
 *
 * **Reutiliza el panel del núcleo tal cual.** La identidad es del núcleo
 * (`user` + `user_company`), su contrato de autorización ya existe
 * (`users.read` / `users.create` / `users.update`) y su formulario ya impide
 * conceder privilegio de plataforma. Escribir aquí una segunda pantalla de
 * usuarios habría creado un segundo sitio donde arreglar el mismo fallo.
 *
 * Lo propio de Route —la designación de supervisor— no está aquí: es un
 * concepto distinto de la identidad y vive en Supervisors.
 *
 * Lo único que esta página añade al panel compartido es **desde qué producto**
 * administra. Con eso el panel habla al contrato de CER Route, que ofrece los
 * dos roles de producto y rechaza cualquier otro — venga de quien venga.
 */
const RouteUsersPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteUsersPage">
        <PageHeader
            title="Users"
            description="People who can sign in to this company."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Users' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            {/* El contrato de CER Route: sólo ofrece y sólo acepta los dos
                roles de producto, para cualquiera que entre por aquí. */}
            <SecurityUsersPanel contract="cer-route" />
        </div>
    </div>
);

export default RouteUsersPage;
