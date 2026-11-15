import {
  Sprout,
  Drama,
  Cog,
  Wrench,
  BrainCircuit,
  Search,
  Target,
  Lightbulb,
  ShieldAlert,
  Compass,
  BookMarked,
  Zap,
  Puzzle,
  CloudFog,
  Sparkles,
  Fingerprint,
  Gauge,
} from 'lucide-react'

/**
 * نمادهای موتور فهم‌سنجی — همه از lucide و **تأییدشده**.
 *
 * درسِ گرفته‌شده: نسخهٔ نصب‌شدهٔ lucide-react (۰.۴۴۵) نامِ `Brain` را ندارد
 * (جایش `BrainCircuit` است). ایمپورتِ نامِ ناموجود، خطا نمی‌دهد بلکه
 * `undefined` می‌شود و React آن را به‌صورتِ یک مستطیلِ سفیدِ خالی رندر
 * می‌کند — بدونِ هیچ هشداری در کنسول. پس هر نماد این‌جا فقط از نام‌هایی
 * است که واقعاً وجود دارند.
 */
export const STAGE_ICONS = {
  philosophy: Sprout,
  mask_mcq: Drama,
  perturbation: Cog,
  debugging: Wrench,
  feynman_synthesis: BrainCircuit,
}

export const FINDING_ICONS = {
  CONTRADICTION: Zap,
  JARGON_VIOLATION: BookMarked,
  BLUFF_DETECTED: Drama,
  SLIP_RESOLVED: Wrench,
  SYNERGY: Sparkles,
}

export const PERSONA_ICONS = {
  MASTERED: Gauge,
  ILLUSION_OF_COMPETENCE: Drama,
  JARGON_DEPENDENT: BookMarked,
  PARTIAL_FRAGMENTED: Puzzle,
  UNSTRUCTURED: CloudFog,
}

export const UI_ICONS = {
  brain: BrainCircuit,
  search: Search,
  target: Target,
  lightbulb: Lightbulb,
  alert: ShieldAlert,
  compass: Compass,
  fingerprint: Fingerprint,
  sparkles: Sparkles,
}
