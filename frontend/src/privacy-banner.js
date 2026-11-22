// Privacy notice shown above the main section. Text must match the backend exactly.
const PRIVACY_TEXT = {
  en: "Please do not share Aadhaar, PAN, Voter ID, ration card or bank account numbers. We hide them automatically.",
  te: "దయచేసి ఆధార్, పాన్, ఓటర్ ఐడీ, రేషన్ కార్డు లేదా బ్యాంక్ ఖాతా నంబర్లను పంచుకోవద్దు. మేము వాటిని స్వయంచాలకంగా దాచిపెడతాము.",
};

// Returns a notice element for the given language ("en" or "te").
export function renderPrivacyBanner(lang) {
  const node = document.createElement("div");
  node.className = "privacy-banner";
  node.setAttribute("role", "note");
  node.setAttribute("aria-live", "polite");
  node.textContent = lang === "en" ? PRIVACY_TEXT.en : PRIVACY_TEXT.te;
  return node;
}
