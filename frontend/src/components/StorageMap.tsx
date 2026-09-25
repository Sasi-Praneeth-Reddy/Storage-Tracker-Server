/**
 * StorageMap.tsx
 * Leaflet map using free OpenStreetMap tiles — no API key required.
 * Markers are colour-coded by brand. Clicking shows facility details.
 */
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix missing marker icons in Vite bundles
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const BRAND_COLORS: Record<string, string> = {
  'Public Storage':   '#FF9800',
  'Extra Space Storage': '#4CAF50',
  'CubeSmart':        '#F44336',
  'U-Haul':           '#9C27B0',
  'Life Storage':     '#2196F3',
  'StorQuest':        '#00BCD4',
};

function brandColor(brand: string): string {
  for (const [key, color] of Object.entries(BRAND_COLORS)) {
    if (brand.includes(key)) return color;
  }
  return '#8B92A5';
}

interface Facility {
  id: number;
  name: string;
  brand: string;
  address: string;
  city: string;
  zip_code: string;
  latitude: number;
  longitude: number;
  unit_size?: string;
  web_rate?: number;
}

interface StorageMapProps {
  facilities: Facility[];
  selectedSize?: string;
  height?: number;
}

export default function StorageMap({ facilities, selectedSize, height = 500 }: StorageMapProps) {
  // Deduplicate by facility id (keep first occurrence)
  const deduped = Object.values(
    facilities.reduce((acc, f) => {
      if (!acc[f.id]) acc[f.id] = f;
      return acc;
    }, {} as Record<number, Facility>)
  ).filter(f => f.latitude && f.longitude);

  const center: [number, number] =
    deduped.length > 0
      ? [
          deduped.reduce((s, f) => s + f.latitude, 0) / deduped.length,
          deduped.reduce((s, f) => s + f.longitude, 0) / deduped.length,
        ]
      : [38.9072, -77.0369]; // Tysons Corner default

  return (
    <MapContainer
      center={center}
      zoom={9}
      style={{ height, borderRadius: 8, width: '100%' }}
      scrollWheelZoom
    >
      {/* Free OpenStreetMap — CartoDB Dark Matter style, no key needed */}
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        subdomains="abcd"
        maxZoom={19}
      />
      {deduped.map(f => {
        const priceLabel =
          f.web_rate != null ? `$${f.web_rate.toFixed(0)}/mo` : 'N/A';
        return (
          <CircleMarker
            key={f.id}
            center={[f.latitude, f.longitude]}
            radius={5}
            pathOptions={{
              color:       brandColor(f.brand),
              fillColor:   brandColor(f.brand),
              fillOpacity: 0.85,
              weight:      1,
            }}
          >
            <Popup>
              <div style={{ minWidth: 160 }}>
                <strong style={{ fontSize: 13 }}>{f.name}</strong>
                <div style={{ fontSize: 11, color: '#aaa', marginTop: 2 }}>{f.brand}</div>
                <div style={{ marginTop: 6, fontSize: 12 }}>
                  📍 {f.address}, {f.city} {f.zip_code}
                </div>
                {selectedSize && (
                  <div style={{ marginTop: 4, fontSize: 12 }}>
                    📦 {selectedSize}: <strong>{priceLabel}</strong>
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
