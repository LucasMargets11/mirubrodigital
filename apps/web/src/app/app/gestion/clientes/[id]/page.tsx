import { redirect } from 'next/navigation';

type Props = {
    params: Promise<{ id: string }>;
};

// Ficha única de Cliente en `/app/clientes/[id]` (CUSTOMER 02).
export default async function GestionCustomerDetailRedirect({ params }: Props) {
    const { id } = await params;
    redirect(`/app/clientes/${encodeURIComponent(id)}`);
}
