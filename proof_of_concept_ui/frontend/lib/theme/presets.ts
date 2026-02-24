export const DEFAULT_THEME_ID = "ice-mint";

export type ThemePreset = {
  id: string;
  name: string;
  blurb: string;
};

export const THEME_PRESETS: ThemePreset[] = [
  { id: "cinematic-utility", name: "Cinematic Utility", blurb: "Deep navy gradients with mint accents." },
  { id: "arctic-signal", name: "Arctic Signal", blurb: "Cold glass panels and electric cyan cues." },
  { id: "sunset-terminal", name: "Sunset Terminal", blurb: "Burnt orange highlights on dusk surfaces." },
  { id: "forest-console", name: "Forest Console", blurb: "Pine and moss tones for focused browsing." },
  { id: "midnight-gold", name: "Midnight Gold", blurb: "Dark slate base with confident gold edges." },
  { id: "ocean-deck", name: "Ocean Deck", blurb: "Blue steel cards with bright aqua actions." },
  { id: "ember-industrial", name: "Ember Industrial", blurb: "Graphite textures and hot ember actions." },
  { id: "ice-mint", name: "Ice Mint", blurb: "Icy neutral backdrop with fresh mint focus." },
  { id: "clay-workbench", name: "Clay Workbench", blurb: "Warm clay and sand tones for long sessions." },
  { id: "ultra-contrast", name: "Ultra Contrast", blurb: "Accessibility-first black and white high contrast." }
];
