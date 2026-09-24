// Charge la config d'affiliation depuis le serveur (tag Amazon Associates +
// identifiants Awin pour les autres revendeurs) et fournit une fonction pour
// ajouter automatiquement le bon suivi d'affiliation à un lien, sans jamais
// écraser un paramètre déjà présent dans l'URL ni casser un lien vers un
// revendeur pour lequel il n'y a pas encore d'accord d'affiliation.
let amazonTag = '';
let awinPublisherId = '';
let awinMerchantIds = {};

async function loadAffiliateConfig(){
  try{
    const res = await fetch(window.location.origin + '/api/config');
    const data = await res.json();
    amazonTag = data.amazon_tag || '';
    awinPublisherId = data.awin_publisher_id || '';
    awinMerchantIds = data.awin_merchant_ids || {};
  }catch(e){
    console.error('Erreur chargement config affiliation', e);
  }
}

// vendeur est optionnel (rétrocompatible avec les appels existants qui ne le
// passaient pas) mais nécessaire pour reconnaître un marchand Awin, puisque
// contrairement à Amazon il n'y a pas de nom de domaine générique à détecter.
function withAffiliateTag(url, vendeur){
  let parsed;
  try{
    parsed = new URL(url);
  }catch(e){
    return url;
  }

  if(parsed.hostname.includes('amazon.')){
    if(!amazonTag) return url;
    parsed.searchParams.set('tag', amazonTag);
    return parsed.toString();
  }

  const merchantId = vendeur ? awinMerchantIds[vendeur] : null;
  if(!merchantId || !awinPublisherId) return url;

  return `https://www.awin1.com/cread.php?awinmid=${encodeURIComponent(merchantId)}&awinaffid=${encodeURIComponent(awinPublisherId)}&ued=${encodeURIComponent(url)}`;
}
