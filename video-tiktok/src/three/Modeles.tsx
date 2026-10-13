import React, { useMemo } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloner } from "three/examples/jsm/utils/SkeletonUtils.js";
import { continueRender, delayRender, staticFile } from "remotion";
import { C } from "../theme";

// ---------------------------------------------------------------------------
// Modèles 3D téléchargés sur Sketchfab (CC-BY 4.0, crédits dans CREDITS.md).
// Chaque modèle est recentré et mis à l'échelle : « taille » = sa plus grande
// dimension, en unités de la scène.
// ---------------------------------------------------------------------------
export const MODELES = {
  gpu: "modeles/gpu.glb",
  ventirad: "modeles/ventirad.glb",
  ram: "modeles/ram.glb",
  alim: "modeles/alim.glb",
  carteMere: "modeles/carte-mere.glb",
  pc: "modeles/pc.glb",
  pcLeger: "modeles/pc-leger.glb",
  telephone: "modeles/telephone.glb",
} as const;
export type NomModele = keyof typeof MODELES;

type Options = {
  taille: number;
  rouge?: number;                       // 0 à 1 : teinte rouge d'alerte
  masquer?: (nom: string) => boolean;   // nœuds à cacher (logos...)
  tourner?: { filtre: (nom: string) => boolean; angle: number; axe?: "x" | "y" | "z" };
  luminosite?: number;                  // multiplie la couleur des matériaux (ailettes trop blanches...)
  ecran?: { fichier: string; defilement: number; hauteurImage?: number; materiau?: string };
  temps?: number;                       // secondes : joue les animations du modèle (ventilateurs)
};

const rougeAlerte = new THREE.Color(C.danger);

// Chargement qui retient l'image tant que le fichier n'est pas prêt (delayRender) :
// sans ça, la première image d'un plan pouvait être capturée avant le modèle.
const enCours = new Map<string, { promesse: Promise<void>; resultat?: any }>();
function charger<T>(cle: string, lancer: () => Promise<T>): T {
  let e = enCours.get(cle);
  if (!e) {
    const attente = delayRender(`Chargement ${cle}`, { timeoutInMilliseconds: 180000 });
    const entree: { promesse: Promise<void>; resultat?: any } = { promesse: Promise.resolve() };
    entree.promesse = lancer().then((r) => {
      entree.resultat = r;
      // Deux images d'écran : le temps que three.js dessine la scène avec le modèle.
      requestAnimationFrame(() => requestAnimationFrame(() => continueRender(attente)));
    });
    enCours.set(cle, entree);
    e = entree;
  }
  if (e.resultat === undefined) throw e.promesse;
  return e.resultat as T;
}

const useGltf = (fichier: string) => charger(fichier, () => new GLTFLoader().loadAsync(staticFile(fichier)));

// Image d'une page du site affichée sur l'écran du téléphone (UV de l'écran : haut de l'image en v = 1).
const useImage = (fichier?: string) => {
  const t = charger(`img:${fichier || "ecrans/ecran1.jpg"}`, () => new THREE.TextureLoader().loadAsync(staticFile(fichier || "ecrans/ecran1.jpg")));
  t.colorSpace = THREE.SRGBColorSpace;
  t.flipY = true;
  t.anisotropy = 16;
  return t;
};

export const Modele: React.FC<{ nom: NomModele } & Options> = ({ nom, taille, rouge = 0, masquer, tourner, luminosite = 1, ecran, temps }) => {
  const gltf = useGltf(MODELES[nom]);
  const image = useImage(ecran?.fichier);
  // Copie propre (matériaux compris) pour pouvoir teinter sans toucher l'original.
  const { objet, base, mixer } = useMemo(() => {
    // SkeletonUtils.clone : garde les liaisons des maillages animés par des os (ventilateurs).
    const objet = cloner(gltf.scene);
    const base = new Map<THREE.MeshStandardMaterial, { couleur: THREE.Color; emission: THREE.Color }>();
    objet.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.castShadow = m.receiveShadow = true;
        // Maillages animés par des os : leur sphère englobante est fausse, ne pas les écarter.
        m.frustumCulled = false;
        const mats = (Array.isArray(m.material) ? m.material : [m.material]).map((x) => {
          const c = (x as THREE.MeshStandardMaterial).clone();
          if (c.color) base.set(c, { couleur: c.color.clone(), emission: (c.emissive || new THREE.Color(0)).clone() });
          if (ecran && c.name === (ecran.materiau || "Wallpaper")) {
            const ecranMat = new THREE.MeshBasicMaterial({ map: image, toneMapped: false, side: THREE.DoubleSide });
            ecranMat.name = "ecran-site";
            return ecranMat as unknown as THREE.MeshStandardMaterial;
          }
          if (c.map) c.map.anisotropy = 16;
          return c;
        });
        m.material = Array.isArray(m.material) ? mats : mats[0];
      }
    });
    const boite = new THREE.Box3().setFromObject(objet, true);
    if ((globalThis as any).DEBUG_MODELES) {
      const d = boite.getSize(new THREE.Vector3());
      const mats: string[] = [];
      objet.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh) mats.push(`${m.name}:${(m.material as THREE.Material).name}:${(m as any).isSkinnedMesh ? "os" : ""}`); });
      console.log("MODELE", nom, "taille", d.x.toFixed(3), d.y.toFixed(3), d.z.toFixed(3), "|", mats.slice(0, 30).join(" ; "));
    }
    const dim = boite.getSize(new THREE.Vector3());
    const centre = boite.getCenter(new THREE.Vector3());
    objet.position.sub(centre);
    const groupe = new THREE.Group();
    groupe.add(objet);
    groupe.userData.echelle = 1 / Math.max(dim.x, dim.y, dim.z);
    // Animations fournies par le modèle, jouées à un instant précis (rendu image par image).
    const mixer = gltf.animations.length ? new THREE.AnimationMixer(objet) : null;
    gltf.animations.forEach((clip: THREE.AnimationClip) => mixer!.clipAction(clip).play());
    return { objet: groupe, base, mixer };
  }, [gltf]);

  // Teinte, nœuds masqués et pièces qui tournent : appliqués à chaque image.
  base.forEach((v, mat) => {
    mat.color.copy(v.couleur).multiplyScalar(luminosite).lerp(rougeAlerte, rouge * 0.65);
    if (mat.emissive) mat.emissive.copy(v.emission).lerp(rougeAlerte, rouge * 0.35);
  });
  objet.traverse((o) => {
    if (masquer && o.name && masquer(o.name)) o.visible = false;
    if (tourner && o.name && tourner.filtre(o.name)) {
      o.userData.rot0 = o.userData.rot0 ?? o.rotation[tourner.axe ?? "z"];
      o.rotation[tourner.axe ?? "z"] = o.userData.rot0 + tourner.angle;
    }
  });
  if (mixer && temps !== undefined) mixer.setTime(temps);
  if (ecran) {
    // Page du site qui défile : on montre une fenêtre de la capture (largeur entière).
    const visible = Math.min(1, (860 * 2.17) / (ecran.hauteurImage || 4800));
    image.repeat.set(1, visible);
    image.offset.set(0, (1 - visible) * (1 - Math.min(1, Math.max(0, ecran.defilement))));
  }
  return <primitive object={objet} scale={taille * objet.userData.echelle} />;
};
