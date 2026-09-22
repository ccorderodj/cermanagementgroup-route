export { supervisorProfileSchema, vehicleAssignmentSchema } from './model/types';
export type { SupervisorProfile, VehicleAssignment } from './model/types';
export {
    fetchSupervisors,
    fetchMySupervisorProfile,
    createSupervisorProfile,
    fetchAssignmentHistory,
    assignVehicle,
    endAssignment,
} from './model/services/supervisorsService';
