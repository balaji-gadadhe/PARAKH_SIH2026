/**
 * lib/theme.ts — hex mirrors of the CSS tokens in globals.css.
 * Needed because chart libraries (Recharts) set SVG fill attributes
 * where CSS custom properties are not always resolved.
 * Keep values in sync with app/globals.css ROOT tokens (D-023 theme).
 * Charts are used on D-023-scope pages; saffron-scope pages hardcode their
 * own shades where needed.
 */

import type { RiskTier } from "./api";

export const TIER_HEX: Record<RiskTier, string> = {
  LOW: "#2D7D54",
  MEDIUM: "#D78A22",
  HIGH: "#C24C22",
  CRITICAL: "#A92727",
};

export const TIER_BG_HEX: Record<RiskTier, string> = {
  LOW: "#ECFDF5",
  MEDIUM: "#FFFBEB",
  HIGH: "#FFF7ED",
  CRITICAL: "#FEF2F2",
};

export const PRIMARY_HEX = "#0C4A34";
export const ACCENT_HEX = "#D97706";
export const BORDER_HEX = "#E5E2D8";
export const SURFACE_2_HEX = "#F1EFEA";
export const MUTED_HEX = "#6E6B64";

/** Fixed tier order for legends/tables. */
export const TIER_ORDER: RiskTier[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

/** Human tier label for tooltips/details. */
export const TIER_LABELS: Record<RiskTier, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
};

/** Pick a hex for any tier-ish string (defaults to MEDIUM). */
export function tierHex(tier: string): string {
  return TIER_HEX[(tier as RiskTier) in TIER_HEX ? (tier as RiskTier) : "MEDIUM"];
}
