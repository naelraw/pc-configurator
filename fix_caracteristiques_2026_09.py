"""Caractéristiques détaillées relevées sur les fiches des fabricants (amd.com, intel.com…).
Usage : python fix_caracteristiques_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)

Chaque entrée donne l'id, le début exact du nom en base (garde-fou) et les champs à écrire,
fusionnés dans specs_json. Les champs existants de compatibilité ne sont pas touchés."""
import json, sqlite3, sys

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv
UPDATES = {}

# Processeurs : amd.com (fiches produit) et intel.com (ARK). iGPU « Aucune » = pas de
# circuit graphique intégré (modèles F, Ryzen sans G…). « memoire » = types supportés.
CPUS = {
    1949: ("AMD Ryzen 7 9800X3D", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.7, "frequence_boost_ghz": 5.2, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1950: ("AMD Ryzen 5 5600", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1951: ("AMD Ryzen 7 5800X3D", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.5, "cache_l3_mo": 96, "memoire": "DDR4", "igpu": "Aucune"}),
    1952: ("AMD Ryzen 7 7800X3D", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.0, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1953: ("AMD Ryzen 5 9600X", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.9, "frequence_boost_ghz": 5.4, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1954: ("AMD Ryzen 9 9950X3D 3D V-", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.3, "frequence_boost_ghz": 5.7, "cache_l3_mo": 128, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1955: ("AMD Ryzen 7 5700X 3.4GHz", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.6, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1956: ("AMD Ryzen 5 7600X", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 4.7, "frequence_boost_ghz": 5.3, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1957: ("AMD Ryzen 7 9700X 8 Cœurs", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 5.5, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1958: ("AMD Ryzen 9 9900X 12 Cœur", {"coeurs": 12, "threads": 24, "frequence_base_ghz": 4.4, "frequence_boost_ghz": 5.6, "cache_l3_mo": 64, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1959: ("AMD Ryzen 7 9850X3D 8 Cœu", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.7, "frequence_boost_ghz": 5.6, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1960: ("AMD Ryzen 5 7500F 6 Coeur", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 5.0, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "Aucune"}),
    1961: ("AMD Ryzen 7 5800X 4.7 GHz", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 4.7, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1962: ("AMD Ryzen 5 7500X3D 65W", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 4.0, "frequence_boost_ghz": 4.5, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1963: ("AMD Ryzen 7 7700X 8 Cœurs", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.5, "frequence_boost_ghz": 5.4, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1964: ("AMD Ryzen 5 5500 3,6 GHz", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.2, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    1965: ("AMD Ryzen 7 7800X3D Tray", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.0, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1966: ("AMD Ryzen 9 5950X", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.9, "cache_l3_mo": 64, "memoire": "DDR4", "igpu": "Aucune"}),
    1967: ("AMD Ryzen 7 5700X", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.6, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1968: ("AMD Ryzen 9 9950X", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.3, "frequence_boost_ghz": 5.7, "cache_l3_mo": 64, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1969: ("AMD Ryzen 5 8600G", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 4.3, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "AMD Radeon 760M"}),
    1970: ("AMD Ryzen 5 5500", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.2, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    1971: ("AMD Ryzen 5 8400F", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 4.7, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "Aucune"}),
    1972: ("AMD Ryzen 5 5600XT", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.7, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1973: ("AMD Ryzen 7 5700", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.6, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    1974: ("AMD Ryzen 5 5500GT", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.4, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "AMD Radeon Graphics"}),
    1975: ("AMD Ryzen 3 3200G Radeon ", {"coeurs": 4, "threads": 4, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.0, "cache_l3_mo": 4, "memoire": "DDR4", "igpu": "AMD Radeon Vega 8"}),
    1976: ("AMD Ryzen 5 5600GT", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.6, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "AMD Radeon Graphics"}),
    1977: ("AMD Ryzen 5 3600", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.2, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1978: ("AMD Ryzen 7 7700", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 5.3, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1979: ("AMD Ryzen 7 7700X3D 96 Mo", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.0, "frequence_boost_ghz": 4.5, "cache_l3_mo": 96, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1980: ("AMD Ryzen 9 9950X3D2 WOF", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.3, "frequence_boost_ghz": 5.6, "cache_l3_mo": 192, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1981: ("AMD Ryzen 5 8500G", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "AMD Radeon 740M"}),
    1982: ("AMD Ryzen 7 8700F 8 Cœurs", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.1, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "Aucune"}),
    1983: ("AMD Ryzen 7 8700F", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.1, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "Aucune"}),
    1984: ("AMD Ryzen 7 8700G", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.1, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "AMD Radeon 780M"}),
    1985: ("AMD Ryzen 7 9700X", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 5.5, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1986: ("AMD Ryzen 7 5700X Tray 60", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.6, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    1987: ("AMD Ryzen 7 7700 3,8 GHz", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 5.3, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1988: ("AMD Ryzen 7 8700G Wraith ", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.1, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "AMD Radeon 780M"}),
    1989: ("AMD Ryzen 7 8700G OEM", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.1, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "AMD Radeon 780M"}),
    1990: ("AMD Ryzen 3 3200G 3,6 GHz", {"coeurs": 4, "threads": 4, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.0, "cache_l3_mo": 4, "memoire": "DDR4", "igpu": "AMD Radeon Vega 8"}),
    1991: ("AMD Ryzen 3 PRO 4350G 3,8", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 4.0, "cache_l3_mo": 4, "memoire": "DDR4", "igpu": "AMD Radeon Graphics"}),
    1992: ("AMD Ryzen 5 3400G", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.2, "cache_l3_mo": 4, "memoire": "DDR4", "igpu": "AMD Radeon Vega 11"}),
    1993: ("AMD Ryzen 3 4100", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.8, "frequence_boost_ghz": 4.0, "cache_l3_mo": 4, "memoire": "DDR4", "igpu": "Aucune"}),
    1994: ("AMD Ryzen 3 5300G 4 GHz", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 4.0, "frequence_boost_ghz": 4.2, "cache_l3_mo": 8, "memoire": "DDR4", "igpu": "AMD Radeon Graphics"}),
    1995: ("AMD Ryzen 9 7900X3D", {"coeurs": 12, "threads": 24, "frequence_base_ghz": 4.4, "frequence_boost_ghz": 5.6, "cache_l3_mo": 128, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1996: ("AMD Ryzen 9 7900", {"coeurs": 12, "threads": 24, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 5.4, "cache_l3_mo": 64, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1997: ("AMD Ryzen 9 7950X3D", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.7, "cache_l3_mo": 128, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    1998: ("AMD Ryzen 9 5950X Socket ", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.9, "cache_l3_mo": 64, "memoire": "DDR4", "igpu": "Aucune"}),
    1999: ("AMD Ryzen 9 7950X 16 coeu", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.5, "frequence_boost_ghz": 5.7, "cache_l3_mo": 64, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    2000: ("AMD Ryzen 9 9950X Plateau", {"coeurs": 16, "threads": 32, "frequence_base_ghz": 4.3, "frequence_boost_ghz": 5.7, "cache_l3_mo": 64, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    2001: ("AMD Ryzen 5 5500 processe", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.2, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2002: ("Intel Core i5-12400F 4,40", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 18, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2003: ("Intel Core i5-14400F 4,7 ", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2004: ("Intel Core i5-14400 4,7 G", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2005: ("Intel Core i5-14600KF", {"coeurs": 14, "threads": 20, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 5.3, "cache_l3_mo": 24, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2006: ("Intel Core Ultra 5 225F 4", {"coeurs": 10, "threads": 10, "frequence_base_ghz": 3.3, "frequence_boost_ghz": 4.9, "cache_l3_mo": 20, "memoire": "DDR5", "igpu": "Aucune"}),
    2007: ("Intel Core i5-12400F 4.40", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 18, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2008: ("Intel Core i5-14600K LGA1", {"coeurs": 14, "threads": 20, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 5.3, "cache_l3_mo": 24, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2010: ("Intel Core i5-12600KF", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.9, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2011: ("Intel Core Ultra 5 250KF ", {"coeurs": 18, "threads": 18, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.3, "cache_l3_mo": 30, "memoire": "DDR5", "igpu": "Aucune"}),
    2012: ("Intel Core Ultra 5 225", {"coeurs": 10, "threads": 10, "frequence_base_ghz": 3.3, "frequence_boost_ghz": 4.9, "cache_l3_mo": 20, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2013: ("Intel Core i5-14400F 10 C", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2014: ("Intel Core i7-12700KF 3.6", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2015: ("Processeur Intel Intel Co", {"coeurs": 14, "threads": 20, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 5.3, "cache_l3_mo": 24, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2016: ("Intel Core Ultra 5 245KF ", {"coeurs": 14, "threads": 14, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.2, "cache_l3_mo": 24, "memoire": "DDR5", "igpu": "Aucune"}),
    2017: ("Intel Core i5-12600K 3,7 ", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.9, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2018: ("Intel Core i5-12400 4,40 ", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 18, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2019: ("Intel Core i5-14500", {"coeurs": 14, "threads": 20, "frequence_base_ghz": 2.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 24, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2020: ("Intel Core Ultra 5 245K", {"coeurs": 14, "threads": 14, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.2, "cache_l3_mo": 24, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2021: ("Intel Core i7-14700F", {"coeurs": 20, "threads": 28, "frequence_base_ghz": 2.1, "frequence_boost_ghz": 5.4, "cache_l3_mo": 33, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2022: ("Intel Core i5-13400F", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.6, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2027: ("Intel Core i7-14700", {"coeurs": 20, "threads": 28, "frequence_base_ghz": 2.1, "frequence_boost_ghz": 5.4, "cache_l3_mo": 33, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2028: ("Intel Core Ultra 7 265K", {"coeurs": 20, "threads": 20, "frequence_base_ghz": 3.9, "frequence_boost_ghz": 5.5, "cache_l3_mo": 30, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2029: ("Intel Core i3-14100", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2030: ("Intel Core i3-14100F", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2031: ("Intel Core i7-14700KF", {"coeurs": 20, "threads": 28, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 5.6, "cache_l3_mo": 33, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2032: ("Intel Core i7-14700K", {"coeurs": 20, "threads": 28, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 5.6, "cache_l3_mo": 33, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2033: ("Intel Core i7-12700KF 12 ", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2034: ("Intel Core i7-12700F", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 2.1, "frequence_boost_ghz": 4.9, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2035: ("Intel Core i7-12700K 3.60", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2036: ("Intel Core i9-14900KF", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 3.2, "frequence_boost_ghz": 6.0, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2037: ("Intel Core i7-13700F 16 c", {"coeurs": 16, "threads": 24, "frequence_base_ghz": 2.1, "frequence_boost_ghz": 5.2, "cache_l3_mo": 30, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2038: ("Intel Core i9-14900K 24 c", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 3.2, "frequence_boost_ghz": 6.0, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2039: ("Intel Core i7-12700 4,90 ", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 2.1, "frequence_boost_ghz": 4.9, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2040: ("Intel Core i7-8700K 3.7 G", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.7, "cache_l3_mo": 12, "memoire": "DDR4", "igpu": "Intel UHD Graphics 630"}),
    2041: ("Intel Core i7-11700F", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.9, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2042: ("Intel Core Ultra 7 265F", {"coeurs": 20, "threads": 20, "frequence_base_ghz": 2.4, "frequence_boost_ghz": 5.3, "cache_l3_mo": 30, "memoire": "DDR5", "igpu": "Aucune"}),
    2043: ("Intel Core i3-13100F", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.5, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2044: ("Intel Core i3-12100F LGA1", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.3, "frequence_boost_ghz": 4.3, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2045: ("Intel Core i3-9100F", {"coeurs": 4, "threads": 4, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.2, "cache_l3_mo": 6, "memoire": "DDR4", "igpu": "Aucune"}),
    2046: ("Intel Core i3-14100 4,7 G", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2047: ("Intel Core i3-13100F 4,5 ", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.4, "frequence_boost_ghz": 4.5, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2048: ("Intel Core i3-14100 3,5 G", {"coeurs": 4, "threads": 8, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 12, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2049: ("Intel Core i9-12900K", {"coeurs": 16, "threads": 24, "frequence_base_ghz": 3.2, "frequence_boost_ghz": 5.2, "cache_l3_mo": 30, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2050: ("Intel Core i9-14900 5,8 G", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 2.0, "frequence_boost_ghz": 5.8, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2051: ("Intel Core i9-12900KF", {"coeurs": 16, "threads": 24, "frequence_base_ghz": 3.2, "frequence_boost_ghz": 5.2, "cache_l3_mo": 30, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2052: ("Intel Core i9-14900KS 36 ", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 3.2, "frequence_boost_ghz": 6.2, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2053: ("Intel Core Ultra 9 285 24", {"coeurs": 24, "threads": 24, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 5.6, "cache_l3_mo": 36, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2054: ("Intel Core i9-9900K 3,6 G", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Intel UHD Graphics 630"}),
    2055: ("Intel Core i9-12900", {"coeurs": 16, "threads": 24, "frequence_base_ghz": 2.4, "frequence_boost_ghz": 5.1, "cache_l3_mo": 30, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2056: ("Intel Core i9-13900K", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 3.0, "frequence_boost_ghz": 5.8, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2057: ("Intel Core i9-9900K 5,0 G", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Intel UHD Graphics 630"}),
    2058: ("Intel Core i9-13900KF", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 3.0, "frequence_boost_ghz": 5.8, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2059: ("Intel Core i9-14900F", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 2.0, "frequence_boost_ghz": 5.8, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2060: ("Intel Core i9-9900KF", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2061: ("Intel Core i9-11900KF", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 5.3, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2062: ("Intel Core i9-11900F 8 cœ", {"coeurs": 8, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 5.2, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2063: ("Intel Core i9-13900F", {"coeurs": 24, "threads": 32, "frequence_base_ghz": 2.0, "frequence_boost_ghz": 5.6, "cache_l3_mo": 36, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2064: ("Intel CPU/Core i5-12400F ", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 18, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    2065: ("Intel Core i5-14400 4.7 G", {"coeurs": 10, "threads": 16, "frequence_base_ghz": 2.5, "frequence_boost_ghz": 4.7, "cache_l3_mo": 20, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 730"}),
    2066: ("Intel Core Ultra 5 250K L", {"coeurs": 18, "threads": 18, "frequence_base_ghz": 4.2, "frequence_boost_ghz": 5.3, "cache_l3_mo": 30, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2067: ("Intel Core Ultra 7 270K P", {"coeurs": 24, "threads": 24, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 5.5, "cache_l3_mo": 36, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2068: ("Intel Core i7-12700K", {"coeurs": 12, "threads": 20, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 5.0, "cache_l3_mo": 25, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    2069: ("Intel Core Ultra 7 270K P", {"coeurs": 24, "threads": 24, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 5.5, "cache_l3_mo": 36, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    2786: ("AMD Ryzen 5 5600X", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.6, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    2787: ("AMD Ryzen 5 4500", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6, "frequence_boost_ghz": 4.1, "cache_l3_mo": 8, "memoire": "DDR4", "igpu": "Aucune"}),
    2788: ("AMD Ryzen 5 5600 6 cœurs", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.5, "frequence_boost_ghz": 4.4, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
    2789: ("Intel Core i5-10400F", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 2.9, "frequence_boost_ghz": 4.3, "cache_l3_mo": 12, "memoire": "DDR4", "igpu": "Aucune"}),
    2790: ("AMD Ryzen 5 5600X 3,7 GHz", {"coeurs": 6, "threads": 12, "frequence_base_ghz": 3.7, "frequence_boost_ghz": 4.6, "cache_l3_mo": 32, "memoire": "DDR4", "igpu": "Aucune"}),
}
for cid, (nom, valeurs) in CPUS.items():
    UPDATES.setdefault(cid, (nom, {}))[1].update(valeurs)

changes, problems = [], []
for cid, (expected, values) in UPDATES.items():
    r = db.execute("select nom, specs_json from components where id=?", (cid,)).fetchone()
    if not r or not r[0].startswith(expected):
        problems.append(f"{cid} : attendu « {expected} », trouvé {r[0] if r else 'rien'} -> ignoré")
        continue
    specs = json.loads(r[1] or "{}")
    diff = {k: v for k, v in values.items() if specs.get(k) != v}
    if not diff:
        continue
    changes.append(f"{cid} | {r[0][:45]} | " + ", ".join(f"{k}={v}" for k, v in diff.items()))
    if APPLY:
        db.execute("update components set specs_json=? where id=?",
                   (json.dumps({**specs, **diff}, ensure_ascii=False), cid))

for c in changes[:15]: print(c)
for p in problems: print("!!", p)
print(f"\n{len(changes)} fiche(s) {'MODIFIÉE(S)' if APPLY else 'à modifier (simulation, rien écrit)'}, {len(problems)} ignorée(s)")
if APPLY: db.commit()
