import React, { useLayoutEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { C } from "../theme";

// ---------------------------------------------------------------------------
// PC stylisé en 3D, tout en formes simples. Chaque pièce a sa position de
// montage ; « ecart » (0 = montée, 1 = loin) les fait arriver de l'extérieur.
// ---------------------------------------------------------------------------

const metal = { color: "#2a2c32", metalness: 0.65, roughness: 0.38 };
const sombre = { color: "#111215", metalness: 0.4, roughness: 0.6 };

export const Lumieres: React.FC<{ alerte?: number }> = ({ alerte = 0 }) => (
  <>
    <ambientLight intensity={0.55} />
    <directionalLight position={[5, 8, 6]} intensity={2.2} />
    <directionalLight position={[0, 2, 9]} intensity={0.8} />
    <directionalLight position={[-6, 3, -4]} intensity={0.5} color="#9fb8ff" />
    <pointLight position={[3, -1, 3]} intensity={18} distance={12} color={C.accent} />
    <pointLight position={[-2, 2, 4]} intensity={10 * alerte} distance={10} color={C.danger} />
  </>
);

// Caméra pilotée image par image (pas d'animation automatique de three.js).
export const Camera: React.FC<{ position: [number, number, number]; cible?: [number, number, number]; fov?: number }> = ({
  position,
  cible = [0, 0, 0],
  fov = 32,
}) => {
  const { camera } = useThree();
  useLayoutEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    cam.position.set(...position);
    cam.fov = fov;
    cam.updateProjectionMatrix();
    cam.lookAt(new THREE.Vector3(...cible));
  });
  return null;
};

export const Ventilateur: React.FC<{ rotation: number; rayon?: number; couleur?: string; intensite?: number }> = ({
  rotation,
  rayon = 0.5,
  couleur = C.accent,
  intensite = 1.0,
}) => (
  <group>
    <mesh>
      <torusGeometry args={[rayon, rayon * 0.09, 16, 64]} />
      <meshStandardMaterial color={couleur} emissive={couleur} emissiveIntensity={intensite} />
    </mesh>
    <mesh>
      <torusGeometry args={[rayon * 1.12, rayon * 0.03, 8, 64]} />
      <meshStandardMaterial {...sombre} />
    </mesh>
    <group rotation={[0, 0, rotation]}>
      {Array.from({ length: 7 }).map((_, i) => (
        <group key={i} rotation={[0, 0, (i * Math.PI * 2) / 7]}>
          <mesh position={[rayon * 0.5, 0, 0]} rotation={[0.5, 0, 0]}>
            <boxGeometry args={[rayon * 0.78, rayon * 0.26, 0.02]} />
            <meshStandardMaterial color="#2a2c31" metalness={0.3} roughness={0.5} />
          </mesh>
        </group>
      ))}
    </group>
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[rayon * 0.22, rayon * 0.22, 0.08, 24]} />
      <meshStandardMaterial {...metal} />
    </mesh>
  </group>
);

type Piece = { ecart?: number; rouge?: number; tour?: number };

const decalage = (ecart: number, dir: [number, number, number], rot = 1.2) => ({
  position: [dir[0] * ecart, dir[1] * ecart, dir[2] * ecart] as [number, number, number],
  rotation: [ecart * rot, ecart * rot * 0.7, 0] as [number, number, number],
});

const couleurAlerte = (rouge: number, base: string) =>
  rouge > 0 ? new THREE.Color(base).lerp(new THREE.Color(C.danger), rouge).getStyle() : base;

export const CarteGraphique: React.FC<Piece> = ({ ecart = 0, rouge = 0, tour = 0 }) => {
  const d = decalage(ecart, [5, -1.5, 2]);
  return (
    <group position={[-0.25 + d.position[0], -0.55 + d.position[1], 0.15 + d.position[2]]} rotation={d.rotation}>
      <mesh>
        <boxGeometry args={[0.55, 0.42, 2.7]} />
        <meshStandardMaterial {...metal} color={couleurAlerte(rouge, "#1d1f24")} />
      </mesh>
      <mesh position={[0.28, 0.12, 0]}>
        <boxGeometry args={[0.02, 0.05, 2.5]} />
        <meshStandardMaterial color={C.accent} emissive={C.accent} emissiveIntensity={1.12} />
      </mesh>
      {[-0.85, 0, 0.85].map((z) => (
        <group key={z} position={[0.29, -0.02, z]} rotation={[0, Math.PI / 2, 0]} scale={0.62}>
          <Ventilateur rotation={tour * 1.4} rayon={0.55} couleur={rouge > 0.5 ? C.danger : C.accent} intensite={0.8} />
        </group>
      ))}
    </group>
  );
};

export const Processeur: React.FC<Piece> = ({ ecart = 0, rouge = 0, tour = 0 }) => {
  const d = decalage(ecart, [4, 3, -1]);
  return (
    <group position={[-0.45 + d.position[0], 0.95 + d.position[1], -0.35 + d.position[2]]} rotation={d.rotation}>
      {/* Ventirad tour : ailettes + ventilateur */}
      {Array.from({ length: 9 }).map((_, i) => (
        <mesh key={i} position={[0, 0, -0.4 + i * 0.1]}>
          <boxGeometry args={[0.7, 1.05, 0.02]} />
          <meshStandardMaterial color={couleurAlerte(rouge, "#3a3d44")} metalness={0.9} roughness={0.25} />
        </mesh>
      ))}
      <group position={[0.1, 0, 0.52]} scale={0.9}>
        <Ventilateur rotation={tour * 1.2} rayon={0.45} couleur={rouge > 0.5 ? C.danger : C.accent} />
      </group>
    </group>
  );
};

export const Memoire: React.FC<Piece> = ({ ecart = 0, rouge = 0 }) => {
  const d = decalage(ecart, [3, 4, 2], 0.8);
  return (
    <group position={[-0.55 + d.position[0], 0.95 + d.position[1], 0.55 + d.position[2]]} rotation={d.rotation}>
      {[0, 0.16].map((z) => (
        <group key={z} position={[0, 0, z]}>
          <mesh>
            <boxGeometry args={[0.5, 1.15, 0.07]} />
            <meshStandardMaterial {...metal} color={couleurAlerte(rouge, "#24262b")} />
          </mesh>
          <mesh position={[0, 0.6, 0]}>
            <boxGeometry args={[0.5, 0.06, 0.075]} />
            <meshStandardMaterial color={C.accent} emissive={C.accent} emissiveIntensity={1.35} />
          </mesh>
        </group>
      ))}
    </group>
  );
};

export const Alimentation: React.FC<Piece> = ({ ecart = 0, rouge = 0 }) => {
  const d = decalage(ecart, [4, -4, -2], 0.6);
  return (
    <group position={[-0.1 + d.position[0], -1.62 + d.position[1], -0.75 + d.position[2]]} rotation={d.rotation}>
      <mesh>
        <boxGeometry args={[1.5, 0.75, 1.5]} />
        <meshStandardMaterial {...metal} color={couleurAlerte(rouge, "#17181b")} />
      </mesh>
      <mesh position={[0.76, 0, 0]}>
        <boxGeometry args={[0.01, 0.06, 1.3]} />
        <meshStandardMaterial color={C.accent} emissive={C.accent} emissiveIntensity={0.9} />
      </mesh>
    </group>
  );
};

export const CarteMere: React.FC<Piece> = ({ ecart = 0 }) => {
  const d = decalage(ecart, [-2, 1, -5], 0.4);
  return (
    <group position={[-0.88 + d.position[0], 0.25 + d.position[1], 0 + d.position[2]]} rotation={d.rotation}>
      <mesh>
        <boxGeometry args={[0.05, 3.1, 3.0]} />
        <meshStandardMaterial color="#14201b" metalness={0.3} roughness={0.7} />
      </mesh>
      {[-0.9, -0.3, 0.3, 0.9].map((y) => (
        <mesh key={y} position={[0.04, y, 0.6]}>
          <boxGeometry args={[0.01, 0.015, 1.4]} />
          <meshStandardMaterial color="#2e6b52" emissive="#2e6b52" emissiveIntensity={0.27} />
        </mesh>
      ))}
    </group>
  );
};

// Boîtier : châssis sombre, vitre latérale, 3 ventilateurs en façade.
export const Boitier: React.FC<{ tour?: number; vitre?: number }> = ({ tour = 0, vitre = 0.12 }) => (
  <group>
    {/* fond, dessus, dessous, façade */}
    <mesh position={[-1.02, 0, 0]}>
      <boxGeometry args={[0.06, 4.3, 4.3]} />
      <meshStandardMaterial {...metal} />
    </mesh>
    <mesh position={[0, 2.12, 0]}>
      <boxGeometry args={[2.1, 0.06, 4.3]} />
      <meshStandardMaterial {...metal} />
    </mesh>
    <mesh position={[0, -2.12, 0]}>
      <boxGeometry args={[2.1, 0.06, 4.3]} />
      <meshStandardMaterial {...metal} />
    </mesh>
    <mesh position={[0, 0, -2.12]}>
      <boxGeometry args={[2.1, 4.3, 0.06]} />
      <meshStandardMaterial {...metal} />
    </mesh>
    {/* façade avant : cadre + 3 ventilateurs */}
    <mesh position={[0, 0, 2.12]}>
      <boxGeometry args={[2.1, 4.3, 0.04]} />
      <meshStandardMaterial color="#0f1013" metalness={0.5} roughness={0.5} transparent opacity={0.55} />
    </mesh>
    {[1.25, 0, -1.25].map((y) => (
      <group key={y} position={[0, y, 2.06]}>
        <Ventilateur rotation={tour} rayon={0.52} />
      </group>
    ))}
    {/* vitre latérale */}
    <mesh position={[1.04, 0, 0]}>
      <boxGeometry args={[0.02, 4.3, 4.3]} />
      <meshStandardMaterial color="#8fa3b8" metalness={0.1} roughness={0.05} transparent opacity={vitre} />
    </mesh>
    {/* arêtes lumineuses */}
    {[
      [1.05, 2.15, 0, 0.03, 0.03, 4.3],
      [1.05, -2.15, 0, 0.03, 0.03, 4.3],
      [1.05, 0, 2.15, 0.03, 4.3, 0.03],
    ].map(([x, y, z, w, h, d], i) => (
      <mesh key={i} position={[x, y, z]}>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={C.accent} emissive={C.accent} emissiveIntensity={0.63} />
      </mesh>
    ))}
  </group>
);

// Sol réfléchissant discret sous le PC.
export const Sol: React.FC = () => (
  <group position={[0, -2.2, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[6, 64]} />
      <meshStandardMaterial color="#0c0d10" metalness={0.8} roughness={0.35} />
    </mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
      <ringGeometry args={[3.2, 3.24, 96]} />
      <meshStandardMaterial color={C.accent} emissive={C.accent} emissiveIntensity={0.54} transparent opacity={0.6} />
    </mesh>
  </group>
);

export const PcComplet: React.FC<{
  tour: number;
  ecarts?: { gpu?: number; cpu?: number; ram?: number; alim?: number; cm?: number };
  rouge?: number;
}> = ({ tour, ecarts = {}, rouge = 0 }) => (
  <group>
    <Boitier tour={tour} />
    <CarteMere ecart={ecarts.cm ?? 0} />
    <Processeur ecart={ecarts.cpu ?? 0} rouge={rouge} tour={tour} />
    <Memoire ecart={ecarts.ram ?? 0} rouge={rouge} />
    <CarteGraphique ecart={ecarts.gpu ?? 0} rouge={rouge} tour={tour} />
    <Alimentation ecart={ecarts.alim ?? 0} rouge={rouge} />
  </group>
);
