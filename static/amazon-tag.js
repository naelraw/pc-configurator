// Charge le tag Amazon Associates depuis le serveur et fournit une fonction
// pour l'ajouter automatiquement aux liens Amazon (jamais aux autres
// revendeurs, jamais en écrasant des paramètres déjà présents dans l'URL).
let amazonTag = '';

async function loadAmazonTag(){
  try{
    const res = await fetch(window.location.origin + '/api/config');
    const data = await res.json();
    amazonTag = data.amazon_tag || '';
  }catch(e){
    console.error('Erreur chargement config affiliation', e);
  }
}

function withAffiliateTag(url){
  if(!amazonTag) return url;
  try{
    const parsed = new URL(url);
    if(!parsed.hostname.includes('amazon.')) return url;
    parsed.searchParams.set('tag', amazonTag);
    return parsed.toString();
  }catch(e){
    return url;
  }
}
