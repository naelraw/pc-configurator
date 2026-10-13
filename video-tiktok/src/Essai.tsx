import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { W, H } from "./theme";
import { Fond } from "./ui";
import { CameraFixe, Eclairage, Effets, Studio, CarteGraphique, PcReel, SolStudio, Telephone } from "./three/Realiste";

export const Essai: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "#0e0f11" }}>
      <Fond />
      <ThreeCanvas width={W} height={H}>
        <Studio />
        <Eclairage />
        {f === 0 && (<>
          <CameraFixe position={[1.2, 0.9, 4.2]} cible={[0, 0, 0]} fov={36} />
          <group rotation={[0.15, -0.35, 0]}><CarteGraphique tour={0.5} /></group>
        </>)}
        {f === 1 && (<>
          <CameraFixe position={[9, 2.4, 9]} cible={[0, -0.3, 0]} fov={40} />
          <PcReel tour={0.4} />
          <SolStudio />
        </>)}
        {f === 2 && (<>
          <CameraFixe position={[2.5, 0.8, 11]} cible={[0, 0, 0]} fov={40} />
          <group rotation={[0.05, -0.3, 0.04]}><Telephone ecran="ecrans/ecran4.jpg" defilement={0.45} /></group>
        </>)}
        <Effets />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
