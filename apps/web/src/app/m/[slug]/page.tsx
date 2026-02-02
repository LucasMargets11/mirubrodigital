import { notFound } from 'next/navigation'
import { getServerApiBaseUrl } from '@/lib/api-url'
import { PublicMenuLayout } from '@/components/public-menu/menu-layout' // Adjust path if needed
import { MenuCategory, MenuConfig } from '@/components/public-menu/types'

type MenuData = {
  config: {
    brand_name: string;
    description?: string;
    theme_json?: {
      primary?: string;
      secondary?: string;
      background?: string;
      text?: string;
    };
  };
  categories: Array<{
    id: number | string;
    name: string;
    description?: string;
    items: Array<{
      id: number | string;
      name: string;
      description?: string;
      price: number | string;
      is_available: boolean;
      is_featured?: boolean;
    }>;
  }>;
};

type FetchResult = 
  | { success: true; data: MenuData }
  | { success: false; errorType: 'NOT_FOUND' | 'NETWORK_ERROR' | 'UNKNOWN'; message?: string };

async function getPublicMenu(slug: string): Promise<FetchResult> {
  const apiUrl = getServerApiBaseUrl()
  const endpoint = `${apiUrl}/api/v1/menu/public/slug/${slug}/`
  
  try {
    const res = await fetch(endpoint, { 
      cache: 'no-store',
    })
    
    if (res.status === 404) {
      return { success: false, errorType: 'NOT_FOUND' }
    }
    
    if (!res.ok) {
        console.error(`[getPublicMenu] Error ${res.status} fetching ${endpoint}`)
        return { success: false, errorType: 'UNKNOWN', message: `API Error ${res.status}` }
    }
    
    const data = await res.json()
    return { success: true, data }
  } catch (e: any) {
    const isConnectionError = e.code === 'ECONNREFUSED' || e.cause?.code === 'ECONNREFUSED';
    console.error(`[getPublicMenu] Fetch failed to ${endpoint}. Cause: ${e.cause}`, e)
    
    if (isConnectionError) {
        return { success: false, errorType: 'NETWORK_ERROR', message: 'Could not connect to backend API' }
    }
    return { success: false, errorType: 'UNKNOWN', message: e.message }
  }
}

export default async function PublicMenuPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const result = await getPublicMenu(slug)
  
  if (!result.success) {
      if (result.errorType === 'NOT_FOUND') {
          return notFound()
      }
      if (result.errorType === 'NETWORK_ERROR') {
          return (
              <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center space-y-4 bg-slate-50">
                  <h1 className="text-2xl font-bold text-red-600">Sistema no disponible</h1>
                  <p className="text-slate-600">No pudimos conectar con el servidor del menú.</p>
                  <p className="text-xs text-slate-400 font-mono">Error: {result.message}</p>
              </div>
          )
      }
      return (
         <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center space-y-4">
            <h1 className="text-xl font-bold">Algo salió mal</h1>
            <p className="text-slate-600">No se pudo cargar el menú.</p>
         </div>
      )
  }

  const { config, categories } = result.data;
  
  // Cast/Map to expected types
  const mappedConfig: MenuConfig = {
      brand_name: config.brand_name,
      description: config.description,
      theme_json: config.theme_json,
  };

  const mappedCategories: MenuCategory[] = categories.map(c => ({
      id: c.id,
      name: c.name,
      description: c.description,
      items: c.items.map(i => ({
          ...i,
          is_featured: i.is_featured ?? false
      }))
  }));


  return (
    <PublicMenuLayout config={mappedConfig} categories={mappedCategories} />
  )
}
