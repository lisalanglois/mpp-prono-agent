"""Alias de noms d'équipes (FR ↔ EN, variantes courantes)."""

TEAM_ALIASES: dict[str, str] = {
    "espagne": "Spain",
    "spain": "Spain",
    "france": "France",
    "allemagne": "Germany",
    "germany": "Germany",
    "angleterre": "England",
    "england": "England",
    "portugal": "Portugal",
    "italie": "Italy",
    "italy": "Italy",
    "pays-bas": "Netherlands",
    "pays bas": "Netherlands",
    "netherlands": "Netherlands",
    "hollande": "Netherlands",
    "belgique": "Belgium",
    "belgium": "Belgium",
    "brésil": "Brazil",
    "bresil": "Brazil",
    "brazil": "Brazil",
    "argentine": "Argentina",
    "argentina": "Argentina",
    "croatie": "Croatia",
    "croatia": "Croatia",
    "maroc": "Morocco",
    "morocco": "Morocco",
    "suisse": "Switzerland",
    "switzerland": "Switzerland",
    "pologne": "Poland",
    "poland": "Poland",
    "autriche": "Austria",
    "austria": "Austria",
    "danemark": "Denmark",
    "denmark": "Denmark",
    "serbie": "Serbia",
    "serbia": "Serbia",
    "slovaquie": "Slovakia",
    "slovakia": "Slovakia",
    "slovénie": "Slovenia",
    "slovenia": "Slovenia",
    "géorgie": "Georgia",
    "georgie": "Georgia",
    "georgia": "Georgia",
    "albanie": "Albania",
    "albania": "Albania",
    "équateur": "Ecuador",
    "equateur": "Ecuador",
    "ecuador": "Ecuador",
    "pérou": "Peru",
    "perou": "Peru",
    "peru": "Peru",
    "chili": "Chile",
    "chile": "Chile",
    "mexique": "Mexico",
    "mexico": "Mexico",
    "afrique du sud": "South Africa",
    "south africa": "South Africa",
    "australie": "Australia",
    "australia": "Australia",
    "arabie saoudite": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "tunisie": "Tunisia",
    "tunisia": "Tunisia",
    "canada": "Canada",
}


# ESPN / API (anglais) → noms grille MPP (français)
EN_TO_FR: dict[str, str] = {
    "Mexico": "Mexique",
    "South Africa": "Afrique du Sud",
    "Korea Republic": "Corée du Sud",
    "South Korea": "Corée du Sud",
    "Czechia": "Tchéquie",
    "Czech Republic": "Tchéquie",
    "Bosnia and Herzegovina": "Bosnie-Herzégovine",
    "Bosnia-Herzegovina": "Bosnie-Herzégovine",
    "United States": "États-Unis",
    "USA": "États-Unis",
    "Paraguay": "Paraguay",
    "Switzerland": "Suisse",
    "Brazil": "Brésil",
    "Morocco": "Maroc",
    "Haiti": "Haïti",
    "Scotland": "Écosse",
    "England": "Angleterre",
    "Croatia": "Croatie",
    "Ghana": "Ghana",
    "Panama": "Panama",
    "Uzbekistan": "Ouzbékistan",
    "Colombia": "Colombie",
    "Qatar": "Qatar",
    "Canada": "Canada",
    "Saudi Arabia": "Arabie saoudite",
    "Uruguay": "Uruguay",
    "Iran": "Iran",
    "IR Iran": "Iran",
    "New Zealand": "Nouvelle-Zélande",
    "France": "France",
    "Senegal": "Sénégal",
    "Iraq": "Irak",
    "Norway": "Norvège",
    "Argentina": "Argentine",
    "Algeria": "Algérie",
    "Austria": "Autriche",
    "Jordan": "Jordanie",
    "Portugal": "Portugal",
    "DR Congo": "RD Congo",
    "Congo DR": "RD Congo",
    "Germany": "Allemagne",
    "Ivory Coast": "Côte d'Ivoire",
    "Cote d'Ivoire": "Côte d'Ivoire",
    "Ecuador": "Équateur",
    "Curacao": "Curaçao",
    "Curaçao": "Curaçao",
    "Tunisia": "Tunisie",
    "Japan": "Japon",
    "Belgium": "Belgique",
    "Cape Verde": "Cap-Vert",
    "Egypt": "Égypte",
    "Netherlands": "Pays-Bas",
    "Sweden": "Suède",
    "Turkey": "Turquie",
    "Australia": "Australie",
    "Spain": "Espagne",
    "Poland": "Pologne",
    "Serbia": "Serbie",
    "Denmark": "Danemark",
    "Italy": "Italie",
    "Chile": "Chili",
    "Peru": "Pérou",
    "Wales": "Pays de Galles",
    "Cameroon": "Cameroun",
    "Nigeria": "Nigeria",
}


def normalize_team(name: str) -> str:
    """Retourne le nom canonique pour recherche dans les datasets."""
    key = name.strip().lower()
    return TEAM_ALIASES.get(key, name.strip())


def to_french(name: str) -> str:
    """Convertit un nom ESPN/API (souvent anglais) vers le libellé grille MPP."""
    n = name.strip()
    if n in EN_TO_FR:
        return EN_TO_FR[n]
    low = n.lower()
    for fr, en in TEAM_ALIASES.items():
        if en.lower() == low:
            # TEAM_ALIASES keys are lowercase variants; find display FR
            pass
    # reverse lookup via alias values
    for alias_key, en_name in TEAM_ALIASES.items():
        if en_name.lower() == low and alias_key[0].islower():
            return alias_key.title() if " " not in alias_key else alias_key
    return n
