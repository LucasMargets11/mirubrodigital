import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { getServiceEntryPath } from '@/lib/services';

export default async function DashboardPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const targetService = session.current?.service || session.services.default || session.services.enabled[0];
    if (targetService) {
        const entryPath = getServiceEntryPath(targetService);
        if (entryPath) {
            redirect(entryPath);
        }
    }

    redirect('/app/servicios');
}
