import { createContext, useContext } from "react";

// Neutral wording shown until the server says which company it is writing for (and if it cannot be reached).
export const DEFAULT_PROFILE = {
  name: "Content Studio",
  audience: "readers",
  subject: "the company",
  brand_check_label: "Brand and audience sensitivity",
  tagline: "Write content you can trust",
  placeholder: "Describe what you want written",
  examples: [],
};

export const ProfileContext = createContext(DEFAULT_PROFILE);
export const useProfile = () => useContext(ProfileContext);

/** The company from /health, merged over the neutral defaults. */
export function profileFromHealth(health) {
  const company = health && health !== "offline" ? health.company : null;
  return { ...DEFAULT_PROFILE, ...(company || {}) };
}

export const capitalise = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);
