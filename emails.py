"""
E-mails de PC Radar : bannière personnalisée (image PNG dessinée avec la
police du site) et gabarit HTML aux couleurs du site.

La bannière est jointe au message en image « inline » (cid:banniere) : elle
s'affiche sans que Gmail demande « Afficher les images », contrairement à
une image hébergée. Le gabarit n'utilise que des tableaux avec bgcolor en
plus des styles en ligne : c'est ce que les messageries respectent le mieux
(Gmail ignore <body>, <style> et certaines propriétés CSS).
"""
import io
import os
from functools import lru_cache
from html import escape

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Couleurs du site (static/style.css)
BG = "#0e0f11"
SURFACE = "#141517"
SURFACE_2 = "#1a1b1e"
LINE = "#26272b"
LINE_STRONG = "#35363c"
TEXT = "#ececee"
TEXT_2 = "#a3a3ab"
TEXT_3 = "#81828a"
ACCENT = "#3ecf8e"
ACCENT_INK = "#05140d"
FONT_STACK = "Geist,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO_STACK = "'Geist Mono',Consolas,'SF Mono',Menlo,monospace"


# ---------------------------------------------------------------------------
# Bannière
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(ASSETS, "fonts", name), size)


@lru_cache(maxsize=1)
def _logo(size):
    from PIL import Image, ImageDraw
    logo = Image.open(os.path.join(ASSETS, "logo-carre.png")).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.24), fill=255)
    logo.putalpha(mask)
    return logo


def _hex(color, alpha=255):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _wrap(draw, text, font, max_width, max_lines):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def banniere(kicker, titre, valeur=None, sous_titre=None):
    """
    Bannière 1200×480 px (affichée en 600×240) : logo, étiquette verte
    (« ALERTE PRIX »...), titre personnalisé, valeur mise en avant (prix)
    et sous-titre. Renvoie les octets PNG.
    """
    from PIL import Image, ImageDraw

    width, height = 1200, 480
    image = Image.new("RGBA", (width, height), _hex(BG))
    draw = ImageDraw.Draw(image)

    # Quadrillage discret, qui s'efface vers la gauche (où est le texte).
    grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(0, width, 48):
        grid_draw.line([(x, 0), (x, height)], fill=_hex(LINE), width=2)
    for y in range(0, height, 48):
        grid_draw.line([(0, y), (width, y)], fill=_hex(LINE), width=2)
    fade = Image.linear_gradient("L").rotate(90).resize((width, height))
    fade = fade.point(lambda v: int(v * 0.55))
    grid.putalpha(Image.composite(grid.getchannel("A"), Image.new("L", (width, height), 0), fade))
    image.alpha_composite(grid)

    pad = 72
    image.alpha_composite(_logo(64), (pad, 60))
    draw.text((pad + 84, 70), "PC Radar", font=_font("Geist-SemiBold.ttf", 34), fill=_hex(TEXT))

    # Étiquette (pastille verte)
    kicker = kicker.upper()
    kfont = _font("Geist-SemiBold.ttf", 22)
    kw = draw.textlength(kicker, font=kfont)
    ky = 168
    draw.rounded_rectangle((pad, ky, pad + kw + 44, ky + 44), radius=22,
                           fill=_hex("#12301f"), outline=_hex("#2a6b4e"), width=2)
    draw.ellipse((pad + 16, ky + 17, pad + 26, ky + 27), fill=_hex(ACCENT))
    draw.text((pad + 34, ky + 9), kicker, font=kfont, fill=_hex(ACCENT))

    # Titre (2 lignes max), puis la valeur mise en avant (prix) en vert et
    # le sous-titre sur la même ligne.
    right_limit = width - pad
    tfont = _font("Geist-Bold.ttf", 56)
    lines = _wrap(draw, titre, tfont, width - 2 * pad, 2)
    y = ky + 68
    for line in lines:
        draw.text((pad, y), line, font=tfont, fill=_hex(TEXT))
        y += 66
    x = pad
    y += 12
    if valeur:
        vfont = _font("Geist-Bold.ttf", 44)
        draw.text((x, y - 6), valeur, font=vfont, fill=_hex(ACCENT))
        x += draw.textlength(valeur, font=vfont) + 20
    if sous_titre:
        sfont = _font("Geist-Regular.ttf", 28)
        draw.text((x, y + 4), sous_titre, font=sfont, fill=_hex(TEXT_2))

    url_font = _font("GeistMono-Medium.ttf", 22)
    uw = draw.textlength("pcradar.tech", font=url_font)
    draw.text((right_limit - uw, 76), "pcradar.tech", font=url_font, fill=_hex(TEXT_3))

    out = io.BytesIO()
    image.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Gabarit HTML
# ---------------------------------------------------------------------------

def euros(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def ligne(label, valeur, accent=False):
    """Une ligne « libellé ........ valeur » pour les récapitulatifs."""
    color = ACCENT if accent else TEXT
    return (
        f'<tr><td style="padding:11px 0;border-top:1px solid {LINE};font-family:{FONT_STACK};font-size:15px;color:{TEXT_2};">{escape(label)}</td>'
        f'<td align="right" style="padding:11px 0;border-top:1px solid {LINE};font-family:{MONO_STACK};font-size:15px;color:{color};white-space:nowrap;">{escape(valeur)}</td></tr>'
    )


def encadre(lignes_html):
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{SURFACE_2}" '
        f'style="background-color:{SURFACE_2};border:1px solid {LINE};border-radius:12px;">'
        f'<tr><td style="padding:6px 18px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'{lignes_html}</table></td></tr></table>'
    )


def points(items):
    """Liste de points forts, chacun dans une rangée avec une puce verte."""
    rows = "".join(
        f'<tr><td width="22" valign="top" style="padding:7px 0;font-family:{FONT_STACK};font-size:15px;color:{ACCENT};">●</td>'
        f'<td style="padding:7px 0;font-family:{FONT_STACK};font-size:15px;line-height:1.55;color:{TEXT_2};">{item}</td></tr>'
        for item in items
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def gabarit(titre, intro_html, contenu_html="", cta=None, note_html="", pied_html=""):
    """
    Corps HTML complet. `cta` = (libellé, url). Les textes passés en *_html
    doivent déjà être échappés (escape) par l'appelant.
    """
    bouton = ""
    if cta:
        label, url = cta
        bouton = (
            f'<tr><td align="left" style="padding:26px 36px 4px;">'
            f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td bgcolor="{ACCENT}" style="background-color:{ACCENT};border-radius:10px;">'
            f'<a href="{escape(url)}" style="display:inline-block;padding:14px 26px;font-family:{FONT_STACK};font-size:16px;'
            f'font-weight:700;color:{ACCENT_INK};text-decoration:none;">{escape(label)} →</a></td></tr></table></td></tr>'
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark"><title>{escape(titre)}</title></head>
<body style="margin:0;padding:0;background-color:{BG};" bgcolor="{BG}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background-color:{BG};">
<tr><td align="center" style="padding:0;">
<!-- Même fond que la bannière, sans cadre : l'e-mail forme un seul bloc
     sombre sur toute la largeur. La bannière est un lien : Gmail n'affiche
     alors pas ses boutons Télécharger / Drive / Lens au survol. -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" bgcolor="{BG}"
  style="width:100%;max-width:600px;background-color:{BG};">
  <tr><td style="padding:0;"><a href="https://pcradar.tech" style="display:block;text-decoration:none;"><img src="cid:banniere" width="600" alt="{escape(titre)}"
    style="display:block;width:100%;max-width:600px;height:auto;border:0;"></a></td></tr>
  <tr><td style="padding:30px 36px 0;font-family:{FONT_STACK};">
    <h1 style="margin:0 0 12px;font-size:23px;line-height:1.3;font-weight:700;color:{TEXT};">{escape(titre)}</h1>
    <div style="font-size:16px;line-height:1.6;color:{TEXT_2};">{intro_html}</div>
  </td></tr>
  {f'<tr><td style="padding:20px 36px 0;">{contenu_html}</td></tr>' if contenu_html else ''}
  {bouton}
  {f'<tr><td style="padding:18px 36px 0;font-family:{FONT_STACK};font-size:13px;line-height:1.6;color:{TEXT_3};">{note_html}</td></tr>' if note_html else ''}
  <tr><td style="padding:28px 36px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="padding-top:18px;border-top:1px solid {LINE};font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;color:{TEXT_3};">
        {pied_html or 'Tu reçois cet e-mail car tu as un compte sur PC Radar.'}<br>
        <a href="https://pcradar.tech" style="color:{ACCENT};text-decoration:none;">pcradar.tech</a>
        &nbsp;·&nbsp; <a href="https://pcradar.tech/compte" style="color:{TEXT_2};text-decoration:underline;">Mon compte</a>
      </td></tr></table>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


# ---------------------------------------------------------------------------
# Les e-mails du site. Chacun renvoie (sujet, texte brut, html, bannière PNG).
# ---------------------------------------------------------------------------

SITE = "https://pcradar.tech"


def bienvenue(email):
    titre = "Bienvenue sur PC Radar"
    intro = ("Ton compte est prêt. Voici ce que tu peux faire maintenant :")
    contenu = points([
        f'<strong style="color:{TEXT};">Sauvegarder tes configurations</strong> et les retrouver sur tous tes appareils.',
        f'<strong style="color:{TEXT};">Suivre un prix</strong> : choisis un prix cible, on te prévient par e-mail quand il est atteint.',
        f'<strong style="color:{TEXT};">Partager une config</strong> avec un lien, pour demander l\'avis de tes potes.',
        f'<strong style="color:{TEXT};">Demander à l\'assistant IA</strong> une config pour ton budget et tes jeux.',
    ])
    texte = (
        f"{titre} !\n\nTon compte est prêt. Tu peux maintenant sauvegarder tes configurations, "
        "suivre un prix (on te prévient quand il baisse), partager une config avec un lien "
        "et demander une config à l'assistant IA.\n\n"
        f"Commencer : {SITE}/configurateur\n\nTu reçois cet e-mail car tu viens de créer un compte sur PC Radar."
    )
    html_body = gabarit(titre, escape(intro), contenu, ("Créer ma première config", f"{SITE}/configurateur"),
                        pied_html="Tu reçois cet e-mail car tu viens de créer un compte sur PC Radar.")
    return "Bienvenue sur PC Radar 👋", texte, html_body, banniere("Bienvenue", "Ton compte est prêt", sous_titre="Configure, compare et suis les prix de ton PC.")


def alerte_composant_activee(nom, prix_actuel, prix_cible, page):
    titre = "Alerte de prix activée"
    intro = f"On surveille le prix de <strong style=\"color:{TEXT};\">{escape(nom)}</strong> pour toi. Dès qu'il passe sous ton prix cible, tu reçois un e-mail."
    lignes = (ligne("Prix actuel", euros(prix_actuel)) if prix_actuel else "") + ligne("Ton prix cible", euros(prix_cible), accent=True)
    texte = (
        f"{titre}\n\nOn surveille le prix de {nom}. Dès qu'il passe sous {euros(prix_cible)}, tu reçois un e-mail."
        + (f"\nPrix actuel : {euros(prix_actuel)}" if prix_actuel else "")
        + f"\n\nVoir le composant : {SITE}{page}\nGérer tes alertes : {SITE}/compte"
    )
    html_body = gabarit(titre, intro, encadre(lignes), ("Voir le composant", f"{SITE}{page}"),
                        note_html="Les prix sont relevés chaque jour. Tu peux changer ou retirer l'alerte depuis ton compte.")
    return f"Alerte activée : {nom}", texte, html_body, banniere("Alerte activée", nom, valeur=euros(prix_cible), sous_titre="Ton prix cible")


def alerte_config_activee(nom_config, total, prix_cible, build_id):
    titre = "Suivi de ta configuration activé"
    intro = f"On surveille le prix total de ta configuration <strong style=\"color:{TEXT};\">{escape(nom_config)}</strong>. Dès qu'elle passe sous ton prix cible, tu reçois un e-mail."
    lignes = (ligne("Prix total actuel", euros(total)) if total else "") + ligne("Ton prix cible", euros(prix_cible), accent=True)
    lien = f"{SITE}/build/{build_id}"
    texte = (
        f"{titre}\n\nOn surveille le prix total de « {nom_config} ». Dès qu'elle passe sous {euros(prix_cible)}, tu reçois un e-mail."
        + (f"\nPrix total actuel : {euros(total)}" if total else "")
        + f"\n\nVoir la configuration : {lien}\nGérer tes alertes : {SITE}/compte"
    )
    html_body = gabarit(titre, intro, encadre(lignes), ("Voir la configuration", lien),
                        note_html="Les prix sont relevés chaque jour. Tu peux changer ou retirer le suivi depuis ton compte.")
    return f"Suivi activé : ta config « {nom_config} »", texte, html_body, banniere("Suivi activé", nom_config, valeur=euros(prix_cible), sous_titre="Prix cible de ta configuration")


def baisse_prix_composant(nom, prix, prix_cible, lien_offre, page):
    titre = "Le prix a baissé !"
    economie = prix_cible - prix
    intro = (f"Bonne nouvelle : <strong style=\"color:{TEXT};\">{escape(nom)}</strong> est passé à "
             f"<strong style=\"color:{ACCENT};\">{euros(prix)}</strong>, sous ton prix cible.")
    lignes = ligne("Nouveau prix", euros(prix), accent=True) + ligne("Ton prix cible", euros(prix_cible)) + (
        ligne("Sous ta cible de", euros(economie)) if economie >= 0.01 else "")
    cta_url = lien_offre or f"{SITE}{page}"
    texte = (
        f"{titre}\n\n{nom} est passé à {euros(prix)}, sous ton prix cible de {euros(prix_cible)}.\n\n"
        + (f"Voir l'offre : {lien_offre}\n" if lien_offre else "")
        + f"Voir le composant : {SITE}{page}\nGérer tes alertes : {SITE}/compte\n"
        "Les prix changent vite, vérifie-le sur la page du vendeur avant d'acheter."
    )
    html_body = gabarit(titre, intro, encadre(lignes), ("Voir l'offre", cta_url),
                        note_html="Les prix changent vite : vérifie-le sur la page du vendeur avant d'acheter.")
    return f"📉 {nom} à {euros(prix)}", texte, html_body, banniere("Baisse de prix", nom, valeur=euros(prix), sous_titre=f"Sous ta cible de {euros(prix_cible)}")


def baisse_prix_config(nom_config, total, prix_cible, pieces, build_id):
    """pieces = [(catégorie, nom, prix), ...]"""
    titre = "Ta configuration a baissé !"
    intro = (f"Ta configuration <strong style=\"color:{TEXT};\">{escape(nom_config)}</strong> coûte maintenant "
             f"<strong style=\"color:{ACCENT};\">{euros(total)}</strong>, sous ton prix cible de {euros(prix_cible)}.")
    lignes = "".join(ligne(f"{cat} · {n[:38]}", euros(p or 0)) for cat, n, p in pieces) + ligne("Total", euros(total), accent=True)
    lien = f"{SITE}/build/{build_id}"
    texte = (
        f"{titre}\n\n« {nom_config} » coûte maintenant {euros(total)}, sous ton prix cible de {euros(prix_cible)}.\n\n"
        + "\n".join(f"  - {cat} : {n} ({euros(p or 0)})" for cat, n, p in pieces)
        + f"\n\nVoir la configuration : {lien}\nGérer tes alertes : {SITE}/compte\n"
        "Les prix changent vite, vérifie-les sur la page du vendeur avant d'acheter."
    )
    html_body = gabarit(titre, intro, encadre(lignes), ("Voir la configuration", lien),
                        note_html="Les prix changent vite : vérifie-les sur la page du vendeur avant d'acheter.")
    return f"📉 Ta config « {nom_config} » à {euros(total)}", texte, html_body, banniere("Baisse de prix", nom_config, valeur=euros(total), sous_titre=f"Sous ta cible de {euros(prix_cible)}")


def compte_supprime():
    titre = "Ton compte a été supprimé"
    intro = ("Comme demandé, ton compte PC Radar et toutes les données qui y étaient liées "
             "(configurations, favoris, alertes de prix) ont été supprimés définitivement.")
    texte = f"{titre}\n\n{intro}\n\nTu peux toujours utiliser le site sans compte : {SITE}\nÀ bientôt peut-être !"
    html_body = gabarit(titre, escape(intro), "", ("Retourner sur PC Radar", SITE),
                        note_html="Tu n'es pas à l'origine de cette suppression ? Réponds simplement à cet e-mail.",
                        pied_html="Dernier e-mail envoyé à cette adresse : nous ne la conservons plus.")
    return "Ton compte PC Radar a été supprimé", texte, html_body, banniere("Compte supprimé", "À bientôt sur PC Radar", sous_titre="Toutes tes données ont été effacées.")


def controle_admin(nouveaux, admin_url):
    """E-mail quotidien à l'admin : nouveaux prix suspects du catalogue."""
    titre = f"{len(nouveaux)} prix suspect{'s' if len(nouveaux) > 1 else ''} dans le catalogue"
    intro = "Le contrôle quotidien du catalogue a repéré des prix qui s'écartent nettement des autres annonces du même produit."
    lignes = "".join(ligne(f"{s['nom'][:44]}", f"{euros(s['prix'])} (≈ {euros(s['reference'])})") for s in nouveaux)
    texte = f"{titre}\n\n" + "\n".join(
        f"- {s['nom']} ({s['categorie']}) : {euros(s['prix'])} au lieu d'environ {euros(s['reference'])} ({s['motif']})."
        for s in nouveaux) + f"\n\nDétail et actions : {admin_url}"
    html_body = gabarit(titre, escape(intro), encadre(lignes), ("Ouvrir « À surveiller »", admin_url),
                        pied_html="E-mail automatique réservé à l'administration de PC Radar.")
    return f"[PC Radar] {titre}", texte, html_body, banniere("Contrôle du catalogue", titre)
