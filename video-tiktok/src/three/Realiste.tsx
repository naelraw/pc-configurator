import React, { useLayoutEffect, useMemo } from "react";
import { extend, useLoader, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { Bloom, EffectComposer, ToneMapping, Vignette, DepthOfField } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { staticFile } from "remotion";
import { C } from "../theme";

extend({ RoundedBoxGeometry });
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      roundedBoxGeometry: any;
    }
  }
}

// ---------------------------------------------------------------------------
// Studio : reflets d'un studio photo sur tous les matériaux + post-traitement
// ---------------------------------------------------------------------------
export const Studio: React.FC<{ intensite?: number }> = ({ intensite = 1 }) => {
  const { gl, scene } = useThree();
  useLayoutEffect(() => {
    const pm = new THREE.PMREMGenerator(gl);
    const env = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    (scene as any).environmentIntensity = 0.55 * intensite;
    return () => {
      env.dispose();
      pm.dispose();
    };
  }, [gl, scene, intensite]);
  return null;
};

// ecran : plan avec le téléphone ; la page du site garde ses vraies couleurs (pas de correction ACES).
export const Effets: React.FC<{ flou?: { cible: [number, number, number]; force?: number }; ecran?: boolean }> = ({ flou, ecran }) => (
  <EffectComposer multisampling={8}>
    {flou ? (
      <DepthOfField target={new THREE.Vector3(...flou.cible)} focalLength={0.02} bokehScale={flou.force ?? 3} />
    ) : (
      <></>
    )}
    <Bloom intensity={ecran ? 0.18 : 0.85} luminanceThreshold={ecran ? 0.97 : 0.62} luminanceSmoothing={0.2} mipmapBlur />
    {ecran ? <></> : <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />}
    <Vignette offset={0.28} darkness={ecran ? 0.4 : 0.62} />
  </EffectComposer>
);

export const CameraFixe: React.FC<{ position: [number, number, number]; cible?: [number, number, number]; fov?: number }> = ({
  position,
  cible = [0, 0, 0],
  fov = 38,
}) => {
  const { camera } = useThree();
  useLayoutEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    cam.position.set(...position);
    cam.fov = fov;
    cam.near = 0.05;
    cam.far = 200;
    cam.updateProjectionMatrix();
    cam.lookAt(new THREE.Vector3(...cible));
  });
  return null;
};

export const Eclairage: React.FC<{ alerte?: number; accent?: number }> = ({ alerte = 0, accent = 1 }) => (
  <>
    <ambientLight intensity={0.12} />
    {/* Lumière principale douce, contre-jour froid, liseré émeraude */}
    <directionalLight position={[6, 9, 7]} intensity={2.4} color="#fff6ec" />
    <directionalLight position={[-8, 4, -6]} intensity={1.2} color="#9fbcff" />
    <spotLight position={[-5, 6, 8]} angle={0.5} penumbra={0.8} intensity={60 * accent} distance={30} color={C.accent} />
    <pointLight position={[3, -2, 5]} intensity={30 * alerte} distance={14} color={C.danger} />
  </>
);

// ---------------------------------------------------------------------------
// Textures dessinées (aléatoire fixé : la même image à chaque rendu)
// ---------------------------------------------------------------------------
const alea = (graine: number) => () => {
  graine |= 0;
  graine = (graine + 0x6d2b79f5) | 0;
  let t = Math.imul(graine ^ (graine >>> 15), 1 | graine);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const cache: Record<string, THREE.Texture> = {};
const dessiner = (nom: string, w: number, h: number, f: (g: CanvasRenderingContext2D, r: () => number) => void, srgb = false) => {
  if (cache[nom]) return cache[nom];
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  f(c.getContext("2d")!, alea(nom.length * 7919 + w));
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 16;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  cache[nom] = t;
  return t;
};

// Rugosité de métal brossé (stries horizontales).
export const brosse = () =>
  dessiner("brosse", 512, 512, (g, r) => {
    g.fillStyle = "#7a7a7a";
    g.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 5000; i++) {
      const y = r() * 512;
      const v = 95 + r() * 80;
      g.strokeStyle = `rgba(${v},${v},${v},0.35)`;
      g.beginPath();
      g.moveTo(0, y);
      g.lineTo(512, y + (r() - 0.5) * 3);
      g.stroke();
    }
  });

// Circuit imprimé : pistes, pastilles dorées, sérigraphie.
export const circuit = () =>
  dessiner(
    "circuit",
    1024,
    1024,
    (g, r) => {
      g.fillStyle = "#0c1611";
      g.fillRect(0, 0, 1024, 1024);
      g.lineCap = "round";
      for (let i = 0; i < 420; i++) {
        let x = r() * 1024;
        let y = r() * 1024;
        g.strokeStyle = r() > 0.5 ? "#15301f" : "#1a3a28";
        g.lineWidth = 1 + r() * 3;
        g.beginPath();
        g.moveTo(x, y);
        for (let k = 0; k < 4; k++) {
          if (r() > 0.5) x += (r() - 0.5) * 240;
          else y += (r() - 0.5) * 240;
          g.lineTo(x, y);
        }
        g.stroke();
      }
      for (let i = 0; i < 900; i++) {
        g.fillStyle = r() > 0.6 ? "#b8913a" : "#2b2f2c";
        g.fillRect(r() * 1024, r() * 1024, 3 + r() * 9, 2 + r() * 5);
      }
      g.fillStyle = "rgba(220,225,220,0.55)";
      for (let i = 0; i < 160; i++) g.fillRect(r() * 1024, r() * 1024, 10 + r() * 30, 2);
    },
    true
  );

// Grille perforée de façade (alpha : noir = trou).
export const grille = () =>
  dessiner("grille", 512, 512, (g) => {
    g.fillStyle = "#ffffff";
    g.fillRect(0, 0, 512, 512);
    g.fillStyle = "#000000";
    for (let y = 0; y < 512; y += 16)
      for (let x = (y / 16) % 2 ? 8 : 0; x < 512; x += 16) {
        g.beginPath();
        g.arc(x, y, 5.2, 0, Math.PI * 2);
        g.fill();
      }
  });

// Dégradé RGB (diffuseurs de la RAM, bandeaux).
export const degradeRgb = () =>
  dessiner(
    "rgb",
    512,
    8,
    (g) => {
      const d = g.createLinearGradient(0, 0, 512, 0);
      d.addColorStop(0, "#3ecf8e");
      d.addColorStop(0.5, "#5fe0c0");
      d.addColorStop(1, "#3ecf8e");
      g.fillStyle = d;
      g.fillRect(0, 0, 512, 8);
    },
    true
  );

// ---------------------------------------------------------------------------
// Matériaux
// ---------------------------------------------------------------------------
const M = {
  alu: () => <meshStandardMaterial color="#b9bdc4" metalness={1} roughness={0.32} roughnessMap={brosse()} />,
  aluSombre: () => <meshStandardMaterial color="#3a3d44" metalness={1} roughness={0.38} roughnessMap={brosse()} />,
  noir: () => <meshStandardMaterial color="#141519" metalness={0.6} roughness={0.42} roughnessMap={brosse()} />,
  plastique: () => <meshStandardMaterial color="#17181c" metalness={0.1} roughness={0.55} />,
  cuivre: () => <meshStandardMaterial color="#c9774a" metalness={1} roughness={0.22} />,
  or: () => <meshStandardMaterial color="#d6a64a" metalness={1} roughness={0.25} />,
  led: (couleur = C.accent, force = 4) => <meshStandardMaterial color={couleur} emissive={couleur} emissiveIntensity={force} toneMapped={false} />,
};

// ---------------------------------------------------------------------------
// Ventilateur : pales courbes en relief, moyeu, anneau RGB
// ---------------------------------------------------------------------------
let paleGeo: THREE.ExtrudeGeometry | null = null;
const pale = () => {
  if (paleGeo) return paleGeo;
  const s = new THREE.Shape();
  s.moveTo(0.3, -0.1);
  s.bezierCurveTo(0.55, -0.24, 0.82, -0.2, 0.96, 0.02);
  s.lineTo(0.93, 0.2);
  s.bezierCurveTo(0.74, 0.12, 0.52, 0.12, 0.3, 0.12);
  s.closePath();
  paleGeo = new THREE.ExtrudeGeometry(s, { depth: 0.018, bevelEnabled: true, bevelThickness: 0.006, bevelSize: 0.006, bevelSegments: 2, curveSegments: 16 });
  return paleGeo;
};

export const Ventilo: React.FC<{ r?: number; rot: number; couleur?: string; cadre?: boolean; force?: number }> = ({
  r = 0.5,
  rot,
  couleur = C.accent,
  cadre = true,
  force = 3.5,
}) => (
  <group scale={r}>
    {cadre && (
      <>
        <mesh>
          <torusGeometry args={[1.02, 0.07, 20, 80]} />
          {M.noir()}
        </mesh>
        <mesh position={[0, 0, 0.02]}>
          <torusGeometry args={[0.985, 0.022, 12, 96]} />
          {M.led(couleur, force)}
        </mesh>
      </>
    )}
    <group rotation={[0, 0, rot]}>
      {Array.from({ length: 9 }).map((_, i) => (
        <group key={i} rotation={[0, 0, (i * Math.PI * 2) / 9]}>
          <mesh geometry={pale()} rotation={[0.42, 0, 0]}>
            <meshPhysicalMaterial color="#1b1d22" metalness={0.2} roughness={0.35} clearcoat={0.6} transparent opacity={0.92} />
          </mesh>
        </group>
      ))}
    </group>
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[0.31, 0.31, 0.16, 48]} />
      {M.noir()}
    </mesh>
    <mesh position={[0, 0, 0.081]}>
      <circleGeometry args={[0.25, 48]} />
      <meshStandardMaterial color="#202227" metalness={0.8} roughness={0.25} />
    </mesh>
    <mesh position={[0.1, 0.1, 0.083]}>
      <circleGeometry args={[0.045, 24]} />
      {M.led(C.accent, 2)}
    </mesh>
  </group>
);

type Piece = { tour?: number; rouge?: number };
const teinte = (base: string, rouge = 0) => (rouge > 0 ? new THREE.Color(base).lerp(new THREE.Color(C.danger), rouge * 0.7).getStyle() : base);

// ---------------------------------------------------------------------------
// Carte graphique (3 ventilateurs), longueur 3 unités
// ---------------------------------------------------------------------------
export const CarteGraphique: React.FC<Piece> = ({ tour = 0, rouge = 0 }) => (
  <group>
    {/* carénage avant */}
    <mesh position={[0, 0, 0.16]}>
      <roundedBoxGeometry args={[3.0, 1.12, 0.12, 4, 0.05]} />
      <meshStandardMaterial color={teinte("#2a2c32", rouge)} metalness={0.85} roughness={0.3} roughnessMap={brosse()} />
    </mesh>
    {/* radiateur à ailettes entre carénage et plaque arrière */}
    {Array.from({ length: 46 }).map((_, i) => (
      <mesh key={i} position={[-1.4 + i * 0.062, 0, -0.02]}>
        <boxGeometry args={[0.012, 1.0, 0.26]} />
        {M.alu()}
      </mesh>
    ))}
    {/* caloducs en cuivre qui dépassent sur le dessus */}
    {[-0.6, -0.2, 0.2, 0.6].map((x) => (
      <mesh key={x} position={[x, 0.53, -0.02]} rotation={[0, 0, Math.PI / 2]}>
        <torusGeometry args={[0.07, 0.022, 12, 24, Math.PI]} />
        {M.cuivre()}
      </mesh>
    ))}
    {/* plaque arrière */}
    <mesh position={[0, 0, -0.19]}>
      <roundedBoxGeometry args={[3.0, 1.12, 0.05, 3, 0.02]} />
      {M.aluSombre()}
    </mesh>
    {/* bandeau lumineux sur la tranche */}
    <mesh position={[0.2, 0.565, 0.16]}>
      <boxGeometry args={[2.2, 0.025, 0.06]} />
      {M.led(rouge > 0.5 ? C.danger : C.accent, 3)}
    </mesh>
    {/* équerre PCIe et connecteurs */}
    <mesh position={[-1.53, -0.05, 0]}>
      <boxGeometry args={[0.03, 1.2, 0.42]} />
      {M.alu()}
    </mesh>
    {[0.25, 0, -0.25].map((y) => (
      <mesh key={y} position={[-1.55, y, 0.08]}>
        <boxGeometry args={[0.02, 0.12, 0.2]} />
        {M.plastique()}
      </mesh>
    ))}
    {/* contacts dorés PCIe */}
    <mesh position={[-0.4, -0.6, 0]}>
      <boxGeometry args={[1.2, 0.08, 0.05]} />
      {M.or()}
    </mesh>
    {[-0.95, 0, 0.95].map((x) => (
      <group key={x} position={[x, 0, 0.24]}>
        <Ventilo r={0.44} rot={tour * 1.3 + x} couleur={rouge > 0.5 ? C.danger : C.accent} force={2.5} />
      </group>
    ))}
  </group>
);

// ---------------------------------------------------------------------------
// Ventirad tour : ailettes, caloducs en cuivre, capot, ventilateur
// ---------------------------------------------------------------------------
export const Ventirad: React.FC<Piece> = ({ tour = 0, rouge = 0 }) => (
  <group>
    {Array.from({ length: 34 }).map((_, i) => (
      <mesh key={i} position={[0, 0.25 + i * 0.034, 0]}>
        <boxGeometry args={[0.95, 0.008, 0.72]} />
        <meshStandardMaterial color={teinte("#c3c7cd", rouge)} metalness={1} roughness={0.28} roughnessMap={brosse()} />
      </mesh>
    ))}
    {[-0.3, -0.1, 0.1, 0.3].map((x) => (
      <mesh key={x} position={[x, 0.75, 0.12]}>
        <cylinderGeometry args={[0.035, 0.035, 1.3, 20]} />
        {M.cuivre()}
      </mesh>
    ))}
    <mesh position={[0, 0.06, 0]}>
      <roundedBoxGeometry args={[0.7, 0.14, 0.6, 3, 0.03]} />
      {M.cuivre()}
    </mesh>
    <mesh position={[0, 1.44, 0]}>
      <roundedBoxGeometry args={[1.0, 0.07, 0.78, 3, 0.03]} />
      {M.noir()}
    </mesh>
    <mesh position={[0, 1.48, 0]}>
      <boxGeometry args={[0.6, 0.012, 0.03]} />
      {M.led(rouge > 0.5 ? C.danger : C.accent, 3)}
    </mesh>
    <group position={[0, 0.82, 0.42]}>
      <Ventilo r={0.48} rot={tour * 1.1} couleur={rouge > 0.5 ? C.danger : C.accent} />
    </group>
  </group>
);

// ---------------------------------------------------------------------------
// Barrettes de RAM avec dissipateurs et diffuseur lumineux
// ---------------------------------------------------------------------------
export const Ram: React.FC<Piece> = ({ rouge = 0 }) => (
  <group>
    {[0, 0.13].map((z) => (
      <group key={z} position={[0, 0, z]}>
        <mesh position={[0, 0.42, 0]}>
          <roundedBoxGeometry args={[1.35, 0.78, 0.07, 3, 0.02]} />
          <meshStandardMaterial color={teinte("#26282e", rouge)} metalness={0.9} roughness={0.32} roughnessMap={brosse()} />
        </mesh>
        <mesh position={[0, 0.42, 0.037]}>
          <boxGeometry args={[1.0, 0.03, 0.002]} />
          {M.alu()}
        </mesh>
        <mesh position={[0, 0.86, 0]}>
          <roundedBoxGeometry args={[1.32, 0.12, 0.06, 2, 0.02]} />
          <meshStandardMaterial
            color={rouge > 0.5 ? C.danger : C.accent}
            emissive={rouge > 0.5 ? C.danger : C.accent}
            emissiveMap={degradeRgb()}
            emissiveIntensity={2.4}
            transparent
            opacity={0.92}
            toneMapped={false}
          />
        </mesh>
        <mesh position={[0, 0.01, 0]}>
          <boxGeometry args={[1.25, 0.04, 0.035]} />
          {M.or()}
        </mesh>
      </group>
    ))}
  </group>
);

// ---------------------------------------------------------------------------
// Alimentation modulaire
// ---------------------------------------------------------------------------
export const Alim: React.FC<Piece> = ({ tour = 0, rouge = 0 }) => (
  <group>
    <mesh>
      <roundedBoxGeometry args={[1.5, 0.86, 1.4, 4, 0.04]} />
      <meshStandardMaterial color={teinte("#1a1b20", rouge)} metalness={0.7} roughness={0.4} roughnessMap={brosse()} />
    </mesh>
    <group position={[0, 0.44, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <Ventilo r={0.5} rot={tour * 0.7} cadre={false} />
      <mesh position={[0, 0, 0.02]}>
        <torusGeometry args={[0.52, 0.02, 10, 64]} />
        {M.led(rouge > 0.5 ? C.danger : C.accent, 2.2)}
      </mesh>
    </group>
    {[-0.35, 0, 0.35].map((x) => (
      <mesh key={x} position={[x, -0.1, 0.71]}>
        <boxGeometry args={[0.22, 0.12, 0.02]} />
        {M.plastique()}
      </mesh>
    ))}
  </group>
);

// ---------------------------------------------------------------------------
// Carte mère : circuit, socket, dissipateurs VRM, slots
// ---------------------------------------------------------------------------
export const CarteMere: React.FC = () => (
  <group>
    <mesh>
      <boxGeometry args={[3.0, 3.1, 0.04]} />
      <meshStandardMaterial map={circuit()} metalness={0.3} roughness={0.55} />
    </mesh>
    {/* socket */}
    <mesh position={[0.1, 0.7, 0.04]}>
      <boxGeometry args={[0.55, 0.55, 0.05]} />
      {M.alu()}
    </mesh>
    {/* dissipateurs VRM */}
    <mesh position={[-0.5, 0.7, 0.1]}>
      <roundedBoxGeometry args={[0.28, 0.9, 0.18, 3, 0.03]} />
      {M.aluSombre()}
    </mesh>
    <mesh position={[0.1, 1.3, 0.1]}>
      <roundedBoxGeometry args={[0.95, 0.24, 0.18, 3, 0.03]} />
      {M.aluSombre()}
    </mesh>
    {/* slots mémoire */}
    {[0.75, 0.88, 1.01, 1.14].map((x) => (
      <mesh key={x} position={[x, 0.65, 0.05]}>
        <boxGeometry args={[0.06, 1.4, 0.06]} />
        {M.plastique()}
      </mesh>
    ))}
    {/* slot PCIe blindé */}
    <mesh position={[-0.15, -0.35, 0.05]}>
      <boxGeometry args={[2.1, 0.07, 0.07]} />
      {M.alu()}
    </mesh>
    {/* cache I/O avec liseré */}
    <mesh position={[-1.2, 0.95, 0.15]}>
      <roundedBoxGeometry args={[0.45, 1.05, 0.26, 3, 0.04]} />
      {M.noir()}
    </mesh>
    <mesh position={[-1.0, 0.95, 0.285]}>
      <boxGeometry args={[0.02, 0.9, 0.005]} />
      {M.led(C.accent, 2.5)}
    </mesh>
    {/* chipset et M.2 */}
    <mesh position={[0.6, -0.9, 0.06]}>
      <roundedBoxGeometry args={[0.5, 0.5, 0.08, 3, 0.03]} />
      {M.aluSombre()}
    </mesh>
    <mesh position={[-0.3, -0.85, 0.06]}>
      <roundedBoxGeometry args={[1.0, 0.18, 0.05, 2, 0.02]} />
      {M.alu()}
    </mesh>
  </group>
);

// ---------------------------------------------------------------------------
// Boîtier : cadre en aluminium, verre trempé, façade perforée, cache-alim
// ---------------------------------------------------------------------------
const Barre: React.FC<{ p: [number, number, number]; s: [number, number, number] }> = ({ p, s }) => (
  <mesh position={p}>
    <roundedBoxGeometry args={[...s, 3, 0.025]} />
    {M.noir()}
  </mesh>
);

export const Boitier: React.FC<{ tour?: number; verre?: number }> = ({ tour = 0, verre = 0.07 }) => {
  const L = 2.3, Hh = 4.6, P = 4.6;
  return (
    <group>
      {/* arêtes du cadre */}
      {[-1, 1].flatMap((sx) =>
        [-1, 1].map((sy) => <Barre key={`${sx}${sy}`} p={[(sx * L) / 2, (sy * Hh) / 2, 0]} s={[0.09, 0.09, P]} />)
      )}
      {[-1, 1].flatMap((sx) =>
        [-1, 1].map((sz) => <Barre key={`v${sx}${sz}`} p={[(sx * L) / 2, 0, (sz * P) / 2]} s={[0.09, Hh, 0.09]} />)
      )}
      {[-1, 1].flatMap((sy) =>
        [-1, 1].map((sz) => <Barre key={`h${sy}${sz}`} p={[0, (sy * Hh) / 2, (sz * P) / 2]} s={[L, 0.09, 0.09]} />)
      )}
      {/* panneau du fond et dessus en métal */}
      <mesh position={[-L / 2 + 0.02, 0, 0]}>
        <boxGeometry args={[0.03, Hh, P]} />
        {M.noir()}
      </mesh>
      <mesh position={[0, Hh / 2 - 0.02, 0]}>
        <boxGeometry args={[L, 0.03, P]} />
        <meshStandardMaterial color="#16171b" metalness={0.6} roughness={0.5} alphaMap={grille()} transparent alphaTest={0.5} />
      </mesh>
      {/* verre trempé latéral et frontal */}
      <mesh position={[L / 2, 0, 0]}>
        <boxGeometry args={[0.025, Hh - 0.05, P - 0.05]} />
        <meshPhysicalMaterial color="#9fb2c4" metalness={0} roughness={0.03} clearcoat={1} transparent opacity={verre} envMapIntensity={0.7} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0, P / 2]}>
        <boxGeometry args={[L - 0.05, Hh - 0.05, 0.025]} />
        <meshPhysicalMaterial color="#9fb2c4" metalness={0} roughness={0.03} clearcoat={1} transparent opacity={verre * 0.8} envMapIntensity={0.7} depthWrite={false} />
      </mesh>
      {/* 3 ventilateurs en façade, derrière le verre */}
      {[1.35, 0.05, -1.25].map((y) => (
        <group key={y} position={[0.15, y, P / 2 - 0.18]}>
          <Ventilo r={0.56} rot={tour + y} />
        </group>
      ))}
      {/* ventilateur arrière */}
      <group position={[-0.1, 1.45, -P / 2 + 0.15]} rotation={[0, Math.PI, 0]}>
        <Ventilo r={0.5} rot={tour * 0.9} />
      </group>
      {/* cache-alimentation */}
      <mesh position={[0.05, -1.85, -0.1]}>
        <roundedBoxGeometry args={[L - 0.15, 0.85, P - 0.3, 3, 0.03]} />
        {M.noir()}
      </mesh>
      <mesh position={[L / 2 - 0.08, -1.45, -0.1]}>
        <boxGeometry args={[0.005, 0.02, P - 0.6]} />
        {M.led(C.accent, 2.5)}
      </mesh>
      {/* pieds */}
      {[-1, 1].flatMap((sx) =>
        [-1, 1].map((sz) => (
          <mesh key={`p${sx}${sz}`} position={[sx * 0.85, -Hh / 2 - 0.08, sz * 1.9]}>
            <cylinderGeometry args={[0.12, 0.14, 0.1, 24]} />
            {M.plastique()}
          </mesh>
        ))
      )}
    </group>
  );
};

// PC monté : pièces à leur place (ecarts : 0 = montée, 1 = arrive de loin).
export type Ecarts = { cm?: number; alim?: number; cpu?: number; ram?: number; gpu?: number };
const placer = (e: number, base: [number, number, number], dir: [number, number, number]) =>
  [base[0] + dir[0] * e, base[1] + dir[1] * e, base[2] + dir[2] * e] as [number, number, number];

export const PcReel: React.FC<{ tour: number; ecarts?: Ecarts; verre?: number }> = ({ tour, ecarts = {}, verre }) => {
  const e = { cm: 0, alim: 0, cpu: 0, ram: 0, gpu: 0, ...ecarts };
  return (
    <group>
      <Boitier tour={tour} verre={verre} />
      <group position={placer(e.cm, [-0.95, 0.45, -0.1], [-1, 0.5, -4])} rotation={[0, Math.PI / 2, 0]} scale={1.15}>
        <CarteMere />
      </group>
      <group position={placer(e.cpu, [-0.62, 0.55, -0.05], [5, 3, 1])} rotation={[e.cpu * 1.5, Math.PI / 2, e.cpu]} scale={0.95}>
        <Ventirad tour={tour} />
      </group>
      <group position={placer(e.ram, [-0.8, 0.82, -1.2], [4, 4, -1])} rotation={[e.ram, Math.PI / 2, 0]} scale={[1, 1, 1]}>
        <group rotation={[0, 0, Math.PI / 2]} position={[0.2, 0, 0]}>
          <Ram />
        </group>
      </group>
      <group position={placer(e.gpu, [-0.25, -0.75, 0.05], [5, -2, 3])} rotation={[e.gpu * 0.8, -Math.PI / 2, e.gpu * 0.5]}>
        <group rotation={[0, Math.PI, 0]}>
          <CarteGraphique tour={tour} />
        </group>
      </group>
      <group position={placer(e.alim, [0, -1.85, -1.3], [4, -3, -1])} rotation={[e.alim, 0, 0]}>
        <Alim tour={tour} />
      </group>
      <pointLight position={[0.2, 0.3, 0]} intensity={6} distance={5} color={C.accent} />
    </group>
  );
};

// Sol brillant + ombre douce sous l'objet.
let ombreTex: THREE.Texture | null = null;
const ombre = () =>
  ombreTex ||
  (ombreTex = dessiner("ombre", 256, 256, (g) => {
    const d = g.createRadialGradient(128, 128, 10, 128, 128, 128);
    d.addColorStop(0, "rgba(0,0,0,0.85)");
    d.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = d;
    g.fillRect(0, 0, 256, 256);
  }));

export const SolStudio: React.FC<{ y?: number; anneau?: boolean }> = ({ y = -2.45, anneau = true }) => (
  <group position={[0, y, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[40, 96]} />
      <meshStandardMaterial color="#050607" metalness={0.5} roughness={0.5} envMapIntensity={0.12} />
    </mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
      <planeGeometry args={[6, 6]} />
      <meshBasicMaterial map={ombre()} transparent depthWrite={false} />
    </mesh>
    {anneau && (
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <ringGeometry args={[3.3, 3.34, 128]} />
        {M.led(C.accent, 1.6)}
      </mesh>
    )}
  </group>
);

// ---------------------------------------------------------------------------
// Téléphone en 3D : l'écran affiche une vraie page du site, qui défile
// ---------------------------------------------------------------------------
const ecranGeo = (w: number, h: number, r: number) => {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2);
  s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r);
  s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2);
  s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r);
  s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  const g = new THREE.ShapeGeometry(s, 24);
  const pos = g.attributes.position;
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    uv[i * 2] = (pos.getX(i) + w / 2) / w;
    uv[i * 2 + 1] = (pos.getY(i) + h / 2) / h;
  }
  g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return g;
};

export const useEcran = (fichier: string) => {
  const t = useLoader(THREE.TextureLoader, staticFile(fichier));
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 16;
  return t;
};

export const Telephone: React.FC<{ ecran: string; defilement: number; hauteurImage?: number }> = ({
  ecran,
  defilement,
  hauteurImage = 4800,
}) => {
  const W = 3.0, Hh = 6.3, P = 0.3, ew = 2.82, eh = 6.12;
  const tex = useEcran(ecran);
  const geo = useMemo(() => ecranGeo(ew, eh, 0.42), []);
  const cadre = useMemo(() => ecranGeo(W - 0.06, Hh - 0.06, 0.44), []);
  const visible = Math.min(1, ((860 / ew) * eh) / hauteurImage);
  tex.repeat.set(1, visible);
  tex.offset.set(0, (1 - visible) * (1 - Math.min(1, Math.max(0, defilement))));
  return (
    <group>
      <mesh>
        <roundedBoxGeometry args={[W, Hh, P, 8, 0.45]} />
        <meshStandardMaterial color="#3d3f45" metalness={1} roughness={0.26} roughnessMap={brosse()} />
      </mesh>
      <mesh position={[0, 0, P / 2 + 0.002]} geometry={cadre}>
        <meshStandardMaterial color="#050506" roughness={0.2} />
      </mesh>
      <mesh position={[0, 0, P / 2 + 0.004]} geometry={geo}>
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
      {/* îlot de la caméra frontale */}
      <mesh position={[0, eh / 2 - 0.22, P / 2 + 0.006]}>
        <roundedBoxGeometry args={[0.8, 0.22, 0.01, 2, 0.1]} />
        <meshBasicMaterial color="#000000" />
      </mesh>
      {/* reflet du verre */}
      <mesh position={[0, 0, P / 2 + 0.008]} geometry={geo}>
        <meshPhysicalMaterial color="#ffffff" roughness={0} metalness={0} clearcoat={1} transparent opacity={0.025} envMapIntensity={1.2} />
      </mesh>
      {/* boutons latéraux */}
      {[
        [W / 2 + 0.015, 1.4, 0.5],
        [-W / 2 - 0.015, 1.7, 0.35],
        [-W / 2 - 0.015, 1.05, 0.55],
      ].map(([x, y, h], i) => (
        <mesh key={i} position={[x, y, 0]}>
          <roundedBoxGeometry args={[0.04, h, 0.12, 2, 0.015]} />
          <meshStandardMaterial color="#45474d" metalness={1} roughness={0.3} />
        </mesh>
      ))}
    </group>
  );
};
