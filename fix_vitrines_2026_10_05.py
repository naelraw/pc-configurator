"""Repère les fiches « vitrine » (plus d'offre Amazon directe, seulement
« Voir toutes les offres ») parmi les produits en stock, avec Bright Data, et
les marque épuisées comme le ferait la mise à jour de nuit (2026-10-05).
Lister seulement : sans --appliquer (les appels Bright Data sont faits quand même)."""
import json, sqlite3, sys
import main

APPLIQUER = "--appliquer" in sys.argv
db = sqlite3.connect("data/pcradar.db")
rows = db.execute("SELECT id, nom, asin, prix_marche_json, image_url, en_stock FROM components "
                  "WHERE en_stock = 1 AND asin IS NOT NULL AND asin != '' ORDER BY id").fetchall()
print(len(rows), "produits en stock à vérifier", flush=True)
vitrines, erreurs = [], 0
client = main.get_client()
try:
    for i in range(0, len(rows), 50):
        lot = rows[i:i + 50]
        try:
            res = main._brightdata_scrape_sync([{"url": f"https://www.amazon.fr/dp/{r[2]}"} for r in lot], timeout=280)
        except Exception as e:
            print("lot en échec :", e, flush=True); erreurs += len(lot); continue
        par_asin, redirections = main._indexer_resultats_brightdata(res)
        for cid, nom, asin, pm, img, stock in lot:
            item = par_asin.get(asin.upper())
            if item is None or item.get("is_available") is not False:
                continue
            vitrines.append((cid, nom, asin))
            print(f"  vitrine : {cid} {nom[:60]} ({asin})", flush=True)
            if APPLIQUER:
                main._marquer_vitrine(cid, True)
                main._apply_amazon_price_info(client, cid, nom, asin, pm, img, True, {"prix": None}, source_label="Bright Data")
        print(f"... {min(i + 50, len(rows))}/{len(rows)} vérifiés, {len(vitrines)} vitrines", flush=True)
finally:
    client.close()
if APPLIQUER:
    main.invalidate_catalog()
print("TERMINÉ :", len(vitrines), "vitrines", "(marquées épuisées)" if APPLIQUER else "(simulation)", "| lots en échec :", erreurs)
json.dump(vitrines, open("/tmp/vitrines-2026-10-05.json", "w"), ensure_ascii=False)
