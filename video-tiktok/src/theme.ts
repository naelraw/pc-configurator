import { continueRender, delayRender, staticFile } from "remotion";

// Couleurs et polices du site PC Radar (DESIGN.md).
export const C = {
  bg: "#0e0f11",
  surface: "#141517",
  surface2: "#1a1b1e",
  line: "#26272b",
  lineStrong: "#35363c",
  text: "#ececee",
  text2: "#a3a3ab",
  text3: "#81828a",
  accent: "#3ecf8e",
  accentSoft: "rgba(62,207,142,0.12)",
  accentLine: "rgba(62,207,142,0.38)",
  danger: "#f07171",
};

export const FPS = 30;
export const W = 1080;
export const H = 1920;

export const FONT = "Geist, sans-serif";
export const MONO = "'Geist Mono', monospace";

// Polices locales chargées avant le premier rendu.
const polices: [string, string, string][] = [
  ["Geist", "Geist-Regular.ttf", "400"],
  ["Geist", "Geist-SemiBold.ttf", "600"],
  ["Geist", "Geist-Bold.ttf", "700"],
  ["Geist Mono", "GeistMono-Medium.ttf", "500"],
];
if (typeof document !== "undefined") {
  const attente = delayRender("Chargement des polices");
  Promise.all(
    polices.map(([famille, fichier, poids]) => {
      const face = new FontFace(famille, `url(${staticFile(fichier)})`, { weight: poids });
      return face.load().then((f) => document.fonts.add(f));
    })
  ).then(() => continueRender(attente));
}
