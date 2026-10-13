import React from "react";
import { AbsoluteFill, Audio, Sequence, Series, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { C, FONT, H, MONO, W } from "../theme";
import { Coche, Fond, LogoR, ressort } from "../ui";
import voix from "../voix.json";
import { CameraFixe, Eclairage, Effets, SolStudio, Studio } from "../three/Realiste";
import { Modele } from "../three/Modeles";

// ---------------------------------------------------------------------------
// Vidéo promo PC Radar : 8 plans calés sur la voix off (src/voix.json).
// La voix démarre à DECALAGE images dans chaque plan ; t(s) = image où le mot
// prononcé à s secondes tombe.
// ---------------------------------------------------------------------------
const DECALAGE = 6;
const t = (s: number) => DECALAGE + Math.round(s * 30);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const MARGE = 80;
type Plan = { fichier: string; texte: string; mots: { mot: string; debut: number; fin: number }[]; fin_voix: number };
const PLANS = voix as Plan[];
export const dureePlan = (i: number) => DECALAGE + Math.ceil((PLANS[i].fin_voix + 0.75) * 30);
const moment = (i: number, mot: string) => {
  const m = PLANS[i].mots.find((x) => x.mot.toLowerCase().startsWith(mot.toLowerCase()));
  return m ? t(m.debut) : 0;
};

// ---------------------------------------------------------------------------
// Sous-titres mot à mot (3 mots à la fois, mot prononcé en vert)
// ---------------------------------------------------------------------------
const SousTitres: React.FC<{ i: number; haut?: number }> = ({ i, haut = 1360 }) => {
  const frame = useCurrentFrame();
  const s = (frame - DECALAGE) / 30;
  const mots = PLANS[i].mots;
  const groupes: (typeof mots)[] = [];
  mots.forEach((m, k) => {
    const g = groupes[groupes.length - 1];
    const finPhrase = k > 0 && /[.?!:]$/.test(PLANS[i].texte.split(/\s+/)[k - 1] || "");
    if (!g || g.length >= 3 || finPhrase) groupes.push([m]);
    else g.push(m);
  });
  const g = groupes.find((x, k) => s < (groupes[k + 1]?.[0].debut ?? Infinity) && s >= x[0].debut - 0.05);
  if (!g || s > PLANS[i].fin_voix + 0.3) return null;
  const entree = Math.min(1, (s - g[0].debut + 0.05) * 9);
  return (
    <AbsoluteFill style={{ top: haut, height: 170, alignItems: "center" }}>
      <div style={{
        display: "flex", gap: 18, flexWrap: "wrap", justifyContent: "center", maxWidth: 900,
        transform: `scale(${0.92 + 0.08 * entree})`, opacity: entree,
      }}>
        {g.map((m) => {
          const actif = s >= m.debut && s < m.fin + 0.12;
          return (
            <span key={m.debut} style={{
              fontFamily: FONT, fontWeight: 700, fontSize: 70, letterSpacing: "-0.02em",
              color: actif ? C.accent : C.text,
              textShadow: "0 4px 18px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.9)",
              transform: `translateY(${actif ? -4 : 0}px)`,
            }}>{m.mot}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// Étiquette de fonctionnalité en haut de l'écran.
const Etiquette: React.FC<{ texte: string; debut?: number }> = ({ texte, debut = 2 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = ressort(frame, fps, debut, 160, 15);
  return (
    <AbsoluteFill style={{ top: 210, alignItems: "center", height: 100 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 14, padding: "14px 28px", borderRadius: 999,
        background: "rgba(20,21,23,0.85)", border: `2px solid ${C.accentLine}`,
        fontFamily: MONO, fontWeight: 500, fontSize: 34, letterSpacing: "0.12em", color: C.accent,
        transform: `translateY(${(1 - p) * -40}px)`, opacity: p,
      }}>
        <span style={{ width: 14, height: 14, borderRadius: 7, background: C.accent, boxShadow: `0 0 14px ${C.accent}` }} />
        {texte}
      </div>
    </AbsoluteFill>
  );
};

const Voix: React.FC<{ i: number }> = ({ i }) => (
  <Sequence from={DECALAGE}>
    <Audio src={staticFile(PLANS[i].fichier)} />
  </Sequence>
);

const useFondu = (duree: number, entree = 5, sortie = 5) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [0, entree, duree - sortie, duree], [0, 1, 1, 0], clamp);
};

// ---------------------------------------------------------------------------
// 1. Accroche : gros plan sur une carte graphique, flou de profondeur
// ---------------------------------------------------------------------------
const P1: React.FC = () => {
  const frame = useCurrentFrame();
  const d = dureePlan(0);
  const fondu = useFondu(d, 1, 4);
  const k = frame / d;
  const erreur = moment(0, "erreur");
  const alerte = interpolate(frame, [erreur - 8, erreur, erreur + 20], [0, 1, 0.35], clamp);
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.5} />
      <ThreeCanvas width={W} height={H}>
        <Studio />
        <Eclairage alerte={alerte} />
        <CameraFixe position={[1.8 - 1.4 * k, 1.4 - 1.6 * k, 8.4 - 1.2 * k]} cible={[0, 0.5 - 1.2 * k, 0]} fov={34} />
        <group rotation={[0.15, -0.5 + 0.25 * k, 0.05]}>
          <Modele nom="gpu" taille={5.2} rouge={alerte * 0.5} temps={frame / 30} />
        </group>
        <Effets flou={{ cible: [0, 0.6 - 1.5 * k, 0.4], force: 2 }} />
      </ThreeCanvas>
      <SousTitres i={0} />
      <Voix i={0} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 2. Le problème : trois pièces, chacune passe au rouge sur sa phrase
// ---------------------------------------------------------------------------
const Alerte: React.FC<{ debut: number; haut: number; titre: string; detail: string }> = ({ debut, haut, titre, detail }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = ressort(frame, fps, debut, 220, 13);
  return (
    <div style={{
      position: "absolute", left: MARGE, top: haut - 60, maxWidth: 470,
      transform: `translateX(${(1 - p) * -80}px) scale(${0.9 + 0.1 * p})`, opacity: Math.min(1, p * 1.4),
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <svg width="46" height="46" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="11" fill={C.danger} opacity="0.18" />
          <circle cx="12" cy="12" r="11" fill="none" stroke={C.danger} strokeWidth="1.8" />
          <path d="M8 8l8 8M16 8l-8 8" stroke={C.danger} strokeWidth="2.4" strokeLinecap="round" />
        </svg>
        <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 46, color: C.danger, letterSpacing: "-0.01em" }}>{titre}</span>
      </div>
      <div style={{ fontFamily: FONT, fontSize: 32, color: C.text2, marginTop: 6, marginLeft: 60 }}>{detail}</div>
    </div>
  );
};

const P2: React.FC = () => {
  const frame = useCurrentFrame();
  const d = dureePlan(1);
  const fondu = useFondu(d);
  const [a, b, c] = [moment(1, "socket"), moment(1, "faible"), moment(1, "boîtier")];
  const rouge = (debut: number) => interpolate(frame, [debut - 4, debut + 6], [0, 1], clamp);
  const flotte = (k: number) => Math.sin(frame * 0.05 + k) * 0.06;
  const derive = frame * 0.004;
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.5} teinte={frame > a ? C.danger : C.accent} />
      <ThreeCanvas width={W} height={H}>
        <Studio />
        <Eclairage alerte={0.4 * rouge(a) + 0.3 * rouge(c)} accent={0.6} />
        <CameraFixe position={[-0.6, 0.6, 14]} cible={[0.2, 0.4, 0]} fov={40} />
        <group position={[1.5, 2.85 + flotte(0), 0]} rotation={[0.25, -0.6 + derive, 0]}>
          <Modele nom="ventirad" taille={1.9} rouge={rouge(a)} luminosite={0.35} />
        </group>
        <group position={[1.45, 0.75 + flotte(1), 0]} rotation={[0.35, 0.6 + derive, 0]}>
          <Modele nom="alim" taille={1.9} rouge={rouge(b)} />
        </group>
        <group position={[1.4, -1.35 + flotte(2), 0]} rotation={[0.2, Math.PI / 2 - 0.5 + derive, Math.PI / 2]}>
          <Modele nom="gpu" taille={3.5} rouge={rouge(c)} temps={frame / 30} />
        </group>
        <Effets />
      </ThreeCanvas>
      <Alerte debut={a} haut={400} titre="Socket incompatible" detail="Le processeur ne rentre pas" />
      <Alerte debut={b} haut={770} titre="Alim trop faible" detail="Le PC s'éteint en jeu" />
      <Alerte debut={c} haut={1160} titre="GPU trop long" detail="Il ne rentre pas dans le boîtier" />
      <SousTitres i={1} haut={1390} />
      <Voix i={1} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 3. La solution : radar qui balaie, logo PC Radar
// ---------------------------------------------------------------------------
const P3: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const d = dureePlan(2);
  const fondu = useFondu(d, 3, 5);
  const logo = ressort(frame, fps, 3, 130, 12);
  const cercles = interpolate(frame, [0, 16], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={1.3} />
      <AbsoluteFill style={{ alignItems: "center", top: 300 }}>
        <div style={{ position: "relative", width: 860, height: 860 }}>
          {[1, 0.74, 0.48].map((s, i) => (
            <div key={i} style={{
              position: "absolute", inset: `${(1 - s) * 50}%`, borderRadius: "50%",
              border: `2px solid ${C.accentLine}`, opacity: cercles * (0.9 - i * 0.15), transform: `scale(${0.6 + 0.4 * cercles})`,
            }} />
          ))}
          <div style={{
            position: "absolute", inset: 0, borderRadius: "50%", opacity: cercles,
            background: `conic-gradient(from ${frame * 7}deg, ${C.accent}99 0deg, ${C.accent}00 75deg, transparent 360deg)`,
            maskImage: "radial-gradient(circle, black 69%, transparent 70%)",
          }} />
          {[[0.3, -0.25, 14], [-0.36, 0.14, 22], [0.12, 0.4, 30], [-0.2, -0.4, 38]].map(([x, y, debut], i) => {
            const p = ressort(frame, fps, debut, 220, 10);
            return (
              <div key={i} style={{
                position: "absolute", left: `${50 + x * 100}%`, top: `${50 + y * 100}%`, width: 24, height: 24, marginLeft: -12, marginTop: -12,
                borderRadius: "50%", background: C.accent, boxShadow: `0 0 ${26 * p}px ${C.accent}`, transform: `scale(${p})`,
              }} />
            );
          })}
          <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
            <div style={{ transform: `scale(${logo})`, filter: "drop-shadow(0 30px 60px rgba(0,0,0,0.6))" }}>
              <LogoR taille={330} point={0.6 + 0.4 * Math.abs(Math.sin(frame * 0.14))} />
            </div>
          </AbsoluteFill>
        </div>
      </AbsoluteFill>
      <SousTitres i={2} haut={1250} />
      <Voix i={2} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Téléphone 3D réaliste (plans 4 et 6)
// ---------------------------------------------------------------------------
const PlanTelephone: React.FC<{ ecran: string; de: number; a: number; d: number; rot?: [number, number] }> = ({ ecran, de, a, d, rot = [-0.42, 0.12] }) => {
  const frame = useCurrentFrame();
  const k = Math.min(1, frame / d);
  const lisse = k * k * (3 - 2 * k);
  return (
    <ThreeCanvas width={W} height={H}>
      <Studio intensite={1.3} />
      <Eclairage accent={0.7} />
      <CameraFixe position={[0, 0.2, 12.2]} cible={[0, -0.25, 0]} fov={38} />
      <group position={[-2.4, 2.4, -4]} rotation={[0.5, frame * 0.008, 0.3]}>
        <Modele nom="carteMere" taille={3.4} />
      </group>
      <group position={[2.6, -2.2, -3.5]} rotation={[0.3, -frame * 0.01, 0.9]}>
        <Modele nom="ram" taille={3} />
      </group>
      <group rotation={[0.06, Math.PI + rot[0] + (rot[1] - rot[0]) * lisse, 0.03 - 0.05 * lisse]} position={[0, -0.25 + Math.sin(frame * 0.05) * 0.05, 0]}>
        <Modele nom="telephone" taille={5.6} masquer={(n) => n.includes("Screen_Glass")}
          ecran={{ fichier: ecran, defilement: de + (a - de) * lisse }} />
      </group>
      <Effets ecran flou={{ cible: [0, 0, 0.2], force: 1.5 }} />
    </ThreeCanvas>
  );
};

const Pastille: React.FC<{ debut: number; x: number; y: number; children: React.ReactNode; couleur?: string }> = ({ debut, x, y, children, couleur = C.accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = ressort(frame, fps, debut, 200, 13);
  return (
    <div style={{
      position: "absolute", left: x, top: y, display: "flex", alignItems: "center", gap: 14,
      padding: "16px 26px", borderRadius: 22, background: "rgba(14,15,17,0.9)", border: `2px solid ${couleur}66`,
      boxShadow: `0 20px 50px -18px rgba(0,0,0,0.8), 0 0 30px -10px ${couleur}`,
      fontFamily: FONT, fontWeight: 700, fontSize: 40, color: C.text,
      transform: `scale(${p}) translateY(${(1 - p) * 30}px)`, opacity: Math.min(1, p * 1.3),
    }}>{children}</div>
  );
};

// 4. Configurateur
const P4: React.FC = () => {
  const d = dureePlan(3);
  const fondu = useFondu(d);
  const ctrl = moment(3, "contrôlée");
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.9} />
      <PlanTelephone ecran="ecrans/ecran2.jpg" de={0.02} a={0.36} d={d} />
      <Etiquette texte="CONFIGURATEUR" />
      <Pastille debut={ctrl} x={60} y={560}><Coche taille={44} progres={1} />Socket compatible</Pastille>
      <Pastille debut={ctrl + 7} x={600} y={760}><Coche taille={44} progres={1} />Alim suffisante</Pastille>
      <Pastille debut={ctrl + 14} x={90} y={980}><Coche taille={44} progres={1} />GPU : 228 mm, ça rentre</Pastille>
      <Pastille debut={moment(3, "total")} x={560} y={1170}>
        <span style={{ fontFamily: MONO, fontWeight: 500 }}>1 299,54 €</span>
        <span style={{ fontSize: 30, color: C.accent }}>au prix du jour</span>
      </Pastille>
      <SousTitres i={3} haut={1380} />
      <Voix i={3} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 5. Assistant IA : discussion animée dans un téléphone
// ---------------------------------------------------------------------------
const Bulle: React.FC<{ debut: number; moi?: boolean; children: React.ReactNode }> = ({ debut, moi, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = ressort(frame, fps, debut, 170, 15);
  if (frame < debut) return null;
  return (
    <div style={{
      alignSelf: moi ? "flex-end" : "flex-start", maxWidth: "86%", padding: "22px 26px", borderRadius: 28,
      borderBottomRightRadius: moi ? 8 : 28, borderBottomLeftRadius: moi ? 28 : 8,
      background: moi ? C.accent : C.surface2, color: moi ? "#05140d" : C.text, border: moi ? "none" : `2px solid ${C.line}`,
      fontFamily: FONT, fontSize: 34, lineHeight: 1.4, fontWeight: moi ? 600 : 400,
      transform: `translateY(${(1 - p) * 40}px) scale(${0.94 + 0.06 * p})`, opacity: Math.min(1, p * 1.3),
      transformOrigin: moi ? "right bottom" : "left bottom",
    }}>{children}</div>
  );
};

const P5: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const d = dureePlan(4);
  const fondu = useFondu(d);
  const question = "Un PC pour jouer à Fortnite, 1 000 € max";
  const debutQ = moment(4, "Décris");
  const tape = Math.floor(interpolate(frame, [debutQ, debutQ + 34], [0, question.length], clamp));
  const envoi = debutQ + 38;
  const reponse = moment(4, "propose");
  const ecrit = frame >= envoi + 6 && frame < reponse;
  const entree = ressort(frame, fps, 0, 90, 16);
  const tourne = interpolate(frame, [0, d], [-16, -8]);
  const lignes = [
    ["Carte graphique", "XFX Swift RX 9060 XT 8 Go"],
    ["Processeur", "AMD Ryzen 5 5600XT"],
  ];
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.8} />
      <Etiquette texte="ASSISTANT IA" />
      <AbsoluteFill style={{ alignItems: "center", top: 330, perspective: 2200 }}>
        <div style={{
          width: 760, height: 1000, borderRadius: 90, padding: 22, background: "linear-gradient(145deg,#4a4c52,#26272b)",
          boxShadow: "0 60px 120px -40px rgba(0,0,0,0.9), 0 0 0 2px #55575d inset",
          transform: `rotateY(${tourne}deg) rotateX(5deg) translateY(${(1 - entree) * 120}px)`, opacity: entree,
        }}>
          <div style={{ width: "100%", height: "100%", borderRadius: 70, background: C.bg, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "40px 36px 22px", borderBottom: `2px solid ${C.line}` }}>
              <LogoR taille={58} />
              <div>
                <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: 34, color: C.text }}>Assistant PC Radar</div>
                <div style={{ fontFamily: FONT, fontSize: 24, color: C.accent }}>en ligne</div>
              </div>
            </div>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 18, padding: 30, justifyContent: "flex-end" }}>
              <Bulle debut={envoi} moi>{question}</Bulle>
              {ecrit && (
                <div style={{ alignSelf: "flex-start", display: "flex", gap: 10, padding: "22px 26px", borderRadius: 28, background: C.surface2, border: `2px solid ${C.line}` }}>
                  {[0, 1, 2].map((k) => (
                    <span key={k} style={{ width: 14, height: 14, borderRadius: 7, background: C.accent, opacity: 0.4 + 0.6 * Math.abs(Math.sin((frame - k * 4) * 0.25)) }} />
                  ))}
                </div>
              )}
              <Bulle debut={reponse}>
                Voici une config construite autour de la <b>RX 9060 XT</b> et du <b>Ryzen 5 5600XT</b> : environ <b style={{ color: C.accent }}>110 FPS</b> en 1080p sur Fortnite.
                <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                  {lignes.map(([cat, nom], k) => {
                    const p = ressort(frame, fps, reponse + 10 + k * 6, 200, 14);
                    return (
                      <div key={cat} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 26, opacity: p, transform: `translateX(${(1 - p) * 20}px)` }}>
                        <span style={{ color: C.text3 }}>{cat}</span><span>{nom}</span>
                      </div>
                    );
                  })}
                  <div style={{
                    marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 18px", borderRadius: 16,
                    background: C.accentSoft, border: `2px solid ${C.accentLine}`, opacity: ressort(frame, fps, reponse + 24, 200, 14),
                  }}>
                    <span style={{ fontFamily: FONT, fontWeight: 600, fontSize: 28, color: C.text }}>Total, tout compatible</span>
                    <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 40, color: C.accent }}>978 €</span>
                  </div>
                </div>
              </Bulle>
            </div>
            <div style={{ margin: "0 26px 30px", padding: "22px 26px", borderRadius: 999, border: `2px solid ${C.lineStrong}`, fontFamily: FONT, fontSize: 30, color: tape > 0 && frame < envoi ? C.text : C.text3 }}>
              {frame < envoi && tape > 0 ? question.slice(0, tape) : "Écris ta question…"}
              {frame < envoi && tape > 0 && Math.floor(frame / 8) % 2 === 0 ? "|" : ""}
            </div>
          </div>
        </div>
      </AbsoluteFill>
      <SousTitres i={4} haut={1390} />
      <Voix i={4} />
    </AbsoluteFill>
  );
};

// 6. Prix relevés + historique (fiche composant réelle)
const P6: React.FC = () => {
  const d = dureePlan(5);
  const fondu = useFondu(d);
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.9} />
      <PlanTelephone ecran="ecrans/ecran4.jpg" de={0.18} a={0.46} d={d} rot={[0.4, -0.12]} />
      <Etiquette texte="PRIX EN DIRECT" />
      <Pastille debut={moment(5, "plusieurs")} x={50} y={420}>Relevés plusieurs fois par jour</Pastille>
      <Pastille debut={moment(5, "mille")} x={430} y={620}>
        <span style={{ fontFamily: MONO, fontWeight: 500, color: C.accent }}>979</span> composants
      </Pastille>
      <Pastille debut={moment(5, "historique")} x={70} y={1130}>Historique et plus bas prix</Pastille>
      <SousTitres i={5} haut={1380} />
      <Voix i={5} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 7. Alerte de prix par e-mail, puis FPS estimés
// ---------------------------------------------------------------------------
const P7: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const d = dureePlan(6);
  const fondu = useFondu(d);
  const mail = moment(6, "e-mail");
  const bascule = moment(6, "Et");
  const notif = ressort(frame, fps, mail, 150, 15);
  const sortieNotif = interpolate(frame, [bascule - 6, bascule + 6], [1, 0], clamp);
  const jeux = [["Cyberpunk 2077", 80], ["Fortnite", 80], ["Counter-Strike 2", 210]] as const;
  const debutFps = moment(6, "FPS") - 18;
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={0.7} />
      <ThreeCanvas width={W} height={H}>
        <Studio />
        <Eclairage accent={0.8} />
        <CameraFixe position={[0, 0.4, 7.5]} cible={[0, -0.2, 0]} fov={36} />
        <group rotation={[0.3, Math.PI / 2 - 0.9 + frame * 0.006, Math.PI / 2]} position={[0, -1.1, 0]}>
          <Modele nom="gpu" taille={4.6} temps={frame / 30} />
        </group>
        <Effets />
      </ThreeCanvas>
      <Etiquette texte={frame < bascule ? "ALERTES DE PRIX" : "FPS ESTIMÉS"} />
      {/* notification e-mail */}
      <AbsoluteFill style={{ top: 330, alignItems: "center", opacity: sortieNotif }}>
        <div style={{
          width: 900, padding: "28px 32px", borderRadius: 40, background: "rgba(28,29,33,0.94)", border: `2px solid ${C.lineStrong}`,
          boxShadow: "0 40px 90px -30px rgba(0,0,0,0.9)", display: "flex", gap: 26,
          transform: `translateY(${(1 - notif) * -260}px)`, opacity: Math.min(1, notif * 1.5),
        }}>
          <LogoR taille={96} />
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: FONT, fontSize: 28, color: C.text3 }}>
              <span>PC Radar · e-mail</span><span>maintenant</span>
            </div>
            <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: 40, color: C.text, marginTop: 6 }}>Le prix a baissé</div>
            <div style={{ fontFamily: FONT, fontSize: 32, color: C.text2, marginTop: 4, lineHeight: 1.35 }}>
              ASUS Dual RTX 5060 8 Go : <b style={{ color: C.accent, fontFamily: MONO, fontWeight: 500 }}>404,99 €</b>, plus bas prix relevé
            </div>
          </div>
        </div>
      </AbsoluteFill>
      {/* FPS du guide 1080p */}
      {frame >= bascule && (
        <AbsoluteFill style={{ top: 330, padding: `0 ${MARGE}px`, gap: 22 }}>
          <div style={{ fontFamily: FONT, fontWeight: 600, fontSize: 36, color: C.text2, opacity: ressort(frame, fps, bascule, 160, 15) }}>
            PC gamer 1080p à <span style={{ color: C.text, fontFamily: MONO, fontWeight: 500 }}>842 €</span>
          </div>
          {jeux.map(([jeu, ips], k) => {
            const p = ressort(frame, fps, debutFps + k * 7, 140, 16);
            const n = Math.round(ips * Math.min(1, Math.max(0, p)));
            return (
              <div key={jeu} style={{
                padding: "24px 30px", borderRadius: 26, background: "rgba(20,21,23,0.9)", border: `2px solid ${C.line}`,
                transform: `translateX(${(1 - p) * 700}px)`, opacity: Math.min(1, p * 1.3),
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 44, color: C.text }}>{jeu}</span>
                  <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 60, color: C.accent }}>{n} <span style={{ fontSize: 32 }}>FPS</span></span>
                </div>
                <div style={{ height: 12, borderRadius: 6, background: C.surface2, marginTop: 14, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${Math.min(100, (n / 240) * 100)}%`, background: C.accent, boxShadow: `0 0 18px ${C.accent}` }} />
                </div>
              </div>
            );
          })}
        </AbsoluteFill>
      )}
      <SousTitres i={6} haut={1390} />
      <Voix i={6} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 8. Appel à l'action : le PC réel s'assemble et tourne, pcradar.tech
// ---------------------------------------------------------------------------
const P8: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const d = dureePlan(7);
  const fondu = useFondu(d, 4, 1);
  const entree = ressort(frame, fps, 0, 80, 16);
  const angle = 0.7 + frame * 0.01;
  const url = ressort(frame, fps, moment(7, "Rendez-vous") - 6, 140, 13);
  const gratuit = ressort(frame, fps, moment(7, "gratuit"), 220, 12);
  return (
    <AbsoluteFill style={{ opacity: fondu }}>
      <Fond halo={1.1} />
      <ThreeCanvas width={W} height={H}>
        <Studio />
        <Eclairage />
        <CameraFixe position={[14 * Math.sin(angle), 3.2, 14 * Math.cos(angle)]} cible={[0, -1.9, 0]} fov={40} />
        <group position={[0, 1.15 - (1 - entree) * 2, 0]} scale={0.85 + 0.15 * entree}>
          <Modele nom="pcLeger" taille={3.1} />
          <SolStudio y={-1.58} />
        </group>
        <Effets />
      </ThreeCanvas>
      <AbsoluteFill style={{ top: 1040, alignItems: "center", gap: 24 }}>
        <div style={{ transform: `scale(${gratuit})`, padding: "14px 34px", borderRadius: 999, background: C.accent, color: "#05140d", fontFamily: FONT, fontWeight: 700, fontSize: 52 }}>
          100 % gratuit
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 24, transform: `scale(${url})`, opacity: Math.min(1, url * 1.5) }}>
          <LogoR taille={116} />
          <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 100, color: C.text, letterSpacing: "-0.03em" }}>pcradar.tech</span>
        </div>
      </AbsoluteFill>
      <SousTitres i={7} haut={1400} />
      <Voix i={7} />
    </AbsoluteFill>
  );
};

const SCENES = [P1, P2, P3, P4, P5, P6, P7, P8];
export const DUREE_TOTALE = SCENES.reduce((s, _, i) => s + dureePlan(i), 0);

export const Promo: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Series>
      {SCENES.map((S, i) => (
        <Series.Sequence key={i} durationInFrames={dureePlan(i)}>
          <S />
        </Series.Sequence>
      ))}
    </Series>
  </AbsoluteFill>
);
