import { redirect } from 'next/navigation'

export async function GET(request: Request, { params }: { params: Promise<{ public_id: string }> }) {
  const { public_id } = await params
  const apiUrl = process.env.API_URL || 'http://localhost:8000'
  
  try {
    const res = await fetch(`${apiUrl}/api/v1/menu/public/resolve/${public_id}/`, { cache: 'no-store' })
    if (res.ok) {
        const data = await res.json()
        redirect(`/m/${data.slug}`)
    }
  } catch(e) {
      console.error(e)
  }
  
  return new Response('Menu not found', { status: 404 })
}
