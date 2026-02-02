import { 
  Playfair_Display, 
  Cormorant_Garamond, 
  Libre_Baskerville, 
  Alegreya, 
  Merriweather, 
  Alegreya_Sans, 
  Source_Sans_3, 
  Inter, 
  Lora, 
  EB_Garamond 
} from 'next/font/google';

const playfair = Playfair_Display({ subsets: ['latin'], variable: '--font-playfair', display: 'swap' });
const cormorant = Cormorant_Garamond({ weight: ['300', '400', '500', '600', '700'], subsets: ['latin'], variable: '--font-cormorant', display: 'swap' });
const libreBaskerville = Libre_Baskerville({ weight: ['400', '700'], subsets: ['latin'], variable: '--font-libre-baskerville', display: 'swap' });
const alegreya = Alegreya({ subsets: ['latin'], variable: '--font-alegreya', display: 'swap' });
const merriweather = Merriweather({ weight: ['300', '400', '700', '900'], subsets: ['latin'], variable: '--font-merriweather', display: 'swap' });
const alegreyaSans = Alegreya_Sans({ weight: ['100', '300', '400', '500', '700', '800', '900'], subsets: ['latin'], variable: '--font-alegreya-sans', display: 'swap' });
const sourceSans = Source_Sans_3({ subsets: ['latin'], variable: '--font-source-sans', display: 'swap' });
const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const lora = Lora({ subsets: ['latin'], variable: '--font-lora', display: 'swap' });
const ebGaramond = EB_Garamond({ subsets: ['latin'], variable: '--font-eb-garamond', display: 'swap' });

export const menuFontsVariablesClassName = [
  playfair.variable,
  cormorant.variable,
  libreBaskerville.variable,
  alegreya.variable,
  merriweather.variable,
  alegreyaSans.variable,
  sourceSans.variable,
  inter.variable,
  lora.variable,
  ebGaramond.variable,
].join(' ');

export const MENU_FONTS_MAP: Record<string, { label: string; variable: string }> = {
  playfair_display: { label: 'Playfair Display', variable: 'var(--font-playfair)' },
  cormorant_garamond: { label: 'Cormorant Garamond', variable: 'var(--font-cormorant)' },
  libre_baskerville: { label: 'Libre Baskerville', variable: 'var(--font-libre-baskerville)' },
  alegreya: { label: 'Alegreya', variable: 'var(--font-alegreya)' },
  merriweather: { label: 'Merriweather', variable: 'var(--font-merriweather)' },
  alegreya_sans: { label: 'Alegreya Sans', variable: 'var(--font-alegreya-sans)' },
  source_sans_3: { label: 'Source Sans 3', variable: 'var(--font-source-sans)' },
  inter: { label: 'Inter', variable: 'var(--font-inter)' },
  lora: { label: 'Lora', variable: 'var(--font-lora)' },
  eb_garamond: { label: 'EB Garamond', variable: 'var(--font-eb-garamond)' },
};

export const DEFAULT_MENU_FONT = 'inter';

export function getMenuFontFamily(key?: string) {
  const fontKey = key && MENU_FONTS_MAP[key] ? key : DEFAULT_MENU_FONT;
  return `${MENU_FONTS_MAP[fontKey].variable}, system-ui, sans-serif`;
}
