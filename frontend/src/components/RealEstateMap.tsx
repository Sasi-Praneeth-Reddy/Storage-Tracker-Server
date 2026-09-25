/**
 * RealEstateMap.tsx
 * Free OpenStreetMap Leaflet map for real estate listings.
 * Colour-coded by listing status. No API key required.
 */
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';

const STATUS_COLOR: Record<string, string> = {
  for_sale:         '#4CAF50',
  under_contract:   '#FF9800',
  sold:             '#2196F3',
};

interface Listing {
  address: string;
  city: string;
  county: string;
  zip_code: string;
  status: string;
  list_price?: number;
  latitude: number;
  longitude: number;
}

interface RealEstateMapProps {
  listings: Listing[];
  height?: number;
}

export default function RealEstateMap({ listings, height = 500 }: RealEstateMapProps) {
  const mapped = listings.filter(l => l.latitude && l.longitude);

  // Sample if too many markers for performance
  const displayed = mapped.length > 1500 ? mapped.slice(0, 1500) : mapped;

  const center: [number, number] =
    displayed.length > 0
      ? [
          displayed.reduce((s, l) => s + l.latitude, 0) / displayed.length,
          displayed.reduce((s, l) => s + l.longitude, 0) / displayed.length,
        ]
      : [38.9072, -77.0369];

  return (
    <>
      {mapped.length > 1500 && (
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>
          Showing first 1,500 of {mapped.length.toLocaleString()} properties for performance
        </div>
      )}
      <MapContainer
        center={center}
        zoom={9}
        style={{ height, borderRadius: 8, width: '100%' }}
        scrollWheelZoom
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          maxZoom={19}
        />
        {displayed.map((l, i) => (
          <CircleMarker
            key={i}
            center={[l.latitude, l.longitude]}
            radius={4}
            pathOptions={{
              color:       STATUS_COLOR[l.status] ?? '#8B92A5',
              fillColor:   STATUS_COLOR[l.status] ?? '#8B92A5',
              fillOpacity: 0.75,
              weight:      1,
            }}
          >
            <Popup>
              <div style={{ minWidth: 180 }}>
                <strong style={{ fontSize: 13 }}>{l.address}</strong>
                <div style={{ fontSize: 11, color: '#aaa', marginTop: 2 }}>{l.city}, {l.zip_code}</div>
                <div style={{ marginTop: 6, fontSize: 12 }}>
                  💰 {l.list_price != null ? `$${l.list_price.toLocaleString()}` : 'N/A'}
                </div>
                <div style={{ fontSize: 12 }}>
                  Status: <strong>{l.status.replace(/_/g, ' ')}</strong>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </>
  );
}
