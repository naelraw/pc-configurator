def check_cpu_carte_mere(cpu, carte_mere):
	if cpu["socket"] != carte_mere["socket"]:
		return False, "Le socket du CPU ne correspond pas à la carte mère."
	return True, "OK"


def check_carte_mere_ram(carte_mere, ram):
	if carte_mere["ram_type"] != ram["type"]:
		return False, "Le type de RAM n'est pas compatible avec la carte mère."
	return True, "OK"


def check_carte_mere_boitier(carte_mere, boitier):
	if carte_mere["format"] not in boitier["formats_supportes"]:
		return False, "Le format de la carte mère n'est pas supporté par le boîtier."
	return True, "OK"


def check_alimentation(cpu, gpu, alimentation, marge=100):
	tdp_total = cpu["tdp"] + (gpu["tdp"] if gpu else 0) + marge
	if alimentation["wattage"] < tdp_total:
		return False, f"L'alimentation ({alimentation['wattage']}W) est insuffisante (besoin estimé: {tdp_total}W)."
	return True, "OK"


def check_gpu_boitier(gpu, boitier):
	if gpu and gpu["longueur_mm"] > boitier["gpu_max_length_mm"]:
		return False, "Le GPU est trop long pour le boîtier."
	return True, "OK"


def check_stockage(carte_mere, stockages):
	nb_nvme = sum(1 for s in stockages if s["type"] == "NVMe")
	nb_sata = sum(1 for s in stockages if s["type"] == "SATA")
	if nb_nvme > carte_mere["m2_slots"]:
		return False, f"Trop de disques NVMe ({nb_nvme}) pour les slots M.2 disponibles ({carte_mere['m2_slots']})."
	if nb_sata > carte_mere["sata_ports"]:
		return False, f"Trop de disques SATA ({nb_sata}) pour les ports disponibles ({carte_mere['sata_ports']})."
	return True, "OK"


def check_refroidissement(cpu, boitier, cooler):
	if cpu["socket"] not in cooler["sockets_supportes"]:
		return False, "Le refroidisseur ne supporte pas le socket du CPU."
	if cooler["hauteur_mm"] > boitier["cpu_cooler_max_height_mm"]:
		return False, "Le refroidisseur est trop haut pour le boîtier."
	return True, "OK"


def verifier_compatibilite(
	cpu, carte_mere, ram, boitier, alimentation, gpu, stockages, cooler
):
	"""
	Chaque paramètre est un dict (specs_json déjà parsé) sauf stockages qui est
	une liste de dicts. gpu peut être None.
	Retourne une liste d'erreurs (vide = tout compatible).
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
