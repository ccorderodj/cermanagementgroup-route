export {
    vehicleSchema,
    fuelGradeSchema,
    FUEL_GRADES,
    FUEL_GRADE_LABELS,
} from './model/types';
export type {
    Vehicle,
    FuelGrade,
    VehicleCreateInput,
    VehicleUpdateInput,
} from './model/types';
export {
    fetchVehicles,
    createVehicle,
    updateVehicle,
    setVehicleActive,
    deleteVehicle,
    fetchVehiclesForAdmin,
} from './model/services/vehiclesService';
