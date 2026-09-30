// Recherche tolérante de composants, commune au configurateur, au comparateur
// et à l'admin. Trouve le bon produit même si le nom n'est pas tapé
// exactement : fautes de frappe (« rizen » → Ryzen), mots collés
// (« rtx4060ti »), abréviations (« r5 7600 », « cg », « alim »), accents,
// unités (Go/GB, To/TB) ; cherche aussi dans les caractéristiques (puce,
// socket, type) et le nom de catégorie.
//
//   pcrRecherche.score(requete, composant) → 0 (ne correspond pas) ou un score
//   pcrRecherche.filtrer(requete, composants) → composants triés par pertinence
(function(){
  const sansAccents = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

  // Écritures équivalentes, appliquées au texte ET à la requête.
  const EQUIVALENTS = [
    [/\bgb\b/g, 'go'], [/\btb\b/g, 'to'], [/\bmb\b/g, 'mo'],
    [/\bgeforce\b/g, 'geforce'], [/\bradeon\b/g, 'radeon'],
    [/\bcarte mere\b/g, 'cartemere'], [/\bcarte graphique\b/g, 'cartegraphique'],
    [/\bmotherboard\b/g, 'cartemere'], [/\bmobo\b/g, 'cartemere'],
  ];
  // Mots de la requête qui désignent une catégorie (ou sont des abréviations).
  const ALIAS = {
    cg: 'cartegraphique', gpu: 'cartegraphique', graphique: 'cartegraphique',
    cm: 'cartemere', mb: 'cartemere',
    cpu: 'processeur', proc: 'processeur', processeurs: 'processeur',
    alim: 'alimentation', psu: 'alimentation',
    ram: 'memoire', memoires: 'memoire',
    ssd: 'stockage', nvme: 'nvme', hdd: 'stockage', disque: 'stockage',
    boitier: 'boitier', case: 'boitier', tour: 'boitier',
    ventirad: 'refroidissement', watercooling: 'refroidissement', aio: 'refroidissement', rad: 'refroidissement',
    r3: 'ryzen 3', r5: 'ryzen 5', r7: 'ryzen 7', r9: 'ryzen 9',
    nvidia: 'nvidia', amd: 'amd', intel: 'intel',
  };
  const CATEGORIE_MOTS = {
    'CPU': 'processeur cpu', 'GPU': 'cartegraphique gpu', 'Carte mère': 'cartemere',
    'RAM': 'memoire ram', 'Stockage': 'stockage ssd', 'Alimentation': 'alimentation',
    'Boîtier': 'boitier', 'Refroidissement': 'refroidissement ventirad',
  };
  const MOTS_VIDES = new Set(['de', 'du', 'des', 'la', 'le', 'les', 'un', 'une', 'pour', 'avec', 'et', 'a', 'en', 'pas', 'cher', 'the', 'pc']);
  // Suffixes collés au nombre qui forment un mot à part (4060ti → 4060 ti).
  const SUFFIXES = 'ti|super|xtx|xt|gre|go|to|mo|w|mhz|mt|cl';

  function preparer(texte){
    let s = sansAccents(texte).replace(/[®™©()[\],/+|:;!?"']/g, ' ');
    // Préfixes collés au numéro (rtx4060 → rtx 4060) ; « am5 », « b650 » restent entiers.
    s = s.replace(/\b(rtx|gtx|rx|arc|ryzen|ultra|core)(\d)/g, '$1 $2');
    s = s.replace(new RegExp(`(\\d)(${SUFFIXES})\\b`, 'g'), '$1 $2');      // 4060ti → 4060 ti, 16go → 16 go
    s = s.replace(/-/g, ' ');
    EQUIVALENTS.forEach(([re, rempl]) => { s = s.replace(re, rempl); });
    return s.split(/\s+/).filter(Boolean);
  }

  function motsRequete(requete){
    // Les abréviations (« r5 », « cg ») sont remplacées AVANT le découpage
    // lettres/chiffres, sinon « r5 » deviendrait « r » + « 5 ».
    const brut = sansAccents(requete).split(/\s+/).filter(Boolean)
      .map(m => ALIAS[m] || m).join(' ');
    return preparer(brut).filter(m => !MOTS_VIDES.has(m))
      .flatMap(m => (ALIAS[m] || m).split(' '));
  }

  // Déclinaisons d'un modèle : « rtx 4060 » doit passer avant la « 4060 Ti ».
  const DECLINAISONS = new Set(['ti', 'super', 'xt', 'xtx', 'gre', 'x3d']);

  // Distance de Damerau-Levenshtein (transpositions comptées comme 1 faute).
  function distance(a, b, max){
    if(Math.abs(a.length - b.length) > max) return max + 1;
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for(let j = 1; j <= b.length; j++) d[0][j] = j;
    for(let i = 1; i <= a.length; i++){
      let min = Infinity;
      for(let j = 1; j <= b.length; j++){
        const c = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
        if(i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        min = Math.min(min, d[i][j]);
      }
      if(min > max) return max + 1;
    }
    return d[a.length][b.length];
  }

  // Gammes de cartes graphiques : le nombre tapé juste après doit être le début
  // du numéro de la carte (« rtx 30 » → 3050, 3060… ; « rtx 3 » ≠ « Infinity 3 »).
  const GAMMES_GPU = new Set(['rtx', 'gtx', 'rx']);

  // Meilleure correspondance d'un mot de la requête parmi les mots du produit.
  // « enCours » : dernier mot de la requête, peut-être pas fini de taper
  // (« 40 » doit déjà proposer les 4060, 4070…).
  function scoreMot(q, mots, enCours){
    const numerique = /^\d+$/.test(q);
    // Un mot qui contient un chiffre est un numéro de modèle : jamais « corrigé »
    // (9800x3d ≠ 5800x3d, 14400f ≠ 12400f).
    const modele = /\d/.test(q);
    const debutMin = numerique ? (enCours ? 2 : 4) : 2;
    let best = 0;
    for(const m of mots){
      if(m === q){ best = Math.max(best, 10); continue; }
      if(m.startsWith(q) && q.length >= debutMin && !(numerique && m.length < 4)){ best = Math.max(best, numerique ? 6 : 7); continue; }
      if(modele) continue;                          // un numéro de modèle ne se « corrige » jamais (4060 ≠ 4070)
      if(q.length >= 4 && m.length >= 3){
        const max = q.length >= 8 ? 2 : 1;
        const cible = m.length > q.length + max ? m.slice(0, q.length) : m;
        if(distance(q, cible, max) <= max){ best = Math.max(best, 4); continue; }
      }
      if(q.length >= 3 && m.includes(q)) best = Math.max(best, 3);
    }
    return best;
  }

  const cache = new WeakMap();
  function motsComposant(c){
    if(cache.has(c)) return cache.get(c);
    const specs = c.specs || {};
    const extra = [specs.puce, specs.socket, specs.type, specs.ram_type, specs.chipset, specs.format, specs.type_refroidissement, c.marque]
      .filter(Boolean).join(' ');
    const mots = preparer(`${c.nom || ''} ${extra} ${CATEGORIE_MOTS[c.categorie] || ''}`);
    const suite = preparer(`${c.nom || ''} | ${specs.puce || ''}`);   // mots dans l'ordre
    const nom = new Set(suite);
    const r = { mots, nom, suite };
    cache.set(c, r);
    return r;
  }

  function score(requete, c){
    const q = motsRequete(requete);
    if(!q.length) return 1;
    const { mots, nom, suite } = motsComposant(c);
    let total = 0, rates = 0;
    const scores = q.map((m, k) => {
      // Nombre juste après « rtx », « gtx » ou « rx » : il doit suivre la gamme
      // dans le nom du produit et en être le début (même un seul chiffre).
      if(k > 0 && GAMMES_GPU.has(q[k - 1]) && /^\d+$/.test(m)){
        let s = 0;
        suite.forEach((mot, i) => {
          if(i && suite[i - 1] === q[k - 1] && mot.startsWith(m)) s = Math.max(s, mot === m ? 10 : 7);
        });
        return s;
      }
      return scoreMot(m, mots, k === q.length - 1);
    });
    for(const [k, m] of q.entries()){
      const s = scores[k];
      if(!s) rates++;
      total += s + (nom.has(m) ? 2 : 0);            // bonus si le mot est dans le nom lui-même
    }
    // Tous les mots doivent correspondre ; au-delà de 3 mots, un oubli est toléré,
    // mais jamais celui d'un numéro de modèle (9800x3d ne doit pas donner la 5800X3D).
    if(rates > (q.length >= 4 ? 1 : 0)) return 0;
    if(rates && q.some((m, k) => /\d/.test(m) && !scores[k])) return 0;
    if(c.en_stock === false) total -= 1;
    const demandes = new Set(q);
    nom.forEach(m => { if(DECLINAISONS.has(m) && !demandes.has(m)) total -= 3; });
    return Math.max(0.1, total - rates * 5);
  }

  function filtrer(requete, composants){
    if(!requete || !requete.trim()) return composants.slice();
    return composants
      .map(c => [c, score(requete, c)])
      .filter(([, s]) => s > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => c);
  }

  window.pcrRecherche = { score, filtrer, preparer, motsRequete };
})();
