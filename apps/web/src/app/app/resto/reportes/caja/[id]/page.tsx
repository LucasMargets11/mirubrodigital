import { redirect } from 'next/navigation';

type PageProps = {
    params: {
        id: string;
    };
};

export default function LegacyRestauranteCashClosureDetailRedirect({ params }: PageProps) {
    redirect(`/app/resto/operacion/reportes/caja/${params.id}`);
}
