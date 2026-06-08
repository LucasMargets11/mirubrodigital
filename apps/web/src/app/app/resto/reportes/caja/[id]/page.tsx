import { redirect } from 'next/navigation';

type PageProps = {
    params: Promise<{
        id: string;
    }>;
};

export default async function LegacyRestauranteCashClosureDetailRedirect({ params }: PageProps) {
    const { id } = await params;
    redirect(`/app/resto/operacion/reportes/caja/${id}`);
}
