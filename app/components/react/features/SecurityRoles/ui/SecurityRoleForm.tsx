import {
    useCallback,
    useEffect,
    useMemo,
} from 'react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
    Button,
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    Input,
    ToastAction,
} from '@/shared/ui/shadcn/new-york';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { extractErrorMessage } from '@/shared/lib/utils/utils';
import { createRole, updateRole } from '@/entities/Roles';
import type { RoleEntity } from '@/entities/Roles';

interface SecurityRoleFormProps {
    getData: (data: RoleEntity) => void;
    onError: (message: string) => void;
    initialData?: RoleEntity | null;
    disabled?: boolean;
}

const SecurityRoleFormSchema = z.object({
    name: z.string({ required_error: 'Role name is required' }).trim().min(1, 'Role name is required'),
    description: z.string().optional(),
});

type SecurityRoleFormValues = z.infer<typeof SecurityRoleFormSchema>;

export default function SecurityRoleForm(props: SecurityRoleFormProps) {
    const {
        getData,
        onError,
        initialData,
        disabled = false,
    } = props;
    const dispatch = useAppDispatch();
    const isEdit = Boolean(initialData?.id);
    const { toast } = useToast();

    const defaultValues = useMemo<Partial<SecurityRoleFormValues>>(
        () => ({
            name: initialData?.name ?? '',
            description: initialData?.description ?? '',
        }),
        [initialData],
    );

    const form = useForm<SecurityRoleFormValues>({
        resolver: zodResolver(SecurityRoleFormSchema),
        defaultValues,
    });

    useEffect(() => {
        form.reset(defaultValues);
    }, [defaultValues, form]);

    const onSubmit = useCallback(async (values: SecurityRoleFormValues) => {
        if (disabled) {
            toast({
                variant: 'destructive',
                title: 'You do not have permission to perform this action',
                description: 'Submission failed',
                action: <ToastAction altText="Try again">Try again</ToastAction>,
            });
            return;
        }

        try {
            const saved = isEdit && initialData?.id
                ? await dispatch(updateRole({
                    roleId: initialData.id,
                    data: {
                        name: values.name.trim(),
                        description: values.description?.trim() || null,
                    },
                })).unwrap()
                : await dispatch(createRole({
                    name: values.name.trim(),
                    description: values.description?.trim() || null,
                })).unwrap();
            getData(saved);
            toast({
                title: isEdit ? 'Role Updated' : 'Role Created',
                description: isEdit
                    ? `Role "${saved.name}" was updated successfully.`
                    : `Role "${saved.name}" was created successfully.`,
            });
            if (!isEdit) {
                form.reset({ name: '', description: '' });
            }
        } catch (error: unknown) {
            const errorMessage = extractErrorMessage(error, 'Could not save role');
            onError(errorMessage);
            toast({
                variant: 'destructive',
                title: errorMessage,
                description: 'The request to /api/roles did not complete.',
                action: <ToastAction altText="Try again">Try again</ToastAction>,
            });
        }
    }, [disabled, dispatch, form, getData, initialData?.id, isEdit, onError, toast]);

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="md:col-span-2">
                        <FormField
                            control={form.control}
                            name="name"
                            render={({ field }) => (
                                <FormItem className="flex flex-col">
                                    <FormControl>
                                        <Input
                                            id="security-role-name"
                                            placeholder="Role name"
                                            {...field}
                                            value={field.value || ''}
                                            onChange={field.onChange}
                                            disabled={disabled}
                                        />
                                    </FormControl>
                                    <FormLabel>Role name</FormLabel>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>

                    <div className="md:col-span-2">
                        <FormField
                            control={form.control}
                            name="description"
                            render={({ field }) => (
                                <FormItem className="flex flex-col">
                                    <FormControl>
                                        <Input
                                            id="security-role-description"
                                            placeholder="Description (optional)"
                                            {...field}
                                            value={field.value || ''}
                                            onChange={field.onChange}
                                            disabled={disabled}
                                        />
                                    </FormControl>
                                    <FormLabel>Description (optional)</FormLabel>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>

                    <div className="md:col-span-2">
                        <Button
                            type="submit"
                            className="mt-4 w-full bg-primary text-white font-medium p-2 rounded-md hover:bg-primary"
                        >
                            {isEdit ? 'Update Role' : 'Create Role'}
                        </Button>
                    </div>
                </div>
            </form>
        </Form>
    );
}
