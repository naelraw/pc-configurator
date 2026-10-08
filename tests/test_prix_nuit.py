"""Mise à jour des prix : une fois par nuit, entre 2 h et 6 h (heure de Paris)."""
from datetime import datetime


def _paris(main, *args):
    return datetime(*args, tzinfo=main.PRIX_FUSEAU)


def _dernier_passage(main, valeur):
    """Écrit la date comme _mark_task_done en production : texte brut, pas du JSON."""
    client = main.get_client()
    try:
        client.execute("INSERT INTO app_state (cle, valeur) VALUES ('derniere_mise_a_jour_prix', ?) "
                       "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", [valeur])
    finally:
        client.close()


def test_fenetre_de_nuit(client, app_main):
    main = app_main
    # Dernier passage le 6 octobre à 8 h 28 (Paris) = 6 h 28 UTC.
    _dernier_passage(main, "2026-10-06T06:28:45")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 6, 23, 0))   # hors fenêtre
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 1, 59))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 2, 0))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 5, 59))
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 6, 0))


def test_une_seule_fois_par_nuit(client, app_main):
    main = app_main
    # Passage fait cette nuit à 2 h 05 (Paris) = 0 h 05 UTC, le même jour à Paris.
    _dernier_passage(main, "2026-10-07T00:05:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 3, 30))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 8, 2, 0))
    # 23 h 30 UTC le 6 = 1 h 30 à Paris le 7 : la date est bien prise à l'heure de Paris.
    _dernier_passage(main, "2026-10-06T23:30:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 2, 0))


def test_date_ecrite_par_mark_task_done(client, app_main):
    """Bug d'octobre 2026 : la date brute était lue comme du JSON, donc jamais
    trouvée, et la mise à jour recommençait en boucle de 2 h à 6 h."""
    main = app_main
    main._mark_task_done("derniere_mise_a_jour_prix")
    maintenant = datetime.now(main.PRIX_FUSEAU).replace(hour=3, minute=0)
    assert not main._mise_a_jour_prix_due(maintenant)
