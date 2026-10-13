"""Inspecte les modèles GLB : crédits (auteur, licence), taille, maillages, matériaux."""
import json, struct, sys, glob, os

def lire(chemin):
    with open(chemin, "rb") as f:
        magic, version, longueur = struct.unpack("<III", f.read(12))
        taille, genre = struct.unpack("<II", f.read(8))
        return json.loads(f.read(taille))

for chemin in sorted(glob.glob("public/modeles/*.glb")):
    g = lire(chemin)
    ex = g.get("asset", {}).get("extras", {})
    mn = [float("inf")] * 3; mx = [float("-inf")] * 3
    for acc in g.get("accessors", []):
        if acc.get("type") == "VEC3" and "min" in acc and acc.get("max"):
            for i in range(3):
                mn[i] = min(mn[i], acc["min"][i]); mx[i] = max(mx[i], acc["max"][i])
    print(f"\n=== {os.path.basename(chemin)} ({os.path.getsize(chemin)//1024} Ko)")
    print("  titre :", ex.get("title"), "| auteur :", ex.get("author"), "| licence :", ex.get("license"))
    print("  source :", ex.get("source"))
    print("  maillages :", len(g.get("meshes", [])), "| noeuds :", len(g.get("nodes", [])), "| matériaux :", len(g.get("materials", [])), "| textures :", len(g.get("textures", [])))
    print("  matériaux :", ", ".join(m.get("name", "?") for m in g.get("materials", []))[:400])
    noms = [n.get("name", "") for n in g.get("nodes", []) if n.get("name")]
    print("  noeuds :", ", ".join(noms[:40])[:500])
    print("  boîte (brute, sans transformations) :", [round(a, 2) for a in mn], [round(b, 2) for b in mx])
