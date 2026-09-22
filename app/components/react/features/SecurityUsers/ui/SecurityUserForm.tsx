import {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from 'react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Eye, EyeOff } from 'lucide-react';
import {
    Button,
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    Input,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    ToastAction,
} from '@/shared/ui/shadcn/new-york';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { createUserManagement, setUserAccess, updateUserManagement } from '@/entities/UserManagement';
import { fetchRoles, type RoleEntity } from '@/entities/Roles';
import type { UserManagementEntity } from '@/entities/UserManagement';

interface SecurityUserFormProps {
    getData: (data: UserManagementEntity) => void;
    initialData?: UserManagementEntity;
}

const SecurityUserFormSchema = z.object({
    username: z.string({ required_error: 'Username is required' }).trim().min(1, 'Username is required'),
    email: z.string({ required_error: 'Email is required' }).trim().min(1, 'Email is required'),
    first_name: z.string({ required_error: 'First name is required' }).trim().min(1, 'First name is required'),
    last_name: z.string({ required_error: 'Last name is required' }).trim().min(1, 'Last name is required'),
    password: z.string().optional(),
    confirm_password: z.string().optional(),
    gender: z.enum(['true', 'false'], { required_error: 'Gender is required' }),
    is_active: z.enum(['active', 'inactive'], { required_error: 'Status is required' }),
    // El rol vive en user_company, pero desde la UI es un campo del usuario:
    // crear a alguien sin decidir qué puede hacer no es un flujo válido.
    role_id: z.string({ required_error: 'Role is required' }).min(1, 'Role is required'),
}).refine((values) => {
    return /\S+@\S+\.\S+/.test(values.email.trim());
}, { message: 'Invalid email', path: ['email'] });

type SecurityUserFormValues = z.infer<typeof SecurityUserFormSchema>;

export default function SecurityUserForm(props: SecurityUserFormProps) {
    const {
        getData,
        initialData,
    } = props;
    const dispatch = useAppDispatch();
    const isEditMode = Boolean(initialData);
    const { toast } = useToast();
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [roles, setRoles] = useState<RoleEntity[]>([]);

    useEffect(() => {
        dispatch(fetchRoles()).unwrap().then(setRoles).catch(() => setRoles([]));
    }, [dispatch]);

    const defaultValues = useMemo<Partial<SecurityUserFormValues>>(
        () => {
            let defaultGender: 'true' | 'false' | undefined;
            let defaultIsActive: 'active' | 'inactive' | undefined;

            if (initialData) {
                defaultGender = initialData.gender ? 'true' : 'false';
                defaultIsActive = initialData.is_active ? 'active' : 'inactive';
            }

            return {
                username: initialData?.username ?? '',
                email: initialData?.email ?? '',
                first_name: initialData?.first_name ?? '',
                last_name: initialData?.last_name ?? '',
                password: '',
                confirm_password: '',
                gender: defaultGender,
                is_active: defaultIsActive,
                role_id: initialData?.role_id ? String(initialData.role_id) : '',
            };
        },
        [initialData],
    );

    const form = useForm<SecurityUserFormValues>({
        resolver: zodResolver(SecurityUserFormSchema),
        defaultValues,
    });

    useEffect(() => {
        form.reset(defaultValues);
    }, [defaultValues, form]);

    const onSubmit = useCallback(async (values: SecurityUserFormValues) => {
        const password = values.password?.trim() || '';
        const confirmPassword = values.confirm_password?.trim() || '';
        const isPasswordProvided = Boolean(password);

        if (!isEditMode && !isPasswordProvided) {
            form.setError('password', { type: 'manual', message: 'Password is required' });
            return;
        }

        if (isPasswordProvided && password.length < 6) {
            form.setError('password', { type: 'manual', message: 'Password must be at least 6 characters' });
            return;
        }

        if (isPasswordProvided && password !== confirmPassword) {
            form.setError('confirm_password', { type: 'manual', message: 'Passwords do not match' });
            return;
        }

        try {
            if (isEditMode && initialData) {
                const updated = await dispatch(updateUserManagement({
                    userId: initialData.id,
                    data: {
                        username: values.username.trim(),
                        email: values.email.trim(),
                        first_name: values.first_name.trim(),
                        last_name: values.last_name.trim(),
                        password: isPasswordProvided ? password : undefined,
                        gender: values.gender === 'true',
                        role_id: Number(values.role_id),
                    },
                })).unwrap();

                // Suspender o reactivar es una operación distinta de editar:
                // actúa sobre la pertenencia a esta compañía, no sobre la
                // identidad de plataforma (D7). Solo se llama si cambió.
                const wantsActive = values.is_active === 'active';
                const result = wantsActive === initialData.is_active
                    ? updated
                    : await dispatch(setUserAccess({
                        userId: initialData.id,
                        isActive: wantsActive,
                    })).unwrap();

                getData(result);
                toast({
                    title: 'User Updated Successfully',
                    description: 'User has been updated successfully.',
                });
            } else {
                const created = await dispatch(createUserManagement({
                    username: values.username.trim(),
                    email: values.email.trim(),
                    first_name: values.first_name.trim(),
                    last_name: values.last_name.trim(),
                    password,
                    gender: values.gender === 'true',
                    // Un usuario nuevo entra siempre con la pertenencia activa;
                    // suspenderlo es una acción posterior y explícita.
                    role_id: Number(values.role_id),
                })).unwrap();
                getData(created);
                toast({
                    title: 'User Added Successfully',
                    description: 'User has been saved successfully.',
                });
                form.reset({
                    username: '',
                    email: '',
                    first_name: '',
                    last_name: '',
                    password: '',
                    confirm_password: '',
                    gender: undefined,
                    is_active: undefined,
                    role_id: '',
                });
            }
        } catch (error) {
            const errorMessage = (error as Error).message || `Could not ${isEditMode ? 'update' : 'create'} user`;
            toast({
                variant: 'destructive',
                title: errorMessage,
                description: 'Submission failed',
                action: <ToastAction altText="Try again">Try again</ToastAction>,
            });
        }
    }, [dispatch, form, getData, initialData, isEditMode, toast]);

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormField
                        control={form.control}
                        name="username"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Input
                                        id="security-user-username"
                                        placeholder="Username"
                                        {...field}
                                        value={field.value || ''}
                                        onChange={field.onChange}
                                    />
                                </FormControl>
                                <FormLabel>Username</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="email"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Input
                                        id="security-user-email"
                                        type="email"
                                        placeholder="Email"
                                        {...field}
                                        value={field.value || ''}
                                        onChange={field.onChange}
                                    />
                                </FormControl>
                                <FormLabel>Email</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="first_name"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Input
                                        id="security-user-first-name"
                                        placeholder="First name"
                                        {...field}
                                        value={field.value || ''}
                                        onChange={field.onChange}
                                    />
                                </FormControl>
                                <FormLabel>First Name</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="last_name"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Input
                                        id="security-user-last-name"
                                        placeholder="Last name"
                                        {...field}
                                        value={field.value || ''}
                                        onChange={field.onChange}
                                    />
                                </FormControl>
                                <FormLabel>Last Name</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="password"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <div className="relative">
                                    <FormControl>
                                        <Input
                                            id="security-user-password"
                                            type={showPassword ? 'text' : 'password'}
                                            placeholder={isEditMode ? 'Leave empty to keep current password' : 'Password'}
                                            {...field}
                                            value={field.value || ''}
                                            onChange={field.onChange}
                                            className="pr-10"
                                        />
                                    </FormControl>
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((prev) => !prev)}
                                        className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-700"
                                    >
                                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                <FormLabel>{isEditMode ? 'Password (optional)' : 'Password'}</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="confirm_password"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <div className="relative">
                                    <FormControl>
                                        <Input
                                            id="security-user-confirm-password"
                                            type={showConfirmPassword ? 'text' : 'password'}
                                            placeholder={isEditMode ? 'Confirm new password' : 'Confirm password'}
                                            {...field}
                                            value={field.value || ''}
                                            onChange={field.onChange}
                                            className="pr-10"
                                        />
                                    </FormControl>
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPassword((prev) => !prev)}
                                        className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-700"
                                    >
                                        {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                <FormLabel>{isEditMode ? 'Confirm Password (optional)' : 'Confirm Password'}</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    {/*
                      Aqui habia un desplegable "Superuser".
                      `Users.is_superuser` es privilegio de PLATAFORMA, no un rol
                      del tenant: concede acceso total a todas las companias y
                      cortocircuita el RBAC entero. Que estuviera en este
                      formulario permitia que cualquiera con `users.create` se
                      fabricara uno (D6, AUD-SEC-012). El backend ya no lo acepta
                      en el cuerpo de la peticion; el formulario tampoco lo ofrece.
                    */}

                    <FormField
                        control={form.control}
                        name="gender"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Select
                                        value={field.value}
                                        onValueChange={field.onChange}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select gender" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="false">Female</SelectItem>
                                            <SelectItem value="true">Male</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </FormControl>
                                <FormLabel>Gender</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="is_active"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Select
                                        value={field.value}
                                        onValueChange={field.onChange}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select status" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="active">Active</SelectItem>
                                            <SelectItem value="inactive">Inactive</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </FormControl>
                                <FormLabel>Status</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="role_id"
                        render={({ field }) => (
                            <FormItem className="flex flex-col">
                                <FormControl>
                                    <Select value={field.value} onValueChange={field.onChange}>
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select role" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {roles.map((role) => (
                                                <SelectItem key={role.id} value={String(role.id)}>
                                                    <span className="capitalize">{role.name}</span>
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </FormControl>
                                <FormLabel>Role in this company</FormLabel>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <div className="md:col-span-2">
                        <Button
                            type="submit"
                            className="mt-4 w-full bg-primary text-white font-medium p-2 rounded-md hover:bg-primary"
                        >
                            {isEditMode ? 'Update User' : 'Create User'}
                        </Button>
                    </div>
                </div>
            </form>
        </Form>
    );
}
