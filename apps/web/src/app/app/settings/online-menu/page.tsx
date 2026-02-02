'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { getPublicMenuConfig, updatePublicMenuConfig, uploadMenuLogo } from '@/features/menu/api'
import type { PublicMenuConfig } from '@/features/menu/types'
import { MENU_FONTS_MAP, menuFontsVariablesClassName, getMenuFontFamily } from '@/lib/fonts'
import { ONLINE_MENU_PRESETS, applyPreset } from '@/lib/online-menu-presets'
import { MenuBrandHeader } from '@/components/public-menu/brand-header'

function ColorInput({ label, value, onChange }: { label: string, value: string, onChange: (val: string) => void }) {
    const [localValue, setLocalValue] = useState(value);
    const [error, setError] = useState(false);

    useEffect(() => {
        setLocalValue(value);
        setError(false);
    }, [value]);

    const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const newVal = e.target.value;
        setLocalValue(newVal);
        
        // Simple hex validation
        const isValidHex = /^#([0-9A-F]{3}){1,2}$/i.test(newVal);
        if (isValidHex) {
           setError(false);
           onChange(newVal.toLowerCase());
        } else {
           setError(true);
        }
    };

    return (
        <div>
            <label className="block text-xs font-medium mb-1">{label}</label>
            <div className="flex items-center gap-2">
                <input 
                    type="color" 
                    className="h-9 w-9 rounded cursor-pointer border-0 p-0 shadow-sm" 
                    value={!error ? localValue : '#000000'} // Fallback if error, or just keep previous valid
                    onChange={e => {
                        const val = e.target.value;
                        setLocalValue(val);
                        setError(false);
                        onChange(val);
                    }} 
                />
                <div className="relative flex-1">
                    <input 
                        className={`w-full text-xs font-mono border rounded px-2 py-1.5 focus:outline-none focus:ring-2 ${error ? 'border-red-500 focus:ring-red-200' : 'border-slate-200 focus:ring-blue-100'}`}
                        value={localValue}
                        onChange={handleTextChange}
                        maxLength={7}
                    />
                </div>
            </div>
            {error && <span className="text-[10px] text-red-500">Hex inválido</span>}
        </div>
    );
}

export default function OnlineMenuSettingsPage() {
  const [config, setConfig] = useState<PublicMenuConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploadingLogo, setUploadingLogo] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  async function loadConfig() {
    try {
      const data = await getPublicMenuConfig()
      setConfig(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!config) return
    setSaving(true)
    try {
      const updated = await updatePublicMenuConfig({
        enabled: config.enabled,
        slug: config.slug,
        brand_name: config.brand_name,
        theme_json: config.theme_json,
      })
      setConfig(updated)
      // alert("Guardado correctamente")
    } catch (e) {
      // alert("Error al guardar")
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="p-8">Cargando configuración...</div>
  if (!config) return <div className="p-8">Error cargando configuración. Asegúrate de tener un negocio activo.</div>

  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirubro.digital'
  const finalQrUrl = `${origin}/q/${config.public_id}`
  const qrImageSrc = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(finalQrUrl)}`

  return (
    <div className="p-6 space-y-8 max-w-4xl animate-in fade-in">
      <div className="flex items-center justify-between">
         <h1 className="text-2xl font-bold tracking-tight">Carta Online</h1>
         <div className="flex gap-2">
             {config.enabled && (
                 <Button variant="outline" asChild>
                    <Link href={`/m/${config.slug}`} target="_blank">Ver Carta</Link>
                 </Button>
             )}
             <Button onClick={handleSave} disabled={saving}>
               {saving ? 'Guardando...' : 'Guardar Cambios'}
             </Button>
         </div>
      </div>
      
      <div className="flex items-center space-x-4 bg-white p-4 rounded-lg border shadow-sm">
        <Switch 
          checked={config.enabled} 
          onCheckedChange={(c: boolean) => setConfig({...config, enabled: c})} 
        />
        <label className="text-sm font-medium">Habilitar Carta Pública</label>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="space-y-6">
            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4">
                <h2 className="text-lg font-semibold">Configuración General</h2>
                <div>
                   <label className="block text-sm font-medium mb-1">Slug URL (Dirección web)</label>
                   <div className="flex items-center gap-2">
                     <span className="text-slate-500 text-sm whitespace-nowrap">{origin}/m/</span>
                     <input 
                       value={config.slug} 
                       onChange={(e) => setConfig({...config, slug: e.target.value})} 
                       className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                     />
                   </div>
                   <p className="text-xs text-slate-500 mt-1">Identificador único para tu carta.</p>
                </div>
                <div>
                   <label className="block text-sm font-medium mb-1">Nombre del Negocio (Visible)</label>
                   <input 
                     value={config.brand_name} 
                     onChange={(e) => setConfig({...config, brand_name: e.target.value})} 
                     className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                   />
                </div>
            </div>

            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4">
                <h2 className="text-lg font-semibold">Logo de la Carta</h2>
                
                <div>
                   <label className="block text-sm font-medium mb-1">Logo del Negocio</label>
                   
                   <div className="flex items-center gap-4 border p-3 rounded-lg bg-slate-50">
                       {/* Preview current logo small */}
                       {config.theme_json?.menuLogoUrl ? (
                           <div className="relative h-16 w-16 shrink-0 rounded border bg-white p-1 flex items-center justify-center overflow-hidden">
                               <img src={config.theme_json.menuLogoUrl} alt="Logo actual" className="h-full w-full object-contain" />
                           </div>
                       ) : (
                           <div className="h-16 w-16 bg-slate-200 rounded flex items-center justify-center text-slate-400 text-[10px] text-center p-1">
                               Sin Logo
                           </div>
                       )}

                       <div className="flex-1 min-w-0">
                           <input 
                               type="file" 
                               accept="image/png, image/jpeg, image/jpg, image/svg+xml, image/webp"
                               onChange={async (e) => {
                                    if (!e.target.files || e.target.files.length === 0) return;
                                    const file = e.target.files[0];
                                    
                                    if (!config) return;

                                    setUploadingLogo(true);
                                    try {
                                        const res = await uploadMenuLogo(file);
                                        setConfig({...config, theme_json: {...config.theme_json, menuLogoUrl: res.url}});
                                    } catch (err) {
                                        console.error("Error uploading logo", err);
                                        // Using browser alert for simplicity in this specific user flow request
                                        alert("Error al subir el logo. Intenta con un archivo más pequeño o formato diferente.");
                                    } finally {
                                        setUploadingLogo(false);
                                        // Reset input
                                        e.target.value = '';
                                    }
                               }}
                               disabled={uploadingLogo}
                               className="block w-full text-sm text-slate-500
                                 file:mr-4 file:py-2 file:px-4
                                 file:rounded-full file:border-0
                                 file:text-xs file:font-semibold
                                 file:bg-slate-100 file:text-slate-700
                                 hover:file:bg-slate-200
                                 cursor-pointer
                               "
                           />
                           <p className="mt-1 text-xs text-slate-500">
                               {uploadingLogo ? 'Subiendo imagen...' : 'PNG, JPG, WebP o SVG. Recomendado fondo transparente.'}
                           </p>
                       </div>

                       {config.theme_json?.menuLogoUrl && (
                            <Button 
                                variant="outline" 
                                size="sm" 
                                className="text-red-500 hover:text-red-700 hover:bg-red-50 border-red-200 hover:border-red-300" 
                                onClick={() => setConfig({...config, theme_json: {...config.theme_json, menuLogoUrl: ''}})}
                                disabled={uploadingLogo}
                            >
                                Quitar
                            </Button>
                       )}
                   </div>
                </div>

                <div>
                    <label className="block text-sm font-medium mb-2">Posición</label>
                    <div className="grid grid-cols-2 gap-2">
                        {[
                            { id: 'top_center', label: 'Centrado Arriba' },
                            { id: 'title_left', label: 'Izquierda' },
                            { id: 'top_right_small', label: 'Superior Derecha' },
                            { id: 'watermark', label: 'Marca de Agua (Fondo)' }
                        ].map((pos) => (
                            <button
                                key={pos.id}
                                className={`p-2 rounded border text-xs text-left transition-colors ${
                                    (config.theme_json?.menuLogoPosition || 'top_center') === pos.id 
                                    ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium ring-1 ring-blue-500' 
                                    : 'border-slate-200 hover:border-slate-300'
                                }`}
                                onClick={() => setConfig({...config, theme_json: {...config.theme_json, menuLogoPosition: pos.id as any}})}
                            >
                                {pos.label}
                            </button>
                        ))}
                    </div>
                </div>

                {(config.theme_json?.menuLogoPosition || 'top_center') !== 'watermark' && (
                    <div>
                         <label className="block text-sm font-medium mb-2">Tamaño</label>
                         <div className="flex gap-2">
                             {['sm', 'md', 'lg'].map((size) => (
                                 <button
                                     key={size}
                                     className={`px-3 py-1 rounded border text-xs transition-colors uppercase ${
                                         (config.theme_json?.menuLogoSize || 'md') === size
                                         ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium ring-1 ring-blue-500'
                                         : 'border-slate-200 hover:border-slate-300' 
                                     }`}
                                     onClick={() => setConfig({...config, theme_json: {...config.theme_json, menuLogoSize: size as any}})}
                                 >
                                     {size}
                                 </button>
                             ))}
                         </div>
                    </div>
                )}

                 {(config.theme_json?.menuLogoPosition) === 'watermark' && (
                    <div>
                        <label className="block text-sm font-medium mb-1">
                            Opacidad ({(config.theme_json?.menuLogoWatermarkOpacity || 0.08)})
                        </label>
                         <input 
                            type="range" 
                            min="0.05" 
                            max="0.15" 
                            step="0.01"
                            className="w-full"
                            value={config.theme_json?.menuLogoWatermarkOpacity || 0.08}
                            onChange={(e) => setConfig({...config, theme_json: {...config.theme_json, menuLogoWatermarkOpacity: Number(e.target.value)}})}
                        />
                    </div>
                 )}
            </div>

            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4">
               <div className="flex items-center justify-between">
                   <h2 className="text-lg font-semibold">Personalización</h2>
                   <select 
                       className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs"
                       onChange={(e) => {
                           if (config && e.target.value) {
                             const newTheme = applyPreset(config.theme_json, e.target.value);
                             setConfig({...config, theme_json: newTheme as any});
                           }
                       }}
                       defaultValue=""
                   >
                       <option value="" disabled>Cargar Preset...</option>
                       {ONLINE_MENU_PRESETS.map(p => (
                           <option key={p.id} value={p.id}>{p.name}</option>
                       ))}
                   </select>
               </div>
               
               <div className="grid grid-cols-2 gap-4">
                 <ColorInput 
                    label="Fondo (Background)" 
                    value={config.theme_json?.background || '#0a0a0a'}
                    onChange={(v) => setConfig({...config, theme_json: {...config.theme_json, background: v}})}
                 />
                 <ColorInput 
                    label="Texto Principal" 
                    value={config.theme_json?.text || '#ffffff'}
                    onChange={(v) => setConfig({...config, theme_json: {...config.theme_json, text: v}})}
                 />
                 <ColorInput 
                    label="Texto Secundario (Muted)" 
                    value={config.theme_json?.mutedText || '#a3a3a3'}
                    onChange={(v) => setConfig({...config, theme_json: {...config.theme_json, mutedText: v}})}
                 />
                 <ColorInput 
                    label="Acento (Precios/Títulos)" 
                    value={config.theme_json?.accent || '#8b5cf6'}
                    onChange={(v) => setConfig({...config, theme_json: {...config.theme_json, accent: v}})}
                 />
                 <ColorInput 
                    label="Divisores/Bordes" 
                    value={config.theme_json?.divider || '#262626'}
                    onChange={(v) => setConfig({...config, theme_json: {...config.theme_json, divider: v}})}
                 />
               </div>
               
               <div>
                   <label className="block text-sm font-medium mb-1">Fuentes</label>
                   <div className="grid grid-cols-2 gap-4">
                       <div>
                            <label className="mb-1 block text-xs text-slate-500">Títulos (Heading)</label>
                            <select 
                                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                value={config.theme_json?.headingFont || config.theme_json?.fontFamily || 'inter'} // Fallback
                                onChange={(e) => setConfig({...config, theme_json: {...config.theme_json, headingFont: e.target.value}})}
                            >
                                {Object.entries(MENU_FONTS_MAP).map(([key, font]) => (
                                    <option key={key} value={key}>{font.label}</option>
                                ))}
                            </select>
                       </div>
                       <div>
                            <label className="mb-1 block text-xs text-slate-500">Cuerpo (Body)</label>
                            <select 
                                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                value={config.theme_json?.bodyFont || config.theme_json?.fontFamily || 'inter'}
                                onChange={(e) => setConfig({...config, theme_json: {...config.theme_json, bodyFont: e.target.value, fontFamily: e.target.value}})}
                            >
                                {Object.entries(MENU_FONTS_MAP).map(([key, font]) => (
                                    <option key={key} value={key}>{font.label}</option>
                                ))}
                            </select>
                       </div>
                   </div>

                   <div className="mt-4 grid grid-cols-2 gap-4">
                        <div>
                            <label className="mb-1 block text-xs text-slate-500">
                                Tamaño Títulos ({config.theme_json?.menuHeadingFontSize || 1.25}rem)
                            </label>
                            <input 
                                type="range" 
                                min="1.125" 
                                max="1.75" 
                                step="0.125"
                                className="w-full"
                                value={config.theme_json?.menuHeadingFontSize || 1.25}
                                onChange={(e) => setConfig({...config, theme_json: {...config.theme_json, menuHeadingFontSize: Number(e.target.value)}})}
                            />
                        </div>
                        <div>
                            <label className="mb-1 block text-xs text-slate-500">
                                Tamaño Cuerpo ({config.theme_json?.menuBodyFontSize || 1}rem)
                            </label>
                            <input 
                                type="range" 
                                min="0.875" 
                                max="1.125" 
                                step="0.0625"
                                className="w-full"
                                value={config.theme_json?.menuBodyFontSize || 1}
                                onChange={(e) => setConfig({...config, theme_json: {...config.theme_json, menuBodyFontSize: Number(e.target.value)}})}
                            />
                        </div>
                   </div>

                   {/* Preview Font */}
                   <div 
                        className={`mt-4 rounded-md border p-4 text-center ${menuFontsVariablesClassName} overflow-hidden`}
                        style={{
                            backgroundColor: config.theme_json?.background || '#0a0a0a',
                            color: config.theme_json?.text || '#ffffff',
                            fontFamily: getMenuFontFamily(config.theme_json?.bodyFont || config.theme_json?.fontFamily),
                             // Inject CSS Variables for MenuBrandHeader & Items
                            '--menu-bg': config.theme_json?.background || '#0a0a0a',
                            '--menu-text': config.theme_json?.text || '#ffffff',
                            '--menu-muted': config.theme_json?.mutedText || '#a3a3a3',
                            '--menu-accent': config.theme_json?.accent || '#8b5cf6',
                            '--menu-divider': config.theme_json?.divider || '#262626',
                            '--menu-font-body': getMenuFontFamily(config.theme_json?.bodyFont || config.theme_json?.fontFamily),
                            '--menu-font-heading': getMenuFontFamily(config.theme_json?.headingFont || config.theme_json?.bodyFont || config.theme_json?.fontFamily),
                            '--menu-size-heading': `${config.theme_json?.menuHeadingFontSize || 1.25}rem`,
                            '--menu-size-body': `${config.theme_json?.menuBodyFontSize || 1}rem`,
                            '--menu-watermark-opacity': config.theme_json?.menuLogoWatermarkOpacity || 0.08,
                        } as React.CSSProperties}
                   >
                       <div className="mb-6 border-b border-dashed border-white/20 pb-4 relative">
                             {/* Watermark Preview */}
                            {config.theme_json?.menuLogoUrl && config.theme_json?.menuLogoPosition === 'watermark' && (
                                <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ opacity: config.theme_json?.menuLogoWatermarkOpacity || 0.08 }}>
                                    <img src={config.theme_json.menuLogoUrl} className="h-full w-auto max-h-20 object-contain grayscale" />
                                </div>
                            )}

                           <div className="relative z-10 w-full">
                                <MenuBrandHeader 
                                    brandDetails={{ 
                                        name: config.brand_name || 'Mi Restaurant', 
                                        description: (config as any).description || 'La mejor comida de la ciudad' 
                                    }}
                                    theme={config.theme_json || {}}
                                />
                           </div>
                       </div>

                       <p 
                        className="font-bold mb-2 text-left"
                        style={{ 
                            fontFamily: 'var(--menu-font-heading)',
                            fontSize: 'calc(var(--menu-size-body) * 1.1)'
                        }}
                       >
                        Entradas / Pizzas
                       </p>
                       <div className="flex justify-between items-center" style={{ fontSize: 'var(--menu-size-body)' }}>
                           <span style={{ fontFamily: 'var(--menu-font-heading)' }}>Muzzarella</span>
                           <span style={{ color: 'var(--menu-accent)', fontFamily: 'var(--menu-font-heading)' }}>$12.500</span>
                       </div>
                       <p className="mt-1 text-left opacity-70" style={{ 
                           color: config.theme_json?.mutedText,
                           fontSize: 'calc(var(--menu-size-body) * 0.85)'
                        }}>
                           Salsa de tomate, muzzarella y orégano fresco.
                       </p>
                   </div>
               </div>
            </div>
        </div>
        
        <div className="space-y-6">
           <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4 text-center">
              <h2 className="text-lg font-semibold text-left">QR Acceso Directo</h2>
              <div className="flex justify-center p-4 bg-white rounded border inline-block mx-auto">
                 {/* Using external API to avoid missing dependency issues in this env */}
                 <img src={qrImageSrc} alt="QR Code" width={200} height={200} />
              </div>
              <div className="text-center">
                  <a href={qrImageSrc} download="carta-qr.png" target="_blank" className="text-sm text-blue-600 hover:underline">Descargar Imagen</a>
              </div>
              <p className="text-xs text-slate-500 break-all bg-slate-50 p-2 rounded">{finalQrUrl}</p>
              <p className="text-xs text-slate-400">
                Este QR es permanente. Redirige a la dirección actual de tu carta.
                Puedes imprimirlo y colocarlo en tus mesas.
              </p>
           </div>
        </div>
      </div>
    </div>
  )
}
