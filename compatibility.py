def check_cpu_carte_mere(cpu, carte_mere):
	if "socket" not in cpu or "socket" not in carte_mere:
		return True, "OK"
	if cpu["socket"] != carte_mere["socket"]:
		return False, "Le socket du CPU ne correspond pas à la carte mère."
	return True, "OK"


def check_carte_mere_ram(carte_mere, ram):
	if "ram_type" not in carte_mere or "type" not in ram:
		return True, "OK"
	if carte_mere["ram_type"] != ram["type"]:
		return False, "Le type de RAM n'est pas compatible avec la carte mère."
	return True, "OK"


def check_carte_mere_boitier(carte_mere, boitier):
	if "format" not in carte_mere or "formats_supportes" not in boitier:
		return True, "OK"
	if carte_mere["format"] not in boitier["formats_supportes"]:
		return False, "Le format de la carte mère n'est pas supporté par le boîtier."
	return True, "OK"


def check_alimentation(cpu, gpu, alimentation, marge=100):
	if "tdp" not in cpu or "wattage" not in alimentation or (gpu and "tdp" not in gpu):
		return True, "OK"
	tdp_total = cpu["tdp"] + (gpu["tdp"] if gpu else 0) + marge
	if alimentation["wattage"] < tdp_total:
		return False, f"L'alimentation ({alimentation['wattage']}W) est insuffisante (besoin estimé: {tdp_total}W)."
	return True, "OK"


def check_gpu_boitier(gpu, boitier):
	if not gpu or "longueur_mm" not in gpu or "gpu_max_length_mm" not in boitier:
		return True, "OK"
	if gpu["longueur_mm"] > boitier["gpu_max_length_mm"]:
		return False, "Le GPU est trop long pour le boîtier."
	return True, "OK"


def check_stockage(carte_mere, stockages):
	# Chaque vérification ne dépend que de sa propre donnée : une carte mère
	# dont on connaît les ports SATA mais pas les slots M.2 est quand même
	# contrôlée côté SATA.
	if any("type" not in s for s in stockages):
		return True, "OK"
	nb_nvme = sum(1 for s in stockages if s["type"] == "NVMe")
	nb_sata = sum(1 for s in stockages if s["type"] == "SATA")
	if "m2_slots" in carte_mere and nb_nvme > carte_mere["m2_slots"]:
		return False, f"Trop de disques NVMe ({nb_nvme}) pour les slots M.2 disponibles ({carte_mere['m2_slots']})."
	if "sata_ports" in carte_mere and nb_sata > carte_mere["sata_ports"]:
		return False, f"Trop de disques SATA ({nb_sata}) pour les ports disponibles ({carte_mere['sata_ports']})."
	return True, "OK"


def check_refroidissement(cpu, boitier, cooler):
	# Socket et hauteur sont vérifiés séparément : un watercooling n'a pas de
	# hauteur de ventirad, mais son socket doit quand même correspondre.
	if "socket" in cpu and "sockets_supportes" in cooler and cpu["socket"] not in cooler["sockets_supportes"]:
		return False, "Le refroidisseur ne supporte pas le socket du CPU."
	if "hauteur_mm" in cooler and "cpu_cooler_max_height_mm" in boitier and cooler["hauteur_mm"] > boitier["cpu_cooler_max_height_mm"]:
		return False, "Le refroidisseur est trop haut pour le boîtier."
	return True, "OK"


def verifier_compatibilite(
	cpu, carte_mere, ram, boitier, alimentation, gpu, stockages, cooler
):
	"""
	Chaque paramètre est un dict (specs_json déjà parsé) sauf stockages qui est
	une liste de dicts. gpu peut être None.

	Un composant peut avoir des specs incomplètes (enregistrement autorisé
	même si des champs obligatoires manquent — l'admin les complète plus
	tard). Dans ce cas, la vérification concernée est silencieusement
	ignorée (ni erreur, ni "compatible" affirmé) plutôt que de planter :
	mieux vaut ne rien dire que de crasher toute la page, mais on ne
	prétend jamais une compatibilité qu'on n'a pas pu vérifier.

	Retourne une liste d'erreurs (vide = tout compatible, ou pas assez
	d'infos pour dire le contraire).
	"""
	erreurs = []

	checks = [
		check_cpu_carte_mere(cpu, carte_mere),
		check_carte_mere_ram(carte_mere, ram),
		check_carte_mere_boitier(carte_mere, boitier),
		check_alimentation(cpu, gpu, alimentation),
		check_gpu_boitier(gpu, boitier),
		check_stockage(carte_mere, stockages),
		check_refroidissement(cpu, boitier, cooler),
	]

	for ok, message in checks:
		if not ok:
			erreurs.append(message)

	return erreurs
