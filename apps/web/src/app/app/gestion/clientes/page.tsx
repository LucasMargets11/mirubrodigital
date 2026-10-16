import { redirect } from 'next/navigation';

// Clientes es una entidad compartida (Gestión y Turnos, CUSTOMER 02): la
// superficie canónica es `/app/clientes`. Se mantiene esta URL por links viejos.
export default function GestionClientesRedirect() {
    redirect('/app/clientes');
}
