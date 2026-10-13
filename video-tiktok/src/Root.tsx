import React from "react";
import { AbsoluteFill, Composition, Series } from "remotion";
import { FPS, H, W } from "./theme";
import { Accroche, AppelAction, Assemblage, Atouts, Probleme, Solution } from "./Scenes";
import { Essai } from "./Essai";
import { DUREE_TOTALE, Promo } from "./v2/Promo";
import { EssaiModeles } from "./EssaiModeles";

// Durées des plans, en images (30 par seconde) : 22 s au total.
const PLANS = [
  { duree: 75, C: Accroche },
  { duree: 105, C: Probleme },
  { duree: 120, C: Solution },
  { duree: 150, C: Assemblage },
  { duree: 120, C: Atouts },
  { duree: 90, C: AppelAction },
];
const TOTAL = PLANS.reduce((t, p) => t + p.duree, 0);

const Video: React.FC = () => (
  <AbsoluteFill style={{ background: "#0e0f11" }}>
    <Series>
      {PLANS.map(({ duree, C }, i) => (
        <Series.Sequence key={i} durationInFrames={duree}>
          <C duree={duree} />
        </Series.Sequence>
      ))}
    </Series>
  </AbsoluteFill>
);

export const Root: React.FC = () => (
  <>
    <Composition id="PcRadarTikTok" component={Video} durationInFrames={TOTAL} fps={FPS} width={W} height={H} />
    <Composition id="Essai3D" component={Essai} durationInFrames={3} fps={FPS} width={W} height={H} />
    <Composition id="EssaiModeles" component={EssaiModeles} durationInFrames={8} fps={FPS} width={W} height={H} />
    <Composition id="PcRadarPromo" component={Promo} durationInFrames={DUREE_TOTALE} fps={FPS} width={W} height={H} />
  </>
);
