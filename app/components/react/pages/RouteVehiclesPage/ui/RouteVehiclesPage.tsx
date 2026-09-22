import { useState } from 'react';
import { PageHeader } from '@/widgets/Layout';
import { SupervisorAssignmentsPanel, VehiclesPanel } from '@/features/RouteVehicles';

/**
 * Vehículos y asignaciones, en una sola pantalla con dos pestañas.
 *
 * Van juntas porque son la misma tarea vista desde dos lados: qué vehículos
 * tiene la compañía y quién conduce cada uno. Separarlas en dos pantallas
 * obligaría a ir y volver para comprobar lo segundo después de cambiar lo
 * primero.
 */
const RouteVehiclesPage = () => {
    const [tab, setTab] = useState<'vehicles' | 'assignments'>('vehicles');

    return (
        <div className="flex flex-1 flex-col" data-testid="RouteVehiclesPage">
            <PageHeader
                title="Vehicles"
                description="Vehicles of this company and which supervisor drives each one."
                breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Vehicles' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <div className="flex gap-1 rounded-lg bg-muted p-1 sm:w-fit">
                    <button
                        type="button"
                        onClick={() => setTab('vehicles')}
                        className={[
                            'flex-1 rounded-md px-4 py-2 text-sm font-medium sm:flex-none',
                            tab === 'vehicles' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground',
                        ].join(' ')}
                    >
                        Vehicles
                    </button>
                    <button
                        type="button"
                        onClick={() => setTab('assignments')}
                        className={[
                            'flex-1 rounded-md px-4 py-2 text-sm font-medium sm:flex-none',
                            tab === 'assignments' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground',
                        ].join(' ')}
                    >
                        Assignments
                    </button>
                </div>

                {tab === 'vehicles' ? <VehiclesPanel /> : <SupervisorAssignmentsPanel />}
            </div>
        </div>
    );
};

export default RouteVehiclesPage;
