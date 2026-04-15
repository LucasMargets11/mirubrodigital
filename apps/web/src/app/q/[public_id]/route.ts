import { redirect } from 'next/navigation'
import { getServerApiBaseUrl } from '@/lib/api-url'

export const dynamic = 'force-dynamic'

export async function GET(request: Request, { params }: { params: Promise<{ public_id: string }> }) {
  const { public_id } = await params
  const apiUrl = getServerApiBaseUrl()

  const res = await fetch(`${apiUrl}/api/v1/menu/public/resolve/${public_id}/`, {
    cache: 'no-store',
  })

  if (!res.ok) {
    return new Response('Menu not found', { status: 404 })
  }

  const data = await res.json()
  redirect(`/m/${data.slug}`)
}
