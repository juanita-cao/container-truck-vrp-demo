/** Google 编码折线解码（polyline6），返回 [经度, 纬度]。 */
export function decodePolyline(s: string, precision = 6): [number, number][] {
  const factor = Math.pow(10, precision);
  let lat = 0, lon = 0, i = 0;
  const out: [number, number][] = [];
  while (i < s.length) {
    for (let axis = 0; axis < 2; axis++) {
      let shift = 0, result = 0, b: number;
      do {
        b = s.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const d = result & 1 ? ~(result >> 1) : result >> 1;
      if (axis === 0) lat += d; else lon += d;
    }
    out.push([lon / factor, lat / factor]);
  }
  return out;
}
