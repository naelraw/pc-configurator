import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { W, H, FONT } from "./theme";
import { Fond } from "./ui";
import { CameraFixe, Eclairage, Effets, Studio } from "./three/Realiste";
import { Modele, MODELES, NomModele } from "./three/Modeles";

// Une image par modèle, vue de 3/4, pour juger le rendu et le cadrage.
const NOMS = Object.keys(MODELES) as NomModele[];

export const EssaiModeles: React.FC = () => {
  const f = useCurrentFrame();
  const nom = NOMS[f % NOMS.length];
  return (
    <AbsoluteFill style={{ background: "#0e0f11" }}>
      <Fond halo={0.6} />
      <ThreeCanvas width={W} height={H}>
        <Studio intensite={1.2} />
        <Eclairage />
        <CameraFixe position={[4.2, 2.2, 6.5]} cible={[0, 0, 0]} fov={36} />
        <group rotation={[0, nom === "telephone" ? Math.PI - 0.4 : -0.4, 0]}>
          <Modele nom={nom} taille={4} luminosite={nom === "ventirad" ? 0.35 : 1} temps={1.3}
            masquer={nom === "telephone" ? (n) => n.includes("Screen_Glass") : undefined}
            ecran={nom === "telephone" ? { fichier: "ecrans/ecran4.jpg", defilement: 0.4 } : undefined} />
        </group>
        <Effets />
      </ThreeCanvas>
      <div style={{ position: "absolute", top: 80, left: 60, fontFamily: FONT, fontSize: 60, color: "#fff" }}>{nom}</div>
    </AbsoluteFill>
  );
};
