import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "./theme";

export const ressort = (frame: number, fps: number, debut: number, raideur = 140, amorti = 15) =>
  spring({ frame: frame - debut, fps, config: { stiffness: raideur, damping: amorti } });

// Fond commun : dégradé anthracite, halo émeraude et grille qui défile lentement.
export const Fond: React.FC<{ halo?: number; teinte?: string }> = ({ halo = 1, teinte = C.accent }) => {
  const frame = useCurrentFrame();
  const decale = (frame * 0.6) % 80;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(120% 70% at 50% 62%, #16181c 0%, ${C.bg} 60%, #08090b 100%)` }}>
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
          backgroundPosition: `0 ${decale}px`,
          opacity: 0.35,
          maskImage: "radial-gradient(70% 55% at 50% 55%, black 0%, transparent 80%)",
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(45% 28% at 50% 58%, ${teinte}33 0%, transparent 70%)`,
          opacity: halo,
        }}
      />
    </AbsoluteFill>
  );
};

// Fondu d'entrée et de sortie d'un plan (en images).
export const useFondu = (duree: number, entree = 6, sortie = 6) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [0, entree, duree - sortie, duree], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

// Logo PC Radar : R + point émeraude (mêmes tracés que le favicon du site).
export const LogoR: React.FC<{ taille: number; point?: number; fond?: boolean }> = ({ taille, point = 1, fond = true }) => (
  <svg width={taille} height={taille} viewBox="0 0 64 64">
    {fond && <rect width="64" height="64" rx="15" fill={C.surface} stroke={C.lineStrong} strokeWidth="1.5" />}
    <path d="M21 50.5V16.5h12.5a9.5 9.5 0 0 1 0 19H21" fill="none" stroke={C.text} strokeWidth="7" />
    <path d="M28.86 37.79L34.15 33.21L49.13 50.5L39.87 50.5Z" fill={C.text} />
    <circle cx="50" cy="13" r={4.5 * point} fill={C.accent} />
  </svg>
);

export const Coche: React.FC<{ taille: number; progres: number; couleur?: string }> = ({ taille, progres, couleur = C.accent }) => (
  <svg width={taille} height={taille} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="11" fill={couleur} opacity={0.16 * progres} />
    <circle cx="12" cy="12" r="11" fill="none" stroke={couleur} strokeWidth="1.6" opacity={progres} />
    <path
      d="M7 12.5l3.2 3.2L17 9"
      fill="none"
      stroke={couleur}
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="16"
      strokeDashoffset={16 * (1 - progres)}
    />
  </svg>
);

// Mot qui « tombe » à sa place avec un léger rebond.
export const MotQuiTombe: React.FC<{ debut: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  debut,
  children,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = ressort(frame, fps, debut, 180, 13);
  return (
    <div
      style={{
        fontFamily: FONT,
        transform: `translateY(${(1 - p) * 70}px) scale(${0.85 + 0.15 * p})`,
        opacity: Math.min(1, p * 1.4),
        filter: `blur(${(1 - Math.min(1, p)) * 10}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
