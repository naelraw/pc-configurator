"""Étape 10 : dimensions physiques relevées sur les fiches des fabricants
(jamais les « Dimensions de l'article » d'Amazon, qui mesurent souvent le carton).
Usage : python fix_dimensions_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)

Chaque ligne donne l'id, un bout du nom attendu (garde-fou contre un mauvais id)
et les valeurs à écrire. Une valeur déjà en base et différente est signalée et
remplacée : les fiches fabricant font foi."""
import json, sqlite3, sys

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv

# Boîtiers : longueur GPU max / hauteur ventirad max (mm), fiches fabricant.
BOITIERS = {
    2598: ("Prime AP202", 420, 175),            # asus.com techspec
    2824: ("GT502 Horizon", 400, 163),          # asus.com techspec
    2832: ("GT502 Plus", 400, 163),             # asus.com techspec
    2828: ("GT502 Plus", 400, 163),
    2592: ("3200D RS", 400, 165),               # corsair.com
    2587: ("3500X LX-R", 425, 170),             # corsair.com
    2591: ("3500X RS-R", 425, 170),             # corsair.com
    2593: ("AIR 5400", 360, 180),               # corsair.com
    2586: ("4000D RS", 430, 170),               # corsair.com
    2589: ("4500X", 460, 185),                  # corsair.com
    2588: ("4000D", 430, 170),                  # corsair.com
    2594: ("4000D Wood", 430, 170),             # corsair.com
    2590: ("4500X", 460, 185),
    2871: ("North XL", 413, 185),               # fractal-design.com
    2870: ("O11 Dynamic Mini V2", 400, 160),    # lian-li.com
    2579: ("Forge 100M", 330, 160),             # msi.com (toutes les fiches MSI)
    2578: ("Forge 100R", 330, 160),
    2599: ("Forge 110R", 330, 160),
    2576: ("Forge 112R", 330, 160),
    2577: ("Forge 120A", 330, 160),
    2869: ("Forge 320R", 390, 160),
    2584: ("Forge 320R", 390, 160),
    2581: ("Forge 321R", 390, 160),
    2585: ("Forge M100R", 300, 160),
    2580: ("PANO 100R", 400, 166),
    2574: ("PANO 110R", 400, 160),
    2575: ("PANO M100L", 390, 175),
    2583: ("GUNGNIR 300R", 360, 175),
    2582: ("Gungnir 110R", 340, 165),
    2873: ("MC-CURV", 334, 165),                # marsgaming.eu
    2867: ("MC-VIEW3", 330, 155),               # marsgaming.eu
    2597: ("H3 Flow", 352, 170),                # nzxt.com (avec ventilateurs en façade)
    2596: ("H5 Flow", 410, 170),                # nzxt.com
    2875: ("H6 Flow", 365, 163),                # nzxt.com
    2872: ("H6 Flow", 365, 163),
    2868: ("A70", 420, 168),                    # thermalright.com (168,4)
    2595: ("A70", 420, 168),
}

UPDATES = {cid: (nom, {"gpu_max_length_mm": g, "cpu_cooler_max_height_mm": h})
           for cid, (nom, g, h) in BOITIERS.items()}

# Valeurs fausses déjà en base (souvent la taille du carton Amazon), corrigées
# d'après la fiche fabricant. Longueur GPU = carte avec équerre quand le
# fabricant donne les deux (c'est ce qui compte dans le boîtier).
UPDATES.update({
    2487: ("RX 9070 Challenger", {"longueur_mm": 290}),      # asrock.com (400 = carton)
    2517: ("Swift RX 9060 XT 8", {"longueur_mm": 290}),      # xfxforce.com, RX-96TS38GB7 triple ventilateur (406 = carton)
    2299: ("Phoenix GeForce RTX 3050 V2", {"longueur_mm": 178}),  # asus.com (123 = largeur)
    2432: ("3090 Gaming X Trio", {"longueur_mm": 323}),      # msi.com
    2503: ("Quicksilver", {"longueur_mm": 350}),             # xfxforce.com
    2135: ("B850 Steel Legend", {"m2_slots": 4, "sata_ports": 4}),   # asrock.com (24 SATA : erreur)
    2164: ("Z890-E", {"m2_slots": 7, "sata_ports": 4}),      # rog.asus.com (1 SATA : erreur)
    2107: ("A520M-A PRO", {"m2_slots": 1, "sata_ports": 4}),        # msi.com
    2085: ("B550-A Pro", {"m2_slots": 2, "sata_ports": 6}),         # msi.com
    2078: ("B850M Gaming Plus", {"m2_slots": 2, "sata_ports": 4}),  # msi.com
    2090: ("B850M Mortar", {"m2_slots": 3, "sata_ports": 4}),       # msi.com
    2186: ("TUF Gaming B650-Plus", {"m2_slots": 3, "sata_ports": 4}),  # asus.com
})

# Lot 2 : longueur des cartes graphiques (mm), fiches fabricant (msi.com, gigabyte.com,
# asus.com, sapphiretech.com, xfxforce.com, asrock.com, powercolor.com, palit.com,
# gainward.com, brochures PDF pny.com, nvidia.com). Cote avec équerre quand donnée ;
# arrondie au mm. Garde-fou : début exact du nom en base.
GPUS = {
    2300: ("ASUS Dual GeForce RTX 305", 201),
    2301: ("MSI GeForce RTX 3050 LP E", 174),
    2302: ("MSI GeForce RTX 3050 Vent", 189),
    2303: ("MSI GeForce RTX 3050 Vent", 189),
    2304: ("ASUS GeForce RTX 3050 LP ", 182),
    2305: ("MSI GeForce RTX 3050 LP 6", 174),
    2307: ("PNY GeForce RTX 5050 8Go ", 200),
    2309: ("GIGABYTE GeForce RTX 3050", 191),
    2310: ("MSI GeForce RTX 5060 Ti 8", 226),
    2311: ("MSI GeForce RTX 3050 Vent", 205),
    2312: ("ASUS Prime GeForce RTX 50", 304),
    2314: ("GIGABYTE Radeon RX 9070 X", 288),
    2316: ("ASUS Dual GeForce RTX 305", 200),
    2317: ("MSI GeForce RTX 5070 12G ", 236),
    2318: ("MSI Gaming RTX 3050 Ventu", 189),
    2319: ("ASUS Dual Radeon RX 7600 ", 229),
    2320: ("MSI GeForce RTX 5080 16 G", 288),
    2322: ("ASUS Phoenix GeForce RTX ", 177),
    2324: ("GIGABYTE GeForce RTX 5050", 199),
    2325: ("ASUS Dual GeForce RTX 306", 200),
    2326: ("MSI GeForce RTX 5070 12G ", 302),
    2327: ("ASUS Dual GeForce RTX 506", 229),
    2328: ("MSI GeForce RTX 5060 8G V", 197),
    2329: ("Gigabyte GeForce RTX 3060", 198),
    2330: ("MSI GeForce RTX 5060 Shad", 197),
    2331: ("Sapphire Pulse AMD Radeon", 240),
    2332: ("ASUS Prime GeForce RTX 50", 268),
    2333: ("GIGABYTE GeForce RTX 5060", 199),
    2334: ("ASUS Dual GeForce RTX 506", 228),
    2335: ("Gigabyte RTX 3060 Gaming ", 282),
    2336: ("PNY GeForce RTX 5060 8Go ", 200),
    2337: ("Gigabyte GeForce RTX 3060", 198),
    2338: ("GIGABYTE GeForce RTX 5070", 324),
    2339: ("ASUS Prime GeForce RTX 50", 268),
    2340: ("GIGABYTE Radeon RX 9060 X", 281),
    2341: ("GIGABYTE GeForce RTX 5050", 280),
    2343: ("ASUS TUF Gaming GeForce R", 302),
    2344: ("Palit RTX 3070 Ti GamingP", 294),
    2345: ("NVIDIA GeForce RTX 3070 F", 242),
    2346: ("GIGABYTE GeForce RTX 5070", 327),
    2347: ("ASUS Dual GeForce RTX 505", 203),
    2348: ("MSI GeForce RTX 5060 Ti G", 300),
    2349: ("ASUS ROG Strix GeForce RT", 318),
    2351: ("GIGABYTE GeForce RTX 3070", 282),
    2352: ("ASUS Dual GeForce RTX 506", 228),
    2353: ("Gigabyte GeForce RTX 3070", 282),
    2354: ("MSI GeForce RTX 5060 Gami", 248),
    2355: ("PNY GeForce RTX 5060 8Go ", 280),
    2356: ("GIGABYTE GeForce RTX 5060", 208),
    2357: ("Gigabyte AORUS GeForce RT", 290),
    2358: ("MSI RTX 3070 Ti Ventus 3X", 305),
    2359: ("GIGABYTE GeForce RTX 3070", 286),
    2360: ("ASUS Prime Radeon RX 9070", 312),
    2361: ("ASUS Dual GeForce RTX 506", 229),
    2362: ("ASUS TUF Gaming GeForce R", 300),
    2363: ("MSI GeForce RTX 5070 Gami", 338),
    2364: ("MSI GeForce RTX 5070 Ti 1", 338),
    2365: ("MSI GeForce RTX 5080 16G ", 303),
    2366: ("MSI GeForce RTX 5070 Shad", 231),
    2367: ("ASUS GeForce RTX 4070 Sup", 227),
    2368: ("PNY GeForce RTX 5070 Ti 1", 300),
    2369: ("MSI GeForce RTX 5080 16G ", 338),
    2370: ("ASUS ROG Strix GeForce RT", 318),
    2371: ("GIGABYTE AORUS GeForce RT", 319),
    2372: ("GIGABYTE AORUS Radeon RX ", 339),
    2373: ("NVIDIA GeForce RTX 3080 F", 285),
    2374: ("GIGABYTE AORUS Xtreme GeF", 319),
    2375: ("ASUS TUF Gaming GeForce R", 348),
    2376: ("GIGABYTE GeForce RTX 5080", 340),
    2377: ("ASUS Prime GeForce RTX 50", 304),
    2378: ("ASUS TUF Gaming GeForce R", 348),
    2379: ("ASUS ROG Astral GeForce R", 358),
    2380: ("MSI GeForce RTX 5080 16G ", 303),
    2381: ("MSI GeForce RTX 5070 Ti 1", 303),
    2382: ("MSI GeForce RTX 4080 16GB", 337),
    2383: ("ASUS Prime GeForce RTX 50", 304),
    2384: ("Palit GeForce RTX 4080 Ga", 329),
    2385: ("PNY GeForce RTX 5080 16Go", 329),
    2386: ("GIGABYTE GeForce RTX 4080", 342),
    2387: ("GIGABYTE GeForce RTX 4080", 330),
    2388: ("GIGABYTE GeForce RTX 4080", 342),
    2389: ("ASUS Prime GeForce RTX 50", 304),
    2390: ("GIGABYTE GeForce RTX 4080", 342),
    2391: ("ASUS Prime Radeon RX 9060", 304),
    2392: ("ASUS TUF Gaming GeForce R", 348),
    2393: ("MSI GeForce RTX 5080 16G ", 303),
    2394: ("ASUS ROG Strix GeForce RT", 358),
    2396: ("ASUS ProArt GeForce RTX 5", 304),
    2397: ("GIGABYTE AORUS GeForce RT", 330),
    2398: ("NVIDIA GeForce RTX 4080 F", 304),
    2399: ("GIGABYTE GeForce RTX 5060", 208),
    2400: ("MSI GeForce RTX 5060 Ti 1", 227),
    2401: ("GIGABYTE GeForce RTX 5050", 201),
    2402: ("ASUS Dual GeForce RTX 506", 229),
    2404: ("GIGABYTE GeForce RTX 5050", 182),
    2405: ("PNY GeForce RTX 5070 Ti 1", 300),
    2406: ("Gigabyte GeForce RTX 4060", 192),
    2407: ("ASRock Radeon RX 7600 Ste", 303),
    2408: ("Sapphire Pulse AMD Radeon", 244),
    2409: ("Sapphire Pulse AMD Radeon", 240),
    2410: ("MSI GeForce RTX 4060 Vent", 199),
    2411: ("XFX Speedster SWFT210 Rad", 241),
    2414: ("GIGABYTE RTX 3090 Gaming ", 320),
    2415: ("ASUS ROG Strix RTX 3090 O", 318),
    2416: ("MSI GeForce RTX 3090 SUPR", 336),
    2417: ("ASUS ROG Astral GeForce R", 358),
    2418: ("ASUS TUF Gaming GeForce R", 300),
    2419: ("ASUS ROG Strix GeForce RT", 318),
    2420: ("NVIDIA GeForce RTX 3090 F", 313),
    2421: ("Sapphire Pulse AMD Radeon", 320),
    2422: ("Sapphire Nitro+ AMD Radeo", 331),
    2424: ("Sapphire Pure AMD Radeon ", 320),
    2425: ("ASUS TUF Gaming GeForce R", 300),
    2426: ("ASUS Prime Radeon RX 9070", 312),
    2427: ("ASUS ROG Strix GeForce RT", 318),
    2428: ("PNY GeForce RTX 5080 16Go", 329),
    2430: ("MSI RTX 5090 Ventus 3X OC", 325),
    2431: ("Nvidia RTX 3090 Ti Founde", 313),
    2433: ("MSI GeForce RTX 5090 Gami", 359),
    2434: ("ASUS TUF Gaming GeForce R", 300),
    2435: ("ASUS TUF Gaming GeForce R", 348),
    2436: ("Sapphire Nitro+ AMD Radeo", 331),
    2437: ("GIGABYTE GeForce RTX 3090", 320),
    2440: ("MSI Gaming RTX 5050 8G Sh", 197),
    2441: ("ASUS Dual GeForce RTX 505", 203),
    2442: ("GIGABYTE GeForce RTX 5050", 145),
    2444: ("Palit GeForce RTX 5050 St", 170),
    2445: ("Gainward RTX 5050 Ghost 8", 262),
    2448: ("ASUS Dual GeForce RTX 505", 203),
    2449: ("MSI Gaming RTX 5060 8G Ve", 197),
    2450: ("ASUS TUF Gaming GeForce R", 302),
    2451: ("ASUS Dual GeForce RTX 506", 228),
    2453: ("GIGABYTE GeForce RTX 5060", 215),
    2454: ("GIGABYTE GeForce RTX 5060", 208),
    2455: ("Palit GeForce RTX 5060 Ti", 262),
    2456: ("GIGABYTE GeForce RTX 5060", 208),
    2457: ("GIGABYTE GeForce RTX 5060", 208),
    2458: ("MSI RTX 5060 Ti 8G Ventus", 227),
    2461: ("GIGABYTE GeForce RTX 5070", 290),
    2462: ("PNY GeForce RTX 5070 Ti O", 300),
    2463: ("GIGABYTE GeForce RTX 5070", 290),
    2464: ("Sapphire Pulse AMD Radeon", 280),
    2466: ("Palit RTX 5070 Infinity 3", 292),
    2467: ("ASUS Prime GeForce RTX 50", 304),
    2468: ("GIGABYTE AORUS GeForce RT", 317),
    2469: ("MSI GeForce RTX 5070 12G ", 236),
    2470: ("GIGABYTE GeForce RTX 5070", 304),
    2471: ("XFX Swift AMD Radeon RX 9", 270),
    2472: ("PNY GeForce RTX 5070 Over", 300),
    2473: ("PNY GeForce RTX 5080 16GB", 329),
    2476: ("Palit GeForce RTX 5080 In", 332),
    2477: ("ASUS ROG Astral GeForce R", 358),
    2478: ("ASUS TUF Gaming RTX 5080 ", 348),
    2479: ("Palit GeForce RTX 5080 Ga", 332),
    2480: ("MSI RTX 5080 Ventus 3X OC", 303),
    2481: ("MSI RTX 5080 16G Gaming T", 338),
    2482: ("MSI RTX 5090 Gaming Trio ", 359),
    2483: ("GIGABYTE GeForce RTX 5090", 342),
    2485: ("GIGABYTE Radeon RX 9070 G", 288),
    2486: ("ASUS Prime Radeon RX 9070", 312),
    2487: ("ASRock AMD Radeon RX 9070", 290),
    2488: ("XFX Swift RX 9070 16 Go G", 325),
    2489: ("XFX RX 9070 Swift 16GB", 290),
    2490: ("XFX Swift AMD Radeon RX 9", 325),
    2491: ("XFX Swift AMD Radeon RX 9", 301),
    2492: ("Sapphire Nitro+ RX 9070 1", 331),
    2493: ("ASUS Prime RX 9070 GRE 12", 304),
    2494: ("GIGABYTE Radeon RX 9070 G", 288),
    2495: ("Sapphire Pure RX 9070 16G", 320),
    2497: ("XFX Swift RX 9070 XT 16 G", 325),
    2498: ("GIGABYTE Radeon RX 9070 X", 288),
    2499: ("ASUS TUF Gaming Radeon RX", 330),
    2500: ("XFX Quicksilver AMD Radeo", 350),
    2501: ("XFX Swift Radeon RX 9070 ", 325),
    2502: ("PowerColor RX 9070 Reaper", 289),
    2503: ("XFX Quicksilver AMD Radeo", 350),
    2504: ("XFX Swift RX 9060 XT 8 Go", 270),
    2505: ("ASUS Dual Radeon RX 9060 ", 202),
    2506: ("ASRock Radeon RX 9060 XT ", 249),
    2507: ("Sapphire Radeon RX 9060 X", 240),
    2508: ("XFX Swift Radeon RX 9060 ", 290),
    2509: ("XFX Swift RX 9060 XT 16 G", 290),
    2510: ("XFX Swift RX 9060 XT 16GB", 270),
    2511: ("GIGABYTE Radeon RX 9060 X", 281),
    2512: ("ASUS Prime Radeon RX 9060", 304),
    2513: ("PowerColor RX 9060 XT Rea", 200),
    2514: ("PowerColor Reaper RX 9060", 200),
    2515: ("ASUS Dual Radeon RX 9060 ", 202),
    2516: ("PowerColor Hellhound RX 9", 310),
    2518: ("ASUS Dual Radeon RX 9060 ", 202),
    2519: ("GIGABYTE Radeon RX 9060 X", 281),
    2520: ("Sapphire Pulse RX 9060 XT", 240),
    2521: ("Powercolor Hellhound RX 9", 310),
    2522: ("PowerColor Hellhound Spec", 310),
    2523: ("XFX Swift RX 9070 GRE 12 ", 301),
    2524: ("XFX Mercury RX 9060 XT 16", 320),
    2525: ("XFX Radeon RX 7900 XT 20G", 276),
    2526: ("XFX Qicksilver RX 7800 XT", 337),
    2527: ("XFX Radeon RX 7900 GRE 16", 335),
    2528: ("Sapphire Pulse RX 7900 XT", 313),
    2530: ("XFX Mercury Radeon RX 907", 360),
    2531: ("ASRock Taichi RX 9070 XT ", 330),
    2532: ("Gigabyte Radeon RX 7600 G", 282),
    2533: ("ASRock Steel Legend AMD R", 298),
    2534: ("GIGABYTE Radeon RX 7800 X", 302),
    2535: ("XFX Speedster QICK309 RX ", 302),
    2536: ("XFX Speedster SWFT210 Rad", 241),
    2537: ("Sapphire Pulse Radeon RX ", 280),
    2538: ("Sapphire Nitro+ RX 6800 X", 310),
    2539: ("Sapphire Pulse Radeon RX ", 280),
    2540: ("ASUS Dual RX 7700XT 12 Go", 280),
    2541: ("ASRock Challenger RX 7600", 269),
    2542: ("ASRock Phantom Gaming RX ", 328),
    2543: ("XFX Speedster QICK 319 AM", 323),
    2544: ("XFX Speedster SWFT210 RX ", 241),
    2545: ("MSI Radeon RX 6750 XT Gam", 327),
    2546: ("GIGABYTE Radeon RX 6500 X", 192),
    2547: ("PowerColor Hellhound Rade", 223),
    2548: ("MSI Radeon RX 7600 Mech 2", 235),
    2549: ("ASRock Phantom Gaming RX ", 240),
    2550: ("Sapphire Nitro+ Radeon RX", 320),
    2551: ("ASRock Radeon RX 6900 XT ", 330),
    2552: ("GIGABYTE Aorus Master Rad", 322),
    2553: ("MSI Radeon RX 6900 XT Gam", 324),
    2554: ("GIGABYTE Radeon RX 6900 X", 286),
    2555: ("Sapphire Pulse AMD Radeon", 303),
    2556: ("ASUS TUF Gaming Radeon RX", 320),
    2557: ("XFX Speedster SWFT 319 AM", 340),
    2558: ("Sapphire Pulse Radeon RX ", 280),
    2559: ("MSI Radeon RX 6500 XT Mec", 172),
    2560: ("MSI Radeon RX 6750 XT Mec", 249),
    2561: ("ASUS TUF Gaming GeForce R", 305),
    2562: ("PowerColor Fighter Radeon", 191),
    2563: ("MSI RX 6700 XT Gaming X 1", 279),
    2564: ("Gigabyte Radeon RX 6700 X", 281),
    2565: ("GIGABYTE AMD Radeon RX 66", 282),
    2566: ("Gigabyte Radeon RX 6500 X", 282),
    2567: ("Powercolor Red Devil OC R", 320),
    2568: ("Sapphire Pulse AMD Radeon", 240),
    2569: ("MSI Radeon RX 6650 XT Mec", 235),
    2570: ("MSI RX 6600 Mech 2X 8G 91", 235),
    2571: ("GIGABYTE Radeon RX 6400 E", 192),
    2572: ("PowerColor Hellhound Rade", 220),
    2573: ("Gigabyte Radeon RX 6500 X", 192),
}
for cid, (nom, longueur) in GPUS.items():
    UPDATES.setdefault(cid, (nom, {}))[1]["longueur_mm"] = longueur

changes, problems = [], []
for cid, (expected, values) in UPDATES.items():
    r = db.execute("select nom, specs_json from components where id=?", (cid,)).fetchone()
    if not r or expected.lower() not in r[0].lower():
        problems.append(f"{cid} : attendu « {expected} », trouvé {r[0] if r else 'rien'} -> ignoré")
        continue
    specs = json.loads(r[1] or "{}")
    diff = {k: v for k, v in values.items() if specs.get(k) != v}
    if not diff:
        continue
    note = ", ".join(f"{k} {specs[k]} -> {v}" if k in specs else f"{k} = {v}" for k, v in diff.items())
    changes.append(f"{cid} | {r[0][:50]} | {note}")
    if APPLY:
        db.execute("update components set specs_json=? where id=?",
                   (json.dumps({**specs, **diff}, ensure_ascii=False), cid))

for c in changes: print(c)
for p in problems: print("!!", p)
print(f"\n{len(changes)} fiche(s) {'MODIFIÉE(S)' if APPLY else 'à modifier (simulation, rien écrit)'}, {len(problems)} ignorée(s)")
if APPLY: db.commit()
