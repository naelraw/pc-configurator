import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { C, FONT, H, MONO, W } from "./theme";
import { Coche, Fond, LogoR, MotQuiTombe, ressort, useFondu } from "./ui";
import { Camera, Lumieres, PcComplet, Sol, CarteGraphique, Processeur, Memoire, Alimentation, CarteMere } from "./three/Pc";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Zone utile TikTok : rien d'important sous 1500 px (légende) ni à droite (boutons).
const MARGE = 90;

const Titre: React.FC<{ children: React.ReactNode; taille?: number; couleur?: string }> = ({ children, taille = 118, couleur = C.text }) => (
  <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: taille, lineHeight: 1.02, letterSpacing: "-0.035em", color: couleur }}>
    {children}
  </div>
);

// ---------------------------------------------------------------------------
// 1. Accroche : le PC tourne, « Monter son PC, sans te tromper. »
// ---------------------------------------------------------------------------
export const Accroche: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 1, 5);
  const entree = ressort(frame, fps, 0, 90, 16);
  const angle = 0.55 + frame * 0.014;
  const r = 15.5 - entree * 2;
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond />
      <ThreeCanvas width={W} height={H}>
        <Camera position={[r * Math.sin(angle), 2.4, r * Math.cos(angle)]} cible={[0, 0.6, 0]} fov={45} />
        <Lumieres />
        <group scale={0.75 + entree * 0.25} position={[0, -0.6, 0]}>
          <PcComplet tour={frame * 0.32} />
          <Sol />
        </group>
      </ThreeCanvas>
      <AbsoluteFill style={{ padding: `240px ${MARGE}px 0` }}>
        <MotQuiTombe debut={4}>
          <Titre>Monter son PC,</Titre>
        </MotQuiTombe>
        <MotQuiTombe debut={16}>
          <Titre couleur={C.accent}>sans te tromper.</Titre>
        </MotQuiTombe>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 2. Le problème : pièces en désordre, « INCOMPATIBLE »
// ---------------------------------------------------------------------------
export const Probleme: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 4, 5);
  const tampon = ressort(frame, fps, 52, 260, 12);
  const rouge = interpolate(frame, [52, 62], [0, 1], clamp);
  const secousse = frame >= 52 && frame < 64 ? Math.sin(frame * 3.1) * (64 - frame) * 1.6 : 0;
  const flotte = (k: number) => 0.45 + 0.04 * Math.sin(frame * 0.09 + k);
  const pivot = frame * 0.012;
  return (
    <AbsoluteFill style={{ opacity: fondu, transform: `translateX(${secousse}px)` }}>
      <Fond teinte={rouge > 0.5 ? C.danger : C.accent} />
      <ThreeCanvas width={W} height={H}>
        <Camera position={[0, 2.4, 15]} cible={[0, 2.1, 0]} fov={45} />
        <Lumieres alerte={rouge} />
        <group position={[-0.9, 0, 0]} rotation={[0.15, 0.5 + pivot, 0]}>
          <CarteMere ecart={flotte(0)} />
          <Processeur ecart={flotte(1)} rouge={rouge} tour={frame * 0.2} />
          <Memoire ecart={flotte(2)} rouge={rouge} />
          <CarteGraphique ecart={flotte(3)} rouge={rouge} tour={frame * 0.2} />
          <Alimentation ecart={flotte(4)} rouge={rouge} />
        </group>
      </ThreeCanvas>
      <AbsoluteFill style={{ padding: `240px ${MARGE}px 0`, gap: 6 }}>
        <MotQuiTombe debut={6}><Titre taille={104}>Socket.</Titre></MotQuiTombe>
        <MotQuiTombe debut={18}><Titre taille={104}>Alimentation.</Titre></MotQuiTombe>
        <MotQuiTombe debut={30}><Titre taille={104}>Taille du GPU.</Titre></MotQuiTombe>
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", top: 1060 }}>
        <div
          style={{
            fontFamily: FONT, fontWeight: 700, fontSize: 112, letterSpacing: "0.04em", color: C.danger,
            border: `9px solid ${C.danger}`, borderRadius: 22, padding: "10px 36px", background: "rgba(14,15,17,0.72)",
            transform: `rotate(-7deg) scale(${2.2 - 1.2 * tampon})`, opacity: Math.min(1, tampon * 2),
          }}
        >
          INCOMPATIBLE
        </div>
        <MotQuiTombe debut={70} style={{ marginTop: 70 }}>
          <div style={{ fontFamily: FONT, fontWeight: 600, fontSize: 54, color: C.text2, textAlign: "center" }}>
            Une erreur, et tout repart en retour.
          </div>
        </MotQuiTombe>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 3. La solution : radar qui balaie, logo PC Radar
// ---------------------------------------------------------------------------
export const Solution: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 3, 6);
  const logo = ressort(frame, fps, 10, 120, 12);
  const balayage = frame * 6;
  const cercles = interpolate(frame, [0, 22], [0, 1], clamp);
  const blips = [
    [0.32, -0.22, 26], [-0.38, 0.12, 38], [0.1, 0.41, 50], [-0.18, -0.42, 60], [0.44, 0.24, 70],
  ] as const;
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={1.3} />
      <AbsoluteFill style={{ alignItems: "center", top: 330 }}>
        <div style={{ position: "relative", width: 820, height: 820 }}>
          {[1, 0.74, 0.48, 0.22].map((s, i) => (
            <div key={i} style={{
              position: "absolute", inset: `${(1 - s) * 50}%`, borderRadius: "50%",
              border: `2px solid ${C.accentLine}`, opacity: cercles * (0.9 - i * 0.12),
              transform: `scale(${0.6 + 0.4 * cercles})`,
            }} />
          ))}
          <div style={{
            position: "absolute", inset: 0, borderRadius: "50%", opacity: cercles,
            background: `conic-gradient(from ${balayage}deg, ${C.accent}88 0deg, ${C.accent}00 70deg, transparent 360deg)`,
            maskImage: "radial-gradient(circle, black 69%, transparent 70%)",
          }} />
          {blips.map(([x, y, debut], i) => {
            const p = ressort(frame, fps, debut, 200, 10);
            return (
              <div key={i} style={{
                position: "absolute", left: `${50 + x * 100}%`, top: `${50 + y * 100}%`, width: 22, height: 22,
                marginLeft: -11, marginTop: -11, borderRadius: "50%", background: C.accent,
                boxShadow: `0 0 ${24 * p}px ${C.accent}`, transform: `scale(${p})`,
                opacity: interpolate(frame, [debut + 25, debut + 45], [1, 0.35], clamp),
              }} />
            );
          })}
          <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
            <div style={{ transform: `scale(${logo})`, filter: `drop-shadow(0 30px 60px rgba(0,0,0,0.6))` }}>
              <LogoR taille={300} point={0.6 + 0.4 * Math.abs(Math.sin(frame * 0.12))} />
            </div>
          </AbsoluteFill>
        </div>
        <MotQuiTombe debut={28} style={{ marginTop: 60 }}>
          <Titre taille={128}>PC Radar</Titre>
        </MotQuiTombe>
        <MotQuiTombe debut={42} style={{ marginTop: 18 }}>
          <div style={{ fontFamily: FONT, fontWeight: 600, fontSize: 56, color: C.text2, textAlign: "center", maxWidth: 860 }}>
            vérifie <span style={{ color: C.accent }}>tout</span> à ta place.
          </div>
        </MotQuiTombe>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 4. Assemblage 3D : les pièces s'emboîtent, coches, « 100 % compatible »
// ---------------------------------------------------------------------------
const ETAPES = [
  { cle: "cm", nom: "Carte mère", debut: 6 },
  { cle: "alim", nom: "Alimentation", debut: 22 },
  { cle: "cpu", nom: "Processeur", debut: 38 },
  { cle: "ram", nom: "Mémoire", debut: 54 },
  { cle: "gpu", nom: "Carte graphique", debut: 70 },
] as const;

export const Assemblage: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 4, 6);
  const arrivee = (debut: number) => ressort(frame, fps, debut, 110, 16);
  const ecarts = Object.fromEntries(ETAPES.map((e) => [e.cle, 1 - arrivee(e.debut)]));
  const angle = 1.3 - frame * 0.0035;
  const badge = ressort(frame, fps, 100, 170, 12);
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.8 + 0.6 * badge} />
      <ThreeCanvas width={W} height={H}>
        <Camera position={[14 * Math.sin(angle), 2.6, 14 * Math.cos(angle)]} cible={[0, 0, 0]} fov={45} />
        <Lumieres />
        <group position={[0, -1.2, 0]}>
          <PcComplet tour={frame * 0.3} ecarts={ecarts} />
          <Sol />
        </group>
      </ThreeCanvas>
      <AbsoluteFill style={{ padding: `230px ${MARGE}px 0`, gap: 18 }}>
        {ETAPES.map((e) => {
          const p = arrivee(e.debut + 10);
          return (
            <div key={e.cle} style={{ display: "flex", alignItems: "center", gap: 22, opacity: Math.min(1, p * 1.5), transform: `translateX(${(1 - p) * -60}px)` }}>
              <Coche taille={62} progres={Math.min(1, p)} />
              <span style={{ fontFamily: FONT, fontWeight: 600, fontSize: 54, color: C.text }}>{e.nom}</span>
            </div>
          );
        })}
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", top: 1400 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 20, padding: "22px 40px", borderRadius: 999,
          background: C.accent, color: "#05140d", fontFamily: FONT, fontWeight: 700, fontSize: 64,
          transform: `scale(${badge})`, boxShadow: `0 0 ${80 * badge}px ${C.accent}66`,
        }}>
          100 % compatible
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 5. Atouts : cartes qui arrivent une à une, exemple réel chiffré
// ---------------------------------------------------------------------------
const ATOUTS = [
  { titre: "Assistant IA", texte: "Décris ton besoin, il monte la config." },
  { titre: "Prix relevés chaque jour", texte: "Près de 1 000 composants suivis sur Amazon." },
  { titre: "Alerte dès que ça baisse", texte: "Un e-mail quand le prix chute." },
  { titre: "Tes FPS avant d'acheter", texte: "Fortnite, Warzone, Cyberpunk…" },
];

const Icone: React.FC<{ i: number }> = ({ i }) => {
  const trace = [
    <path key="ia" d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z M18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z" />,
    <path key="prix" d="M4 17l5-5 4 4 7-8 M15 8h5v5" fill="none" />,
    <path key="cloche" d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z M10 20a2 2 0 0 0 4 0" fill="none" />,
    <path key="fps" d="M3 14a9 9 0 0 1 18 0 M12 14l4-4 M3 18h18" fill="none" />,
  ][i];
  return (
    <svg width="58" height="58" viewBox="0 0 24 24" fill={C.accent} stroke={C.accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {trace}
    </svg>
  );
};

export const Atouts: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 4, 6);
  const exemple = ressort(frame, fps, 72, 150, 14);
  const prix = Math.round(interpolate(frame, [76, 100], [0, 978], clamp));
  const ips = Math.round(interpolate(frame, [76, 100], [0, 110], clamp));
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.7} />
      <AbsoluteFill style={{ padding: `220px ${MARGE}px 0`, gap: 22 }}>
        {ATOUTS.map((a, i) => {
          const p = ressort(frame, fps, i * 13, 150, 15);
          return (
            <div key={a.titre} style={{
              display: "flex", alignItems: "center", gap: 30, padding: "30px 34px", borderRadius: 28,
              background: "rgba(20,21,23,0.92)", border: `2px solid ${C.line}`,
              boxShadow: "0 24px 60px -24px rgba(0,0,0,0.7)",
              transform: `translateX(${(1 - p) * 900}px) rotate(${(1 - p) * 4}deg)`, opacity: Math.min(1, p * 1.3),
            }}>
              <div style={{ flexShrink: 0, width: 96, height: 96, borderRadius: 24, display: "grid", placeItems: "center", background: C.accentSoft, border: `2px solid ${C.accentLine}` }}>
                <Icone i={i} />
              </div>
              <div>
                <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: 52, color: C.text, letterSpacing: "-0.02em" }}>{a.titre}</div>
                <div style={{ fontFamily: FONT, fontWeight: 400, fontSize: 38, color: C.text2, marginTop: 6 }}>{a.texte}</div>
              </div>
            </div>
          );
        })}
        <div style={{
          marginTop: 26, padding: "30px 34px", borderRadius: 28, border: `2px solid ${C.accentLine}`, background: C.accentSoft,
          transform: `scale(${0.9 + 0.1 * exemple})`, opacity: exemple,
        }}>
          <div style={{ fontFamily: FONT, fontWeight: 600, fontSize: 36, color: C.text2 }}>Exemple réel : un PC pour Fortnite</div>
          <div style={{ display: "flex", gap: 50, marginTop: 10, alignItems: "baseline" }}>
            <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 92, color: C.text }}>{prix} €</span>
            <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 92, color: C.accent }}>~{ips} FPS</span>
          </div>
          <div style={{ fontFamily: FONT, fontSize: 32, color: C.text3, marginTop: 4 }}>en 1080p, toutes les pièces compatibles</div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 6. Appel à l'action : PC qui tourne, pcradar.tech, gratuit, lien en bio
// ---------------------------------------------------------------------------
export const AppelAction: React.FC<{ duree: number }> = ({ duree }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fondu = useFondu(duree, 4, 1);
  const url = ressort(frame, fps, 8, 140, 13);
  const pastille = ressort(frame, fps, 22, 200, 12);
  const fleche = Math.sin(frame * 0.25) * 14;
  const angle = 0.4 + frame * 0.02;
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={1.2} />
      <ThreeCanvas width={W} height={H}>
        <Camera position={[13 * Math.sin(angle), 1.6, 13 * Math.cos(angle)]} cible={[0, -2.9, 0]} fov={45} />
        <Lumieres />
        <group position={[0, -0.3, 0]} scale={0.7}>
          <PcComplet tour={frame * 0.35} />
          <Sol />
        </group>
      </ThreeCanvas>
      <AbsoluteFill style={{ alignItems: "center", top: 1090, gap: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 26, transform: `scale(${url})`, opacity: Math.min(1, url * 1.5) }}>
          <LogoR taille={120} />
          <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 104, color: C.text, letterSpacing: "-0.03em" }}>pcradar.tech</span>
        </div>
        <div style={{ display: "flex", gap: 18, transform: `scale(${pastille})` }}>
          <span style={{ padding: "14px 30px", borderRadius: 999, background: C.accent, color: "#05140d", fontFamily: FONT, fontWeight: 700, fontSize: 48 }}>Gratuit</span>
          <span style={{ padding: "14px 30px", borderRadius: 999, border: `2px solid ${C.lineStrong}`, color: C.text, fontFamily: FONT, fontWeight: 600, fontSize: 48 }}>Lien en bio</span>
        </div>
        <svg width="70" height="70" viewBox="0 0 24 24" style={{ transform: `translateY(${fleche}px)`, opacity: pastille }}>
          <path d="M12 4v14 M6 12l6 6 6-6" fill="none" stroke={C.accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
