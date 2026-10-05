"""
Pages d'erreur de PC Radar, au thème du site (en-tête, menu, pied de page).

- page(code, detail) : rendue par main.py pour les erreurs de l'application
  (page introuvable, erreur interne...) quand c'est un navigateur qui demande
  une page ; les appels d'API gardent leur réponse JSON.
- Les erreurs que nginx produit lui-même (site qui redémarre, trop de
  demandes, fichier introuvable, envoi trop lourd) utilisent des copies
  statiques de ces pages dans static/erreurs/, servies même quand Python est
  arrêté. Les régénérer après une modification :  python erreurs.py
"""
import os
from html import escape

# code -> (titre de l'onglet, titre, explication, boutons, recharge auto en secondes)
PAGES = {
    404: ("Page introuvable", "Cette page n’existe pas",
          "L’adresse contient peut-être une faute, ou la page a été déplacée. Si tu cherchais un composant, "
          "il a peut-être été retiré du catalogue : utilise la loupe en haut pour le retrouver.",
          [("/", "Retour à l’accueil", True), ("/configurateur", "Ouvrir le configurateur", False)], None),
    429: ("Trop de demandes", "Doucement, ça va trop vite",
          "Beaucoup de demandes sont parties de ta connexion en très peu de temps. Patiente quelques "
          "secondes, cette page se recharge toute seule.",
          [("/", "Retour à l’accueil", False)], 20),
    413: ("Envoi trop lourd", "C’est trop lourd à envoyer",
          "Ce que tu essaies d’envoyer dépasse la taille autorisée. Réduis sa taille puis réessaie.",
          [("/", "Retour à l’accueil", True)], None),
    500: ("Erreur interne", "Petit souci de notre côté",
          "Une erreur inattendue est survenue sur PC Radar. Ce n’est pas ta faute : réessaie dans un instant. "
          "Si ça continue, signale-le avec la bulle d’aide en bas à droite.",
          [("", "Réessayer", True), ("/", "Retour à l’accueil", False)], None),
    502: ("PC Radar revient tout de suite", "PC Radar revient tout de suite",
          "Le site est en train de se mettre à jour ou reçoit beaucoup de monde en même temps. "
          "Ça ne dure que quelques secondes : cette page se recharge toute seule.",
          [("", "Réessayer maintenant", True)], 10),
}
# Même message pour toutes les indisponibilités passagères.
ALIAS = {503: 502, 504: 502, 405: 404, 410: 404}

# Fichiers statiques pour nginx (error_page) : nom -> code.
FICHIERS_STATIQUES = {"404.html": 404, "429.html": 429, "413.html": 413, "502.html": 502}

DETAILS_404 = {
    "Composant introuvable.": "Ce composant n’est plus au catalogue, ou son adresse a changé. Utilise la loupe en "
                              "haut pour retrouver un modèle proche.",
    "Guide introuvable.": "Ce guide n’existe pas ou plus. Les guides par budget sont mis à jour chaque jour avec "
                          "les prix du moment.",
    "Comparatif introuvable.": "Ce comparatif n’existe pas. Le comparateur te permet de mettre face à face "
                               "n’importe quels composants.",
    "Configuration introuvable.": "Cette configuration a été supprimée, ou le lien est incomplet.",
    "Catégorie introuvable.": "Cette catégorie de composants n’existe pas.",
}

_TETE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="theme-color" content="#0e0f11">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{titre_onglet} — PC Radar</title>
{recharge}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<header>
  <div class="nav-wrap">
    <a href="/" class="logo"><img src="/static/favicon.svg" alt="" width="22" height="22">PC Radar</a>
    <button class="nav-toggle" id="nav-toggle" aria-label="Ouvrir le menu" aria-expanded="false"><span></span><span></span><span></span></button>
    <nav>
      <ul>
        <li><a href="/">Accueil</a></li>
        <li><a href="/configurateur">Configurateur</a></li>
        <li><a href="/assistant">Assistant IA</a></li>
        <li><a href="/comparateur">Comparateur</a></li>
        <li><a href="/estimer-fps">Estimer FPS</a></li>
        <li><a href="/compte">Mon compte</a></li>
      </ul>
    </nav>
  </div>
</header>
"""

_PIED = """
<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <strong>PC Radar</strong>
      <span>Projet personnel et indépendant. Compatibilité vérifiée côté serveur, suggestions IA validées avant affichage.</span>
    </div>
    <div class="footer-legal-links">
      <a href="/mentions-legales">Mentions légales</a>
      <a href="/confidentialite">Confidentialité</a>
      <a href="/cgu">CGU</a>
    </div>
  </div>
</footer>
{scripts}</body>
</html>
"""


def page(code, detail=None, scripts=True, code_affiche=None, contenu=None):
    """Page d'erreur complète. `scripts` : menu mobile, loupe et bulle d'aide
    (à éviter quand le serveur Python est indisponible)."""
    titre_onglet, titre, texte, boutons, recharge = contenu or PAGES[ALIAS.get(code, code) if ALIAS.get(code, code) in PAGES else 500]
    if code in (404, 405, 410) and detail in DETAILS_404:
        texte = DETAILS_404[detail]
    liens = "".join(
        f'<a class="btn {"btn-primary" if principal else "btn-secondary"}" href="{escape(url) if url else ""}">{escape(libelle)}</a>'
        for url, libelle, principal in boutons
    )
    numero = code_affiche if code_affiche is not None else code
    corps = f"""
<main class="erreur-page">
  <div class="erreur-carte">
    {f'<span class="erreur-code">{escape(str(numero))}</span>' if numero else ''}
    <h1>{escape(titre)}</h1>
    <p>{escape(texte)}</p>
    <div class="erreur-boutons">{liens}</div>
    {'<p class="erreur-auto">Nouvel essai automatique dans quelques secondes.</p>' if recharge else ''}
  </div>
</main>
"""
    return (_TETE.format(titre_onglet=escape(titre_onglet),
                         recharge=f'<meta http-equiv="refresh" content="{recharge}">\n' if recharge else "")
            + corps
            + _PIED.format(scripts='<script src="/static/nav-menu.js"></script>\n' if scripts else ""))


# Page « Pas de connexion » de l'application installée (mise en cache par sw.js).
HORS_LIGNE = ("Pas de connexion", "Pas de connexion",
              "PC Radar a besoin d’Internet pour afficher les prix du jour et vérifier la compatibilité. "
              "Vérifie ta connexion, puis réessaie.",
              [("/", "Réessayer", True)], None)


def ecrire_fichiers_statiques(dossier=None):
    racine = os.path.dirname(os.path.abspath(__file__))
    dossier = dossier or os.path.join(racine, "static", "erreurs")
    os.makedirs(dossier, exist_ok=True)
    for nom, code in FICHIERS_STATIQUES.items():
        # 404 de nginx = fichier statique manquant : le site tourne, scripts possibles.
        with open(os.path.join(dossier, nom), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(code, scripts=(code == 404)))
    with open(os.path.join(racine, "static", "offline.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page(0, scripts=False, code_affiche="", contenu=HORS_LIGNE))


if __name__ == "__main__":
    ecrire_fichiers_statiques()
    print("Pages d'erreur statiques régénérées.")
