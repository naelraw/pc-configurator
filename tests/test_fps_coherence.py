"""Cohérence de l'estimation des FPS (audit du 1er octobre 2026)."""
import fps_data as f

CARTES = [(f"{f._canon(p)}|{v}", rel, v) for p, variants, _ in f.GPU_RELATIVE for v, rel in variants.items()]
MEILLEUR_CPU = max(v for _, v, _ in f.CPU_RELATIVE)


def _fps(jeu, carte, cpu=MEILLEUR_CPU, qualite="ultra"):
    key, rel, vram = carte
    return f.estimate_game(jeu, f.GAMES[jeu], key, rel, vram, cpu, qualite)


def test_resolution_plus_basse_jamais_plus_lente():
    for jeu in f.GAMES:
        for carte in CARTES:
            r = _fps(jeu, carte)
            assert r["1080p"]["fps"] >= r["1440p"]["fps"] >= r["4k"]["fps"], (jeu, carte[0])


def test_reglages_plus_bas_jamais_plus_lents():
    for jeu in f.GAMES:
        for carte in (CARTES[0], CARTES[len(CARTES) // 2], CARTES[-1]):
            fps = [_fps(jeu, carte, 100, q)["1440p"]["fps"] for q in ("ultra", "eleve", "moyen", "bas")]
            assert fps == sorted(fps), (jeu, carte[0], fps)


def test_meilleur_processeur_jamais_plus_lent():
    meilleure = max(CARTES, key=lambda c: c[1][1])
    cpus = sorted({v for _, v, _ in f.CPU_RELATIVE})
    for jeu in f.GAMES:
        valeurs = [_fps(jeu, meilleure, v)["1080p"]["fps"] for v in cpus]
        assert valeurs == sorted(valeurs), jeu


def test_fortnite_epique_bien_plus_lourd_que_moyen():
    """Test TechSpot en Moyen (RTX 4060 : 246 FPS) ; l'Épique doit rester réaliste."""
    carte = next(c for c in CARTES if c[0] == "rtx 4060|8")
    ultra, moyen = _fps("fortnite", carte, 126, "ultra")["1080p"]["fps"], _fps("fortnite", carte, 126, "moyen")["1080p"]["fps"]
    assert ultra < 110 and moyen > 2 * ultra


def test_surnoms_de_jeux():
    for saisie, attendu in [("valo", "valorant"), ("cod", "call of duty black ops 6"), ("hogwarts", "hogwarts legacy"),
                            ("fifa 25", "ea sports fc 26"), ("Roblox", "roblox"), ("lol", "league of legends")]:
        assert f.find_game(saisie)[0] == attendu, saisie


def test_gpu_memoire_video_de_la_fiche():
    _, rel8, v8 = f.match_gpu_full("RTX 5060 Ti", vram_go=8)
    _, rel16, v16 = f.match_gpu_full("RTX 5060 Ti", vram_go=16)
    assert (v8, v16) == (8, 16) and rel8[1] < rel16[1]
