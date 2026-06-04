export const UNIFIED_COLORS = {
  red: {
    label: "Roșu",
    hex: "#E74C3C",
    colorGroup: "Rosu",
  },
  yellow: {
    label: "Galben",
    hex: "#F1C40F",
    colorGroup: "Galben",
  },
  green: {
    label: "Verde",
    hex: "#27AE60",
    colorGroup: "Verde",
  },
  blue: {
    label: "Albastru",
    hex: "#2980B9",
    colorGroup: "Albastru",
  },
  navy: {
    label: "Bleumarin",
    hex: "#1B2A4A",
    colorGroup: "Bleumarin",
  },
  black: {
    label: "Negru",
    hex: "#2C3E50",
    colorGroup: "Negru",
  },
  white: {
    label: "Alb",
    hex: "#FFFFFF",
    colorGroup: "Alb",
  },
  orange: {
    label: "Portocaliu",
    hex: "#E67E22",
    colorGroup: "Portocaliu",
  },
  pink: {
    label: "Roz",
    hex: "#E91E8C",
    colorGroup: "Roz",
  },
  grey: {
    label: "Gri",
    hex: "#95A5A6",
    colorGroup: "Gri",
  },
  purple: {
    label: "Mov",
    hex: "#8E44AD",
    colorGroup: "Mov",
  },
  brown: {
    label: "Maro",
    hex: "#8B4513",
    colorGroup: "Maro",
  },
  turquoise: {
    label: "Turcoaz",
    hex: "#06B6D4",
    colorGroup: "Turcoaz",
  },
  burgundy: {
    label: "Bordo",
    hex: "#800020",
    colorGroup: "Bordo",
  },
  beige: {
    label: "Bej",
    hex: "#D4A574",
    colorGroup: "Bej",
  },
  gold: {
    label: "Auriu",
    hex: "#FFD700",
    colorGroup: "Auriu",
  },
  silver: {
    label: "Argintiu",
    hex: "#C0C0C0",
    colorGroup: "Argintiu",
  },
} as const;

export type UnifiedColorKey = keyof typeof UNIFIED_COLORS;

export const UNIFIED_COLOR_LIST = Object.entries(UNIFIED_COLORS).map(
  ([key, val]) => ({
    key: key as UnifiedColorKey,
    ...val,
  })
);
