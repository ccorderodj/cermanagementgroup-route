export {
    supervisorProfileSchema,
    vehicleAssignmentSchema,
    supervisorCandidateSchema,
} from './model/types';
export type {
    SupervisorProfile,
    VehicleAssignment,
    SupervisorCandidate,
} from './model/types';
export {
    fetchSupervisors,
    fetchMySupervisorProfile,
    createSupervisorProfile,
    fetchAssignmentHistory,
    assignVehicle,
    endAssignment,
    fetchSupervisorCandidates,
    designateSupervisor,
    setSupervisorDesignation,
    setSupervisorTimeZone,
    setSupervisorOperationalState,
    fetchStateCatalog,
    deleteSupervisorProfile,
} from './model/services/supervisorsService';
