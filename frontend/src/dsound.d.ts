// Harmonia-UI-Sounds (/ds/sounds.js, in index.html geladen)
interface Window {
  dsSound?: { mountToggle(parent: HTMLElement): void; play(name: "click" | "hover" | "error" | "success"): void };
}
