"""Voix off de la vidéo : un fichier par plan + le moment de chaque mot (sous-titres).

Voix neuronale Microsoft (service de lecture à voix haute d'Edge), via edge-tts.
Usage : python voix.py   ->  public/voix/planN.mp3 et src/voix.json
"""
import asyncio
import json
import os

import edge_tts

VOIX = "fr-FR-HenriNeural"
DEBIT = "+8%"
PLANS = [
    "Monter son PC, c'est une dizaine de pièces. Et une seule erreur suffit.",
    "Un processeur sur le mauvais socket. Une alimentation trop faible. Une carte graphique trop longue pour le boîtier.",
    "PC Radar vérifie tout, à ta place.",
    "Choisis tes pièces : chacune est contrôlée avec les autres, et le total s'affiche au prix du jour.",
    "Pas envie de chercher ? Décris ton besoin à l'assistant IA. Il te propose une config complète, adaptée à ton budget.",
    "Les prix sont relevés plusieurs fois par jour, sur près de mille composants, avec tout leur historique.",
    "Suis un composant : un e-mail te prévient dès que son prix baisse. Et avant d'acheter, découvre tes FPS sur tes jeux.",
    "PC Radar, c'est gratuit. Rendez-vous sur pcradar point tech.",
]


async def un_plan(i, texte):
    # Le service refuse parfois une connexion (403 passager) : quelques essais espacés.
    for essai in range(6):
        try:
            return await _un_plan(i, texte)
        except Exception as err:
            print(f"plan {i} : essai {essai + 1} refusé ({str(err)[:40]}), nouvel essai...")
            await asyncio.sleep(4 + essai * 4)
    raise RuntimeError(f"plan {i} : voix impossible")


async def _un_plan(i, texte):
    mots = []
    chemin = f"public/voix/plan{i}.mp3"
    com = edge_tts.Communicate(texte, VOIX, rate=DEBIT, boundary="WordBoundary")
    with open(chemin, "wb") as f:
        async for morceau in com.stream():
            if morceau["type"] == "audio":
                f.write(morceau["data"])
            elif morceau["type"] == "WordBoundary":
                # Décalage et durée en centaines de nanosecondes.
                mots.append({"mot": morceau["text"], "debut": morceau["offset"] / 1e7,
                             "fin": (morceau["offset"] + morceau["duration"]) / 1e7})
    return {"fichier": f"voix/plan{i}.mp3", "texte": texte, "mots": mots, "fin_voix": mots[-1]["fin"] if mots else 0}


async def main():
    os.makedirs("public/voix", exist_ok=True)
    plans = []
    for i, t in enumerate(PLANS):
        plans.append(await un_plan(i + 1, t))
        await asyncio.sleep(1.5)
    with open("src/voix.json", "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=1)
    for p in plans:
        print(f"{p['fichier']} : {p['fin_voix']:.2f} s, {len(p['mots'])} mots")


asyncio.run(main())
