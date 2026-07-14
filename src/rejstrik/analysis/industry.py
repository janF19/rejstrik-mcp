from __future__ import annotations

from collections import Counter

from rejstrik.analysis.industry_multiples import FALLBACK_INDUSTRY_KEY

# Ported verbatim from ~/projects/obchodni-rejstrik-ai
# apps/api/services/business_classification.py (NACE_DIVISION_MAP).
NACE_DIVISION_MAP = {
    "01": "farming_agriculture",
    "02": "paper_forest_products",
    "03": "farming_agriculture",
    "05": "coal_related_energy",
    "06": "oil_gas_production_and_exploration",
    "07": "metals_mining",
    "08": "construction_supplies",
    "09": "oilfield_svcs_equip",
    "10": "food_processing",
    "11": "beverage_alcoholic",
    "12": "tobacco",
    "13": "apparel",
    "14": "apparel",
    "15": "shoe",
    "16": "furn_home_furnishings",
    "17": "paper_forest_products",
    "18": "publishing_newspapers",
    "19": "oil_gas_distribution",
    "20": "chemical_diversified",
    "21": "drugs_pharmaceutical",
    "22": "rubber_tires",
    "23": "building_materials",
    "24": "steel",
    "25": "machinery",
    "26": "electronics_general",
    "27": "electrical_equipment",
    "28": "machinery",
    "29": "auto_truck",
    "30": "shipbuilding_marine",
    "31": "furn_home_furnishings",
    "32": "healthcare_products",
    "33": "machinery",
    "35": "power",
    "36": "utility_water",
    "37": "environmental_waste_services",
    "38": "environmental_waste_services",
    "39": "environmental_waste_services",
    "41": "homebuilding",
    "42": "engineering_construction",
    "43": "engineering_construction",
    "45": "retail_automotive",
    "46": "retail_distributors",
    "47": "retail_general",
    "49": "transportation",
    "50": "shipbuilding_marine",
    "51": "air_transport",
    "52": "transportation",
    "53": "transportation",
    "55": "hotel_gaming",
    "56": "restaurant_dining",
    "58": "publishing_newspapers",
    "59": "entertainment",
    "60": "broadcasting",
    "61": "telecom_services",
    "62": "software_system_application",
    "63": "information_services",
    "64": FALLBACK_INDUSTRY_KEY,
    "65": FALLBACK_INDUSTRY_KEY,
    "66": FALLBACK_INDUSTRY_KEY,
    "68": "real_estate_operations_services",
    "69": "business_consumer_services",
    "70": "business_consumer_services",
    "71": "engineering_construction",
    "72": "business_consumer_services",
    "73": "advertising",
    "74": "business_consumer_services",
    "75": "healthcare_support_services",
    "77": "business_consumer_services",
    "78": "business_consumer_services",
    "79": "recreation",
    "80": "business_consumer_services",
    "81": "environmental_waste_services",
    "82": "office_equipment_services",
    "85": "education",
    "86": "hospitals_healthcare_facilities",
    "87": "healthcare_support_services",
    "88": "healthcare_support_services",
    "90": "entertainment",
    "91": "recreation",
    "92": "hotel_gaming",
    "93": "recreation",
    "94": "business_consumer_services",
    "95": "business_consumer_services",
    "96": "business_consumer_services",
}


def _division_priority(division: str) -> int:
    value = int(division)
    if 10 <= value <= 33:
        return 0
    if 45 <= value <= 47:
        return 2
    return 1


def industry_key_for_nace(nace_codes: list[str]) -> tuple[str, str]:
    """Map a list of CZ-NACE codes to a Damodaran industry key and a human
    reason. Manufacturing divisions (10-33) win over retail (45-47) over the
    rest; ties break by frequency then first-seen order (ported selection
    logic). Empty or unmapped input returns the market fallback."""
    divisions: list[str] = []
    for code in nace_codes:
        digits = "".join(ch for ch in str(code) if ch.isdigit())
        if len(digits) >= 2 and digits[:2] in NACE_DIVISION_MAP:
            divisions.append(digits[:2])
    if not divisions:
        return (
            FALLBACK_INDUSTRY_KEY,
            "no mapped NACE division; using generic market fallback",
        )
    counts = Counter(divisions)
    first_seen = {division: divisions.index(division) for division in counts}
    selected = min(
        counts,
        key=lambda division: (
            _division_priority(division),
            -counts[division],
            first_seen[division],
        ),
    )
    target = NACE_DIVISION_MAP[selected]
    return target, f"NACE {int(selected)} → {target}"
