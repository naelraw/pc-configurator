"""Mise à jour des prix : une fois par nuit, entre 2 h et 6 h (heure de Paris)."""
from datetime import datetime


def _paris(main, *args):
    return datetime(*args, tzinfo=main.PRIX_FUSEAU)


def test_fenetre_de_nuit(app_main):
    main = app_main
    # Dernier passage le 6 octobre à 8 h 28 (Paris) = 6 h 28 UTC.
    main._state_set("derniere_mise_a_jour_prix", "2026-10-06T06:28:45")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 6, 23, 0))   # hors fenêtre
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 1, 59))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 2, 0))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 5, 59))
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 6, 0))


def test_une_seule_fois_par_nuit(app_main):
    main = app_main
    # Passage fait cette nuit à 2 h 05 (Paris) = 0 h 05 UTC, le même jour à Paris.
    main._state_set("derniere_mise_a_jour_prix", "2026-10-07T00:05:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 3, 30))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 8, 2, 0))
    # 23 h 30 UTC le 6 = 1 h 30 à Paris le 7 : la date est bien prise à l'heure de Paris.
    main._state_set("derniere_mise_a_jour_prix", "2026-10-06T23:30:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 7, 2, 0))
