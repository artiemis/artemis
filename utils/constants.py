from utils.common import read_json

MAX_DISCORD_SIZE = 25 * 1024**2
MAX_API_SIZE = 200 * 1024**2
MAX_CATBOX_SIZE = 200 * 1024**2
MAX_LITTERBOX_SIZE = 1024**3

WIKT_LANGUAGES = read_json("data/wiktionary-languages.json")

TEEHEE_EMOJIS = [
    "<:teehee:825098257742299136>",
    "<:teehee2:825098258741067787>",
    "<:teehee3:825098263820632066>",
    "<:teehee4:825098262884778026>",
    "<:teehee5:825098263437901825>",
]

RIP_EMOJIS = [
    "<:rip:825101664939147285>",
    "<:rip2:825101666373206086>",
    "<:rip3:825101667434889236>",
    "<:rip4:825101668428546058>",
    "<:rip5:825101671436255243>",
]


TESSERACT_LANGUAGES = [
    "ara",
    "ces",
    "chi_sim",
    "chi_sim_vert",
    "chi_tra",
    "chi_tra_vert",
    "deu",
    "eng",
    "fra",
    "heb",
    "hun",
    "ind",
    "ita",
    "jpn",
    "jpn_vert",
    "kor",
    "kor_vert",
    "msa",
    "pol",
    "rus",
    "slk",
    "slv",
    "spa",
    "ukr",
]


GT_LANGUAGES_EXTRAS = {
    "as": "assamese",
    "ay": "aymara",
    "bm": "bambara",
    "bho": "bhojpuri",
    "dv": "dhivehi",
    "doi": "dogri",
    "ee": "ewe",
    "gn": "guarani",
    "ilo": "ilocano",
    "rw": "kinyarwanda",
    "gom": "konkani",
    "kri": "krio",
    "ckb": "kurdish (sorani)",
    "ln": "lingala",
    "lg": "luganda",
    "mai": "maithili",
    "mni-mtei": "meiteilon (manipuri)",
    "lus": "mizo",
    "om": "oromo",
    "qu": "quechua",
    "sa": "sanskrit",
    "nso": "sepedi",
    "tt": "tatar",
    "ti": "tigrinya",
    "ts": "tsonga",
    "tk": "turkmen",
    "ak": "twi",
}


COMMON_TIMEZONES = {
    "pt": "US/Pacific",
    "pst": "US/Pacific",
    "mst": "US/Mountain",
    "mt": "US/Mountain",
    "cst": "US/Central",
    "ct": "US/Central",
    "est": "US/Eastern",
    "et": "US/Eastern",
    "wib": "Asia/Jakarta",
    "wita": "Asia/Makassar",
    "wit": "Asia/Jayapura",
    "cet": "Europe/Warsaw",
    "cest": "Europe/Warsaw",
    "msk": "Europe/Moscow",
    "eet": "Europe/Moscow",
    "eest": "Europe/Moscow",
}

COMMON_COLOURS = {
    "Almond": "#EFDECD",
    "Antique Brass": "#CD9575",
    "Apricot": "#FDD9B5",
    "Aquamarine": "#78DBE2",
    "Asparagus": "#87A96B",
    "Atomic Tangerine": "#FFA474",
    "Banana Mania": "#FAE7B5",
    "Beaver": "#9F8170",
    "Bittersweet": "#FD7C6E",
    "Black": "#000000",
    "Blizzard Blue": "#ACE5EE",
    "Blue": "#1F75FE",
    "Blue Bell": "#A2A2D0",
    "Blue Gray": "#6699CC",
    "Blue Green": "#0D98BA",
    "Blue Violet": "#7366BD",
    "Blush": "#DE5D83",
    "Brick Red": "#CB4154",
    "Brown": "#B4674D",
    "Burnt Orange": "#FF7F49",
    "Burnt Sienna": "#EA7E5D",
    "Cadet Blue": "#B0B7C6",
    "Canary": "#FFFF99",
    "Caribbean Green": "#1CD3A2",
    "Carnation Pink": "#FFAACC",
    "Cerise": "#DD4492",
    "Cerulean": "#1DACD6",
    "Chestnut": "#BC5D58",
    "Copper": "#DD9475",
    "Cornflower": "#9ACEEB",
    "Cotton Candy": "#FFBCD9",
    "Dandelion": "#FDDB6D",
    "Denim": "#2B6CC4",
    "Desert Sand": "#EFCDB8",
    "Eggplant": "#6E5160",
    "Electric Lime": "#CEFF1D",
    "Fern": "#71BC78",
    "Forest Green": "#6DAE81",
    "Fuchsia": "#C364C5",
    "Fuzzy Wuzzy": "#CC6666",
    "Gold": "#E7C697",
    "Goldenrod": "#FCD975",
    "Granny Smith Apple": "#A8E4A0",
    "Gray": "#95918C",
    "Green": "#1CAC78",
    "Green Blue": "#1164B4",
    "Green Yellow": "#F0E891",
    "Hot Magenta": "#FF1DCE",
    "Inchworm": "#B2EC5D",
    "Indigo": "#5D76CB",
    "Jazzberry Jam": "#CA3767",
    "Jungle Green": "#3BB08F",
    "Laser Lemon": "#FEFE22",
    "Lavender": "#FCB4D5",
    "Lemon Yellow": "#FFF44F",
    "Macaroni and Cheese": "#FFBD88",
    "Magenta": "#F664AF",
    "Magic Mint": "#AAF0D1",
    "Mahogany": "#CD4A4C",
    "Maize": "#EDD19C",
    "Manatee": "#979AAA",
    "Mango Tango": "#FF8243",
    "Maroon": "#C8385A",
    "Mauvelous": "#EF98AA",
    "Melon": "#FDBCB4",
    "Midnight Blue": "#1A4876",
    "Mountain Meadow": "#30BA8F",
    "Mulberry": "#C54B8C",
    "Navy Blue": "#1974D2",
    "Neon Carrot": "#FFA343",
    "Olive Green": "#BAB86C",
    "Orange": "#FF7538",
    "Orange Red": "#FF2B2B",
    "Orange Yellow": "#F8D568",
    "Orchid": "#E6A8D7",
    "Outer Space": "#414A4C",
    "Outrageous Orange": "#FF6E4A",
    "Pacific Blue": "#1CA9C9",
    "Peach": "#FFCFAB",
    "Periwinkle": "#C5D0E6",
    "Piggy Pink": "#FDDDE6",
    "Pine Green": "#158078",
    "Pink Flamingo": "#FC74FD",
    "Pink Sherbet": "#F78FA7",
    "Plum": "#8E4585",
    "Purple Heart": "#7442C8",
    "Purple Mountain's Majesty": "#9D81BA",
    "Purple Pizzazz": "#FE4EDA",
    "Radical Red": "#FF496C",
    "Raw Sienna": "#D68A59",
    "Raw Umber": "#714B23",
    "Razzle Dazzle Rose": "#FF48D0",
    "Razzmatazz": "#E3256B",
    "Red": "#EE204D",
    "Red Orange": "#FF5349",
    "Red Violet": "#C0448F",
    "Robin's Egg Blue": "#1FCECB",
    "Royal Purple": "#7851A9",
    "Salmon": "#FF9BAA",
    "Scarlet": "#FC2847",
    "Screamin' Green": "#76FF7A",
    "Sea Green": "#9FE2BF",
    "Sepia": "#A5694F",
    "Shadow": "#8A795D",
    "Shamrock": "#45CEA2",
    "Shocking Pink": "#FB7EFD",
    "Silver": "#CDC5C2",
    "Sky Blue": "#80DAEB",
    "Spring Green": "#ECEABE",
    "Sunglow": "#FFCF48",
    "Sunset Orange": "#FD5E53",
    "Tan": "#FAA76C",
    "Teal Blue": "#18A7B5",
    "Thistle": "#EBC7DF",
    "Tickle Me Pink": "#FC89AC",
    "Timberwolf": "#DBD7D2",
    "Tropical Rain Forest": "#17806D",
    "Tumbleweed": "#DEAA88",
    "Turquoise Blue": "#77DDE7",
    "Unmellow Yellow": "#FFFF66",
    "Violet (Purple)": "#926EAE",
    "Violet Blue": "#324AB2",
    "Violet Red": "#F75394",
    "Vivid Tangerine": "#FFA089",
    "Vivid Violet": "#8F509D",
    "White": "#FFFFFF",
    "Wild Blue Yonder": "#A2ADD0",
    "Wild Strawberry": "#FF43A4",
    "Wild Watermelon": "#FC6C85",
    "Wisteria": "#CDA4DE",
    "Yellow": "#FCE883",
    "Yellow Green": "#C5E384",
    "Yellow Orange": "#FFAE42",
}

SUPPORTED_CURRENCIES = [
    "AUD",
    "BGN",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HRK",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "ISK",
    "JPY",
    "KRW",
    "MXN",
    "MYR",
    "NOK",
    "NZD",
    "PHP",
    "PLN",
    "RON",
    "RUB",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "USD",
    "ZAR",
]
