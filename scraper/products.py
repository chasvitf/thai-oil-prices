"""One key per fuel, so PTT and Bangchak prices line up even though each brand names them differently."""
import re

# key -> Thai name shown on the site and in Excel, in display order
PRODUCTS = {
    "diesel_b20": "ดีเซล B20",
    "diesel": "ดีเซล",
    "premium_diesel": "ดีเซลพรีเมียม",
    "gasohol_e85": "แก๊สโซฮอล์ E85",
    "gasohol_e20": "แก๊สโซฮอล์ E20",
    "gasohol_91": "แก๊สโซฮอล์ 91",
    "gasohol_95": "แก๊สโซฮอล์ 95",
    "premium_gasohol_95": "แก๊สโซฮอล์ 95 พรีเมียม",
    "benzine_95": "เบนซิน 95",
    "premium_98": "เบนซินพรีเมียม 98+",
}

PREMIUM = ("พรีเมียม", "premium", "superpower", "พาวเวอร์")


def product_key(name: str) -> str:
    """Map a brand's product name to a key in PRODUCTS ("other:<name>" when unknown).

    PTT:      "ดีเซล", "เบนซินแก๊สโซฮอล์ 95", "Super Power GSH95", "Super Power X99", ...
    Bangchak: "ไฮดีเซล S", "แก๊สโซฮอล์ 95 S EVO", "ไฮ พรีเมียม 98 พลัส", ...
    """
    n = re.sub(r"\s+", "", name).lower()
    premium = any(p in n for p in PREMIUM)
    if "b20" in n:
        return "diesel_b20"
    if "ดีเซล" in n or "diesel" in n:
        return "premium_diesel" if premium else "diesel"
    if "e85" in n:
        return "gasohol_e85"
    if "e20" in n:
        return "gasohol_e20"
    if re.search(r"9[89]", n):
        return "premium_98"
    if "แก๊สโซฮอล์" in n or "gasohol" in n or "gsh" in n:
        if "91" in n:
            return "gasohol_91"
        if "95" in n:
            return "premium_gasohol_95" if premium else "gasohol_95"
    if n == "เบนซิน" or n == "เบนซิน95":
        return "benzine_95"
    return f"other:{name.strip()}"
