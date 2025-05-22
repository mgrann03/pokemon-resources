import urllib.request
import json

URL_RAIDS = "https://fight.pokebattler.com/raids"

JSON_TIER_PATH = "pogo_pkm_tiers.json"

raid_tiers = [] # array of all raid tiers, from Pokebattler
pkm_tier_map = {} # dict mapping pokemon to their raid tiers

def main():
    
    # loads raid listing
    print("loading raid lists...")
    raid_req = urllib.request.Request(URL_RAIDS, headers = {'User-agent' : 'Tier-Data Loader'}) # No user-agent = 403 ERROR
    raid_tiers = json.load(urllib.request.urlopen(raid_req))['tiers']

    for tier_obj in raid_tiers:
        if not IsValidTier(tier_obj):
            continue

        tier_num = GetTierNum(tier_obj['tier'])
        if tier_num:
            for raid in tier_obj['raids']:
                pkm_name = raid['pokemon']
                if IsRaidMon(pkm_name):
                    pkm_tier_map[pkm_name] = tier_num

    # manually map a few
    pkm_tier_map["TAUROS_PALDEA_AQUA_FORM"] = 3
    pkm_tier_map["TAUROS_PALDEA_BLAZE_FORM"] = 3
    pkm_tier_map["TAUROS_PALDEA_COMBAT_FORM"] = 3
    pkm_tier_map["MAWILE_MEGA"] = 4
    pkm_tier_map["RAYQUAZA_MEGA"] = 6

    print("dumping into JSON file...")
    json.dump(pkm_tier_map, open(JSON_TIER_PATH, "w"), indent=4)

# Filter down to real raid tiers (no shadow duplication, no dynamax, no empty)
def IsValidTier(tier_obj):
    return len(tier_obj['raids']) > 0 \
        and tier_obj['tier'] != "RAID_LEVEL_UNSET" \
        and not 'SHADOW' in tier_obj['tier']\
        and not 'MAX' in tier_obj['tier']

# Map tier names to levels
def GetTierNum(tier_name):
    if "1" in tier_name:
        return 1
    if "3" in tier_name:
        return 3
    if "RAID_LEVEL_MEGA" in tier_name:
        if "RAID_LEVEL_MEGA_5" in tier_name: # Mega/Primal legendary
            return 6
        return 4
    if "5" in tier_name or "ULTRA" in tier_name:
        return 5
    if "ELITE" in tier_name:
        return 7
    
    return 0

# Manually filter a few pokemon that shouldn't be mapped the way they are
def IsRaidMon(pokemon_name):
    invalid_names = ["PHIONE", "MANAPHY",
                     "POIPOLE", "NAGANADEL",
                     "KUBFU", "URSHIFU", 
                     "DIANCIE", 
                     "ETERNATUS", 
                     "VOLCANION",
                     "MAGEARNA",
                     "ZERAORA"]
    for filter_out in invalid_names:
        if filter_out in pokemon_name:
            return False
    return True

if __name__=="__main__":
    main()