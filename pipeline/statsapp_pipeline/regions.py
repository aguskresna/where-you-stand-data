"""Place codes used by the builders (keep in step with backend/questions/modes.json lists; a test checks)."""

US_STATES = [
    ("AL", "Alabama", "01"), ("AK", "Alaska", "02"), ("AZ", "Arizona", "04"), ("AR", "Arkansas", "05"),
    ("CA", "California", "06"), ("CO", "Colorado", "08"), ("CT", "Connecticut", "09"), ("DE", "Delaware", "10"),
    ("DC", "District of Columbia", "11"), ("FL", "Florida", "12"), ("GA", "Georgia", "13"), ("HI", "Hawaii", "15"),
    ("ID", "Idaho", "16"), ("IL", "Illinois", "17"), ("IN", "Indiana", "18"), ("IA", "Iowa", "19"),
    ("KS", "Kansas", "20"), ("KY", "Kentucky", "21"), ("LA", "Louisiana", "22"), ("ME", "Maine", "23"),
    ("MD", "Maryland", "24"), ("MA", "Massachusetts", "25"), ("MI", "Michigan", "26"), ("MN", "Minnesota", "27"),
    ("MS", "Mississippi", "28"), ("MO", "Missouri", "29"), ("MT", "Montana", "30"), ("NE", "Nebraska", "31"),
    ("NV", "Nevada", "32"), ("NH", "New Hampshire", "33"), ("NJ", "New Jersey", "34"), ("NM", "New Mexico", "35"),
    ("NY", "New York", "36"), ("NC", "North Carolina", "37"), ("ND", "North Dakota", "38"), ("OH", "Ohio", "39"),
    ("OK", "Oklahoma", "40"), ("OR", "Oregon", "41"), ("PA", "Pennsylvania", "42"), ("RI", "Rhode Island", "44"),
    ("SC", "South Carolina", "45"), ("SD", "South Dakota", "46"), ("TN", "Tennessee", "47"), ("TX", "Texas", "48"),
    ("UT", "Utah", "49"), ("VT", "Vermont", "50"), ("VA", "Virginia", "51"), ("WA", "Washington", "53"),
    ("WV", "West Virginia", "54"), ("WI", "Wisconsin", "55"), ("WY", "Wyoming", "56"),
]

USPS = [code for code, _, _ in US_STATES]
FIPS_TO_USPS = {int(fips): code for code, _, fips in US_STATES}
US_NAMES = {code: name for code, name, _ in US_STATES}

MY_STATES = [
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Pulau Pinang", "Perak", "Perlis",
    "Sabah", "Sarawak", "Selangor", "Terengganu", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya",
]

ID_PROVINCES = [
    "Aceh", "Sumatera Utara", "Sumatera Barat", "Riau", "Jambi", "Sumatera Selatan", "Bengkulu", "Lampung",
    "Kepulauan Bangka Belitung", "Kepulauan Riau", "DKI Jakarta", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta",
    "Jawa Timur", "Banten", "Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur", "Kalimantan Barat",
    "Kalimantan Tengah", "Kalimantan Selatan", "Kalimantan Timur", "Kalimantan Utara", "Sulawesi Utara",
    "Sulawesi Tengah", "Sulawesi Selatan", "Sulawesi Tenggara", "Gorontalo", "Sulawesi Barat", "Maluku",
    "Maluku Utara", "Papua Barat", "Papua Barat Daya", "Papua", "Papua Selatan", "Papua Tengah", "Papua Pegunungan",
]
