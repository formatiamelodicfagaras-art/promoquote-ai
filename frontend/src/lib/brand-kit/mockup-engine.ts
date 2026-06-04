import type { PrintArea, MockupConfig, WarpMode } from "./types";

// Estimated position on product image based on print location from API
const LOCATION_MAPPING: Record<string, { x_pct: number; y_pct: number }> = {
  front: { x_pct: 30, y_pct: 30 },
  "front center": { x_pct: 30, y_pct: 30 },
  back: { x_pct: 30, y_pct: 30 },
  "back center": { x_pct: 30, y_pct: 30 },
  "left side": { x_pct: 10, y_pct: 35 },
  "right side": { x_pct: 60, y_pct: 35 },
  "left chest": { x_pct: 55, y_pct: 25 },
  "right chest": { x_pct: 20, y_pct: 25 },
  "cap front": { x_pct: 25, y_pct: 20 },
  barrel: { x_pct: 20, y_pct: 40 },
  clip: { x_pct: 40, y_pct: 10 },
  body: { x_pct: 25, y_pct: 30 },
  panel: { x_pct: 30, y_pct: 30 },
  default: { x_pct: 25, y_pct: 25 },
};

// Rough estimates of total product dimensions (mm) by category keyword
function estimateProductSizeMm(category: string): {
  w: number;
  h: number;
} {
  const cat = (category || "").toLowerCase();
  if (cat.includes("pen") || cat.includes("pix") || cat.includes("styl"))
    return { w: 12, h: 140 };
  if (cat.includes("mug") || cat.includes("cup") || cat.includes("can"))
    return { w: 80, h: 95 };
  if (
    cat.includes("bottle") ||
    cat.includes("flask") ||
    cat.includes("sticl")
  )
    return { w: 70, h: 250 };
  if (cat.includes("bag") || cat.includes("sacosa") || cat.includes("gent"))
    return { w: 350, h: 400 };
  if (
    cat.includes("shirt") ||
    cat.includes("polo") ||
    cat.includes("tricou") ||
    cat.includes("textile")
  )
    return { w: 500, h: 700 };
  if (cat.includes("cap") || cat.includes("hat") || cat.includes("sapc"))
    return { w: 200, h: 120 };
  if (
    cat.includes("umbrella") ||
    cat.includes("umbrel")
  )
    return { w: 1000, h: 800 };
  if (cat.includes("usb") || cat.includes("tech") || cat.includes("power"))
    return { w: 60, h: 100 };
  if (cat.includes("keychain") || cat.includes("breloc"))
    return { w: 40, h: 50 };
  return { w: 200, h: 200 };
}

function findLocationMapping(location: string): {
  x_pct: number;
  y_pct: number;
} {
  const loc = location.toLowerCase().trim();
  for (const [key, val] of Object.entries(LOCATION_MAPPING)) {
    if (loc.includes(key)) return val;
  }
  return LOCATION_MAPPING.default;
}

function isColorDark(hex: string): boolean {
  const c = hex.replace("#", "");
  if (c.length < 6) return true;
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance < 0.5;
}

/** Auto-detect warp mode from category keywords. */
export function detectWarpMode(category: string): WarpMode {
  const cat = (category || "").toLowerCase();
  // Cylindrical products
  if (
    cat.includes("bottle") || cat.includes("flask") || cat.includes("sticl") ||
    cat.includes("mug") || cat.includes("cup") || cat.includes("can") ||
    cat.includes("pen") || cat.includes("pix") || cat.includes("styl") ||
    cat.includes("thermos") || cat.includes("termos") ||
    cat.includes("tumbler") || cat.includes("pahar")
  )
    return "cylinder";
  // Arc-shaped surfaces (caps, hats)
  if (
    cat.includes("cap") || cat.includes("hat") || cat.includes("sapc") ||
    cat.includes("visor")
  )
    return "arc";
  return "none";
}

export function calculateMockupConfig(
  printArea: PrintArea | null,
  category: string,
  productColor?: string
): MockupConfig {
  const pos = findLocationMapping(printArea?.location || "front");
  const productSize = estimateProductSizeMm(category);

  let widthPct = 40;
  let heightPct = 30;

  if (printArea && printArea.width_mm > 0 && printArea.height_mm > 0) {
    widthPct = Math.min(
      60,
      Math.max(10, (printArea.width_mm / productSize.w) * 100)
    );
    heightPct = Math.min(
      50,
      Math.max(8, (printArea.height_mm / productSize.h) * 100)
    );
  }

  const warp = detectWarpMode(category);

  return {
    x_percent: pos.x_pct,
    y_percent: pos.y_pct,
    width_percent: widthPct,
    height_percent: heightPct,
    opacity: 0.95,
    blend_mode: "normal",
    rotation: 0,
    warp,
    warp_intensity: warp !== "none" ? 50 : 0,
  };
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function proxyUrl(src: string): string {
  // External URLs need to go through our proxy to avoid CORS issues
  if (src.startsWith("http") && !src.includes(window.location.host)) {
    return `${API}/brand-kit/image-proxy?url=${encodeURIComponent(src)}`;
  }
  return src;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = proxyUrl(src);
  });
}

export async function generateMockup(
  canvas: HTMLCanvasElement,
  productImageUrl: string,
  logoUrl: string,
  config: MockupConfig,
  scale = 1
): Promise<string> {
  const productImg = await loadImage(productImageUrl);

  const w = productImg.naturalWidth * scale;
  const h = productImg.naturalHeight * scale;
  canvas.width = w;
  canvas.height = h;

  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, w, h);

  // Draw product image
  ctx.drawImage(productImg, 0, 0, w, h);

  // Load and draw logo
  const logoImg = await loadImage(logoUrl);

  const logoW = (config.width_percent / 100) * w;
  const logoH = (config.height_percent / 100) * h;

  // Maintain logo aspect ratio
  const logoAspect = logoImg.naturalWidth / logoImg.naturalHeight;
  let drawW = logoW;
  let drawH = logoW / logoAspect;
  if (drawH > logoH) {
    drawH = logoH;
    drawW = logoH * logoAspect;
  }

  const drawX = (config.x_percent / 100) * w;
  const drawY = (config.y_percent / 100) * h;

  // Subtle drop shadow
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.2)";
  ctx.shadowBlur = 4 * scale;
  ctx.shadowOffsetX = 2 * scale;
  ctx.shadowOffsetY = 2 * scale;
  ctx.globalAlpha = config.opacity;
  ctx.globalCompositeOperation = config.blend_mode as GlobalCompositeOperation;

  const rotation = config.rotation ?? 0;
  const warpMode = config.warp ?? "none";
  const warpIntensity = (config.warp_intensity ?? 0) / 100; // 0..1

  if (warpMode !== "none" && warpIntensity > 0) {
    // Warp rendering: slice logo into vertical strips and warp them
    _drawWarpedLogo(ctx, logoImg, drawX, drawY, drawW, drawH, rotation, warpMode, warpIntensity);
  } else if (rotation !== 0) {
    const cx = drawX + drawW / 2;
    const cy = drawY + drawH / 2;
    ctx.translate(cx, cy);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.drawImage(logoImg, -drawW / 2, -drawH / 2, drawW, drawH);
  } else {
    ctx.drawImage(logoImg, drawX, drawY, drawW, drawH);
  }
  ctx.restore();

  return canvas.toDataURL("image/png");
}

/**
 * Draw logo warped onto a curved surface.
 *
 * "cylinder" — horizontal curvature (bottles, mugs, pens).
 *   Strips at centre are full-width; strips at edges shrink via cos().
 *   Slight vertical pinch at edges simulates perspective.
 *
 * "arc" — logo follows a downward arc (caps, hats).
 *   Each strip is shifted vertically along a parabola and rotated tangent.
 */
function _drawWarpedLogo(
  ctx: CanvasRenderingContext2D,
  logo: HTMLImageElement,
  x: number,
  y: number,
  w: number,
  h: number,
  rotation: number,
  mode: "cylinder" | "arc",
  intensity: number, // 0..1
) {
  const SLICES = 48;
  const srcW = logo.naturalWidth;
  const srcH = logo.naturalHeight;
  const sliceW = srcW / SLICES;

  // Apply rotation around center of the logo area
  const cx = x + w / 2;
  const cy = y + h / 2;
  if (rotation !== 0) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.translate(-cx, -cy);
  }

  // Disable shadow for individual slices (was already set on parent)
  // to avoid compounding shadow per strip
  ctx.shadowColor = "transparent";

  for (let i = 0; i < SLICES; i++) {
    // t goes from -1 (left edge) to +1 (right edge)
    const t = ((i + 0.5) / SLICES) * 2 - 1;

    const srcX = i * sliceW;
    // destination strip width on canvas
    const destSliceW = w / SLICES;
    let destX = x + i * destSliceW;
    let destY = y;
    let destW = destSliceW + 0.5; // +0.5 to avoid sub-pixel gaps
    let destH = h;

    if (mode === "cylinder") {
      // Cylinder wrap: edges shrink horizontally & vertically
      const cosT = Math.cos((t * Math.PI) / 2); // 1 at center, 0 at edges
      const squeeze = 1 - intensity * (1 - cosT); // 1 → squeeze factor

      // Horizontal: compress strips at edges toward center
      const offset = (destSliceW - destSliceW * squeeze) / 2;
      destX += offset;
      destW = destSliceW * squeeze + 0.5;

      // Vertical: slight height reduction at edges (perspective)
      const heightScale = 1 - intensity * 0.15 * (1 - cosT);
      const newH = destH * heightScale;
      destY += (destH - newH) / 2;
      destH = newH;
    } else {
      // Arc warp: strips follow a downward parabola
      const arcDepth = intensity * h * 0.35; // max vertical displacement
      const yOffset = arcDepth * t * t; // parabola: 0 at center, max at edges
      destY += yOffset;

      // Slight rotation of each strip tangent to the arc
      const tangentAngle = intensity * 0.3 * t; // radians at edges

      if (Math.abs(tangentAngle) > 0.001) {
        ctx.save();
        const stripCx = destX + destW / 2;
        const stripCy = destY + destH / 2;
        ctx.translate(stripCx, stripCy);
        ctx.rotate(tangentAngle);
        ctx.drawImage(
          logo,
          srcX, 0, sliceW, srcH,
          -destW / 2, -destH / 2, destW, destH,
        );
        ctx.restore();
        continue;
      }
    }

    ctx.drawImage(
      logo,
      srcX, 0, sliceW, srcH,
      destX, destY, destW, destH,
    );
  }

  if (rotation !== 0) {
    ctx.restore();
  }
}
