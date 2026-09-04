from compatibility import verifier_compatibilite


cpu = {"socket": "AM4", "tdp": 65}
carte_mere = {
	"socket": "AM5",
	"format": "mATX",
	"ram_type": "DDR4",
	"m2_slots": 2,
	"sata_ports": 4,
}
ram = {"type": "DDR4"}
boitier = {
	"formats_supportes": ["ATX", "mATX"],
	"gpu_max_length_mm": 320,
	"cpu_cooler_max_height_mm": 165,
}
alimentation = {"wattage": 550}
gpu = {"tdp": 220, "longueur_mm": 300}
stockages = [{"type": "NVMe"}]
cooler = {"sockets_supportes": ["AM4", "AM5"], "hauteur_mm": 158}

erreurs = verifier_compatibilite(
	cpu,
	carte_mere,
	ram,
	boitier,
	alimentation,
	gpu,
	stockages,
	cooler,
)

if erreurs:
	print("❌ Config incompatible :")
	for erreur in erreurs:
		print(" -", erreur)
else:
	print("✅ Config compatible")
