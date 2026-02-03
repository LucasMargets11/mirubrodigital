'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { branchService } from '@/services/branches';

export default function BranchesPage() {
    const queryClient = useQueryClient();
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    
    const { data: branches, isLoading, error } = useQuery({
        queryKey: ['branches'],
        queryFn: branchService.list,
        retry: false,
    });

    const isAuthorized = !error; 

    const {
        register,
        handleSubmit,
        reset,
        formState: { errors },
    } = useForm<{ name: string }>();

    const createMutation = useMutation({
        mutationFn: branchService.create,
        onSuccess: () => {
            toast.success('Sucursal creada exitosamente');
            queryClient.invalidateQueries({ queryKey: ['branches'] });
            setIsDialogOpen(false);
            reset();
        },
        onError: (err: any) => {
            const msg = err.response?.data?.detail || 'Error al crear sucursal';
            toast.error(msg);
        },
    });

    const onSubmit = (data: { name: string }) => {
        createMutation.mutate(data);
    };

    if (isLoading) return <div>Cargando sucursales...</div>;

    if (!isAuthorized) {
        return (
            <div className="flex h-full flex-col items-center justify-center space-y-4">
                <h1 className="text-xl font-bold">Sin Acceso</h1>
                <p className="text-gray-500">Solo la Casa Matriz puede gestionar sucursales.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Sucursales</h1>
                    <p className="text-muted-foreground">
                        Gestioná las sucursales de tu negocio.
                    </p>
                </div>
                <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <Plus className="mr-2 h-4 w-4" />
                            Nueva Sucursal
                        </Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Crear Sucursal</DialogTitle>
                            <DialogDescription>
                                Agregá una nueva sucursal a tu plan.
                            </DialogDescription>
                        </DialogHeader>
                        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="name">Nombre</Label>
                                <Input
                                    id="name"
                                    placeholder="Ej. Sucursal Centro"
                                    {...register('name', { required: 'El nombre es requerido', minLength: { value: 3, message: 'Mínimo 3 caracteres' } })}
                                />
                                {errors.name && (
                                    <p className="text-sm text-red-500">{errors.name.message}</p>
                                )}
                            </div>
                            <DialogFooter>
                                <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                                    Cancelar
                                </Button>
                                <Button type="submit" disabled={createMutation.isPending}>
                                    {createMutation.isPending ? 'Creando...' : 'Crear'}
                                </Button>
                            </DialogFooter>
                        </form>
                    </DialogContent>
                </Dialog>
            </div>

            <div className="rounded-md border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Nombre</TableHead>
                            <TableHead>Estado</TableHead>
                            <TableHead>Creada</TableHead>
                            <TableHead>ID</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {branches?.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={4} className="h-24 text-center">
                                    No hay sucursales creadas.
                                </TableCell>
                            </TableRow>
                        ) : (
                            branches?.map((branch) => (
                                <TableRow key={branch.id}>
                                    <TableCell className="font-medium">{branch.name}</TableCell>
                                    <TableCell>
                                        <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                                            {branch.status}
                                        </span>
                                    </TableCell>
                                    <TableCell>
                                        {new Date(branch.created_at).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">{branch.id}</TableCell>
                                </TableRow>
                            ))
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
