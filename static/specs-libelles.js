// Libellés lisibles des caractéristiques (clés brutes en base, ex.
// « connecteur_12v_2x6 ») pour les cartes et fenêtres de détail.
//   PCSpecs.libelle(cle)            -> « Câble 16 broches natif »
//   PCSpecs.valeur(cle, valeur)     -> « 1 200 W », « 5,2 GHz », « AM4, AM5 »
//   PCSpecs.resume(composant, max)  -> « 1 200 W · 80 PLUS Titanium · Modulaire »
(function(){
  const LIBELLES = {
    socket: 'Socket', tdp: 'Consommation', wattage: 'Puissance', format: 'Format',
    ram_type: 'Mémoire', type: 'Type', m2_slots: 'Emplacements M.2', sata_ports: 'Ports SATA',
    formats_supportes: 'Cartes mères acceptées', gpu_max_length_mm: 'Carte graphique max.',
    cpu_cooler_max_height_mm: 'Ventirad max.', longueur_mm: 'Longueur', hauteur_mm: 'Hauteur',
    sockets_supportes: 'Sockets', couleur: 'Couleur', coeurs: 'Cœurs', threads: 'Threads',
    frequence_base_ghz: 'Fréquence de base', frequence_boost_ghz: 'Fréquence boost', cache_l3_mo: 'Cache L3',
    memoire: 'Mémoire', igpu: 'Graphique intégré', puce: 'Puce graphique', vram_go: 'Mémoire vidéo',
    type_memoire: 'Type de mémoire vidéo', bus_memoire_bits: 'Bus mémoire', chipset: 'Chipset',
    capacite_go: 'Capacité', frequence_mt_s: 'Fréquence', barrettes: 'Barrettes', latence_cl: 'Latence',
    interface: 'Interface', lecture_mo_s: 'Lecture', ecriture_mo_s: 'Écriture',
    certification: 'Certification', modularite: 'Câbles', format_alim: 'Format',
    connecteur_12v_2x6: 'Câble 16 broches natif', norme_atx: 'Norme', type_refroidissement: 'Type',
    radiateur_mm: 'Radiateur', ventilateurs: 'Ventilateurs', ventilateurs_inclus: 'Ventilateurs fournis',
    radiateur_max_mm: 'Radiateur max.', slots_ram: 'Emplacements RAM', wifi: 'Wi-Fi',
    connecteur_alim: 'Alimentation', tdp_max_w: 'TDP max.',
  };
  const UNITES = {
    tdp: ' W', wattage: ' W', gpu_max_length_mm: ' mm', cpu_cooler_max_height_mm: ' mm', longueur_mm: ' mm',
    hauteur_mm: ' mm', frequence_base_ghz: ' GHz', frequence_boost_ghz: ' GHz', cache_l3_mo: ' Mo',
    vram_go: ' Go', bus_memoire_bits: ' bits', capacite_go: ' Go', frequence_mt_s: ' MT/s',
    lecture_mo_s: ' Mo/s', ecriture_mo_s: ' Mo/s', radiateur_mm: ' mm', radiateur_max_mm: ' mm', tdp_max_w: ' W',
  };
  // Les caractéristiques qui comptent le plus, par catégorie (cartes du configurateur).
  const ESSENTIELLES = {
    'CPU': ['socket', 'coeurs', 'frequence_boost_ghz', 'tdp'],
    'GPU': ['vram_go', 'type_memoire', 'tdp', 'longueur_mm'],
    'Carte mère': ['socket', 'chipset', 'ram_type', 'format', 'wifi'],
    'RAM': ['capacite_go', 'type', 'frequence_mt_s', 'latence_cl'],
    'Stockage': ['capacite_go', 'type', 'interface', 'lecture_mo_s'],
    'Alimentation': ['wattage', 'certification', 'modularite', 'format_alim'],
    'Boîtier': ['formats_supportes', 'gpu_max_length_mm', 'cpu_cooler_max_height_mm', 'ventilateurs_inclus'],
    'Refroidissement': ['type_refroidissement', 'radiateur_mm', 'hauteur_mm', 'sockets_supportes'],
  };

  const nombre = v => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 });

  function libelle(cle){
    return LIBELLES[cle] || String(cle).replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
  }

  function valeur(cle, v){
    if(Array.isArray(v)) return v.join(', ');
    if(typeof v === 'boolean') return v ? 'Oui' : 'Non';
    if(cle === 'capacite_go' && Number(v) >= 1000) return `${nombre(v / 1000)} To`;
    if(cle === 'latence_cl') return `CL${v}`;
    if(typeof v === 'number' || (/^\d+([.,]\d+)?$/.test(String(v)) && UNITES[cle])) return nombre(String(v).replace(',', '.')) + (UNITES[cle] || '');
    return String(v);
  }

  function resume(c, max = 4){
    const specs = (c && c.specs) || {};
    const cles = (ESSENTIELLES[c && c.categorie] || Object.keys(specs))
      .filter(k => specs[k] !== undefined && specs[k] !== null && specs[k] !== '' && !(Array.isArray(specs[k]) && !specs[k].length));
    return cles.slice(0, max).map(k => valeur(k, specs[k])).join(' · ');
  }

  window.PCSpecs = { libelle, valeur, resume };
})();
