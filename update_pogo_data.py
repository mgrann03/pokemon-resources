import urllib.request
import requests
import lxml.html
import json
import os
import copy

# global constants and variables

URL_GAME_MASTER = "https://raw.githubusercontent.com/alexelgt/game_masters/refs/heads/master/GAME_MASTER.json"

URL_UNUSED = "https://pokeminers.com/unusedfindings/"

JSON_PKM_PATH = "pogo_pkm.json"
JSON_PKM_PATH_MIN = "pogo_pkm.min.json"
JSON_FM_PATH = "pogo_fm.json"
JSON_CM_PATH = "pogo_cm.json"

pogo_pkm_names = json.load(open("pogo_pkm_names.json"))
pogo_pkm_tiers = json.load(open("pogo_pkm_tiers.json"))

pogo_unused = {} # sets of unused pokemon, forms, shadows and moves

pogo_pkm = [] # pogo pokemon object, will become json file
pogo_fm = [] # pogo fast moves object, will become json file
pogo_cm = [] # pogo charged moves object, will become json file

pogo_seen = set() # set of all seen pokemon, to prevent duplication

move_name_to_id = {} # move name string -> integer ID, for protobuf serialization

type_string_to_enum = {
    "None":     0,
    "Normal":   1,
    "Fire":     2,
    "Water":    3,
    "Grass":    4,
    "Electric": 5,
    "Ice":      6,
    "Fighting": 7,
    "Poison":   8,
    "Ground":   9,
    "Flying":   10,
    "Psychic":  11,
    "Bug":      12,
    "Rock":     13,
    "Ghost":    14,
    "Dragon":   15,
    "Dark":     16,
    "Steel":    17,
    "Fairy":    18,
}

class_string_to_enum = {
    "POKEMON_CLASS_NORMAL":    1,
    "POKEMON_CLASS_LEGENDARY": 2,
    "POKEMON_CLASS_MYTHIC":    3,
}

def main():

    # gets user input
    wants_manual_patch = input("do you want to apply the manual patch? [y/n] ")

    # scrapes relevant unused lists from pokeminers.com into 'pogo_unused'
    print("scraping " + URL_UNUSED + "...")
    html = lxml.html.fromstring(requests.get(URL_UNUSED).content)
    ScrapeList(html, '//ul[@id="Pokémon-list"]/li/text()', 'pokemon')
    ScrapeList(html, '//ul[@id="Forms-list"]/li/text()', 'forms')
    ScrapeList(html, '//ul[@id="Shadows-list"]/li/text()', 'shadows')
    ScrapeList(html, '//ul[@id="Moves-list"]/li/text()', 'moves')

    # loads game master
    print("loading game master...")
    game_master = json.load(urllib.request.urlopen(URL_GAME_MASTER))

    # creates objects from game master
    print("creating objects from game master...")
    for gm_obj in game_master:
        id = gm_obj["templateId"]
        if id[0] == "V" and id[6:13] == "POKEMON" and id.find("REVERSION") == -1:
            AddPokemon(gm_obj)
        if id[0] == "V" and id[6:10] == "MOVE":
            AddMove(gm_obj, id[-4:] == "FAST")

    # if wanted, applies manual patch to objects
    if wants_manual_patch == "y":
        ManualPatch("pogo_pkm_manual_speculative.json")
        ManualPatch("pogo_pkm_manual_moves.json")
        ManualPatch("pogo_pkm_manual_released.json")
        ManualPatch("pogo_pkm_manual_shadow.json")

    # Sort by id, just to ensure everything is in order
    pogo_pkm.sort(key=lambda pkm_obj: pkm_obj['id'])

    # dumps objects into JSON files
    print("dumping objects into JSON files...")
    json.dump(pogo_pkm, open(JSON_PKM_PATH, "w"), indent=4)
    json.dump(pogo_pkm, open(JSON_PKM_PATH_MIN, "w"), separators=(',', ':'))
    json.dump(pogo_fm, open(JSON_FM_PATH, "w"), indent=4)
    json.dump(pogo_cm, open(JSON_CM_PATH, "w"), indent=4)

    # dumps objects into protobuf files
    print("dumping objects into protobuf files...")
    import pogo_pb2

    mc = pogo_pb2.MoveCollection()
    for move_list in (pogo_fm, pogo_cm):
        for m in move_list:
            move = mc.moves[m["id"]]
            move.id = m["id"]
            move.name = m["name"]
            move.type = type_string_to_enum.get(m["type"], pogo_pb2.POKEMON_TYPE_NONE)
            move.power = m["power"]
            move.duration = m["duration"]
            move.damage_window_start = m["damage_window_start"]
            move.damage_window_end = m["damage_window_end"]
            move.energy_delta = m["energy_delta"]
    with open("pogo_moves.pb", "wb") as f:
        f.write(mc.SerializeToString())
    print("  wrote pogo_moves.pb (" + str(len(mc.moves)) + " moves)")

    pc = pogo_pb2.PokemonCollection()
    for pkm in pogo_pkm:
        GetPokemonProto(pc.pokemon.add(), pkm)
    with open("pogo_pkm.pb", "wb") as f:
        f.write(pc.SerializeToString())
    print("  wrote pogo_pkm.pb (" + str(len(pc.pokemon)) + " pokemon)")

    announced_path = "pogo_pkm_manual_announced.json"
    if os.path.exists(announced_path):
        announced = json.load(open(announced_path))
        apc = pogo_pb2.PokemonCollection()
        for pkm in announced:
            GetPokemonProto(apc.pokemon.add(), pkm)
        with open("pogo_pkm_manual_announced.pb", "wb") as f:
            f.write(apc.SerializeToString())
        print("  wrote pogo_pkm_manual_announced.pb (" + str(len(apc.pokemon)) + " entries)")

    #os.system("pause")

def GetPokemonProto(p, pkm):
    p.id = pkm["id"]
    p.name = pkm["name"]
    p.form = pkm.get("form", "Normal")
    for t in pkm.get("types", []):
        p.types.append(type_string_to_enum.get(t, 0))
    if "stats" in pkm:
        p.stats.base_stamina = pkm["stats"]["baseStamina"]
        p.stats.base_attack = pkm["stats"]["baseAttack"]
        p.stats.base_defense = pkm["stats"]["baseDefense"]
    for move_name in pkm.get("fm", []):
        if move_name in move_name_to_id:
            p.fm.append(move_name_to_id[move_name])
        else:
            print("  WARNING: unknown FM '" + move_name + "' for " + pkm["name"] + " (" + pkm.get("form", "Normal") + ")")
    for move_name in pkm.get("cm", []):
        if move_name in move_name_to_id:
            p.cm.append(move_name_to_id[move_name])
        else:
            print("  WARNING: unknown CM '" + move_name + "' for " + pkm["name"] + " (" + pkm.get("form", "Normal") + ")")
    for move_name in pkm.get("elite_fm", []):
        if move_name in move_name_to_id:
            p.elite_fm.append(move_name_to_id[move_name])
        else:
            print("  WARNING: unknown elite FM '" + move_name + "' for " + pkm["name"] + " (" + pkm.get("form", "Normal") + ")")
    for move_name in pkm.get("elite_cm", []):
        if move_name in move_name_to_id:
            p.elite_cm.append(move_name_to_id[move_name])
        else:
            print("  WARNING: unknown elite CM '" + move_name + "' for " + pkm["name"] + " (" + pkm.get("form", "Normal") + ")")
    p.shadow = pkm.get("shadow", False)
    p.released = pkm.get("released", False)
    p.raid_tier = pkm.get("raid_tier", 0)
    if "class" in pkm:
        setattr(p, "class", class_string_to_enum.get(pkm["class"], 0))
    p.mega = pkm.get("mega", False)

def ScrapeList(html, xpath, name):
    lis = html.xpath(xpath)
    pogo_unused[name] = set()
    for li in lis:
        pkm = li.replace(' ', '').replace('\n', '').replace('\r', '')
        pogo_unused[name].add(pkm)
    print(" " + str(len(lis)) + " unused " + name + " found")

def AddPokemon(gm_obj):

    #print(gm_obj["templateId"])

    gm_obj_s = gm_obj["data"]["pokemonSettings"]

    pkm_obj = {}
    pkm_obj["id"] = int(gm_obj["templateId"][1:5])
    pkm_obj["name"] = pogo_pkm_names[pkm_obj["id"]]
    if "form" in gm_obj_s and isinstance(gm_obj_s["form"], str):
        form = gm_obj_s["form"]
        if gm_obj_s["pokemonId"] in form:
            form = form.replace(gm_obj_s["pokemonId"], "")[1:]
        pkm_obj["form"] = form.capitalize()
    else:
        pkm_obj["form"] = "Normal"
    pkm_obj["types"] = []
    pkm_obj["types"].append(CleanType(gm_obj_s["type"]))
    if "type2" in gm_obj_s:
        pkm_obj["types"].append(CleanType(gm_obj_s["type2"]))
    pkm_obj["stats"] = gm_obj_s["stats"]
    if "quickMoves" in gm_obj_s:
        pkm_obj["fm"] = CleanMoves(gm_obj_s["quickMoves"], True)
    if "cinematicMoves" in gm_obj_s:
        pkm_obj["cm"] = CleanMoves(gm_obj_s["cinematicMoves"], False)
    if "eliteQuickMove" in gm_obj_s:
        pkm_obj["elite_fm"] = CleanMoves(gm_obj_s["eliteQuickMove"], True)
    if "eliteCinematicMove" in gm_obj_s:
        pkm_obj["elite_cm"] = CleanMoves(gm_obj_s["eliteCinematicMove"], False)
    pkm_obj["shadow"] = "shadow" in gm_obj_s
    #if pkm_obj["shadow"]:
    #    pkm_obj["shadow_released"] = (gm_obj["templateId"][14:] + "_SHADOW") not in pogo_unused["shadows"]
    #else:
    #    pkm_obj["shadow_released"] = False
    if "pokemonClass" in gm_obj_s:
        pkm_obj["class"] = gm_obj_s["pokemonClass"]
    pkm_obj["released"] = PokemonIsReleased(gm_obj_s)

    tier = pogo_pkm_tiers.get(gm_obj["templateId"][14:], 0)
    if not tier:
        tier = pogo_pkm_tiers.get(gm_obj["templateId"][14:] + "_FORM", 0)
    if tier:
        pkm_obj["raid_tier"] = tier

    pkm_uniq_id = pkm_obj["name"] + "-" + str(pkm_obj["id"]) + "-" + pkm_obj["form"]
    if pkm_uniq_id not in pogo_seen:
        pogo_pkm.append(pkm_obj)
        pogo_seen.add(pkm_uniq_id)

        if "tempEvoOverrides" in gm_obj_s:
            for gm_obj_s_mega in gm_obj_s["tempEvoOverrides"]:
                if "tempEvoId" not in gm_obj_s_mega or \
                    ("MEGA" not in gm_obj_s_mega["tempEvoId"] and "PRIMAL" not in gm_obj_s_mega["tempEvoId"]):
                    continue

                mega_obj = {
                    "id": pkm_obj["id"],
                    "name": pkm_obj["name"],
                    "form": "Mega",
                    "fm": pkm_obj["fm"],
                    "cm": pkm_obj["cm"],
                    "shadow": False,
                    "released": pkm_obj["released"],
                    "mega": True
                }

                tier = pogo_pkm_tiers.get(gm_obj["templateId"][14:] + "_MEGA", 0)
                if not tier:
                    tier = pogo_pkm_tiers.get(gm_obj["templateId"][14:] + gm_obj_s_mega["tempEvoId"][-7:], 0)
                if tier:
                    mega_obj["raid_tier"] = tier

                if "class" in pkm_obj:
                    mega_obj["class"] = pkm_obj["class"]
                if "elite_fm" in pkm_obj:
                    mega_obj["elite_fm"] = pkm_obj["elite_fm"]
                if "elite_cm" in pkm_obj:
                    mega_obj["elite_cm"] = pkm_obj["elite_cm"]

                if pkm_obj["id"] == 382 or pkm_obj["id"] == 383:
                    mega_obj["name"] = "Primal " + mega_obj["name"]
                else:
                    mega_obj["name"] = "Mega " + mega_obj["name"]

                mega_types = []
                if "typeOverride1" in gm_obj_s_mega:
                    mega_types.append(CleanType(gm_obj_s_mega["typeOverride1"]))
                if "typeOverride2" in gm_obj_s_mega:
                    mega_types.append(CleanType(gm_obj_s_mega["typeOverride2"]))
                if mega_types:
                    mega_obj["types"] = mega_types
                if "stats" in gm_obj_s_mega:
                    mega_obj["stats"] = gm_obj_s_mega["stats"]
                if "MEGA_X" in gm_obj_s_mega["tempEvoId"]:
                    mega_obj["name"] = mega_obj["name"] + " X"
                elif "MEGA_Y" in gm_obj_s_mega["tempEvoId"]:
                    mega_obj["name"] = mega_obj["name"] + " Y"
                    mega_obj["form"] = mega_obj["form"] + "Y"

                mega_uniq_id = mega_obj["name"] + "-" + str(mega_obj["id"]) + "-" + mega_obj["form"]
                if mega_uniq_id not in pogo_seen:
                    pogo_pkm.append(mega_obj)
                    pogo_seen.add(mega_uniq_id)

def PokemonIsReleased(gm_obj_s):
    released = gm_obj_s["pokemonId"] not in pogo_unused["pokemon"]
    if released and "form" in gm_obj_s:
        released = gm_obj_s["form"] not in pogo_unused["forms"]
    return released

def AddMove(gm_obj, is_fast):

    #print(gm_obj["templateId"])

    gm_obj_s = gm_obj["data"]["moveSettings"]

    move_obj = {}
    move_obj["id"] = int(gm_obj["templateId"][1:5])
    move_obj["name"] = CleanMove(gm_obj_s["movementId"], is_fast)
    move_obj["type"] = CleanType(gm_obj_s["pokemonType"])
    if "power" in gm_obj_s:
        move_obj["power"] = gm_obj_s["power"]
    else:
        move_obj["power"] = 0
    move_obj["duration"] = gm_obj_s["durationMs"]
    if "damageWindowStartMs" in gm_obj_s:
        move_obj["damage_window_start"] = gm_obj_s["damageWindowStartMs"]
    else:
        move_obj["damage_window_start"] = 0
    move_obj["damage_window_end"] = gm_obj_s["damageWindowEndMs"]
    if "energyDelta" in gm_obj_s:
        move_obj["energy_delta"] = gm_obj_s["energyDelta"]
    else:
        move_obj["energy_delta"] = 0

    if is_fast:
        pogo_fm.append(move_obj)
    else:
        pogo_cm.append(move_obj)

    move_name_to_id[move_obj["name"]] = move_obj["id"]

    # checks for Hidden Power and adds corresponding moves
    HIDDEN_POWER_TYPES = ["Fire", "Water", "Grass", "Electric", "Ice",
                          "Fighting", "Poison", "Ground", "Flying", "Psychic",
                          "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel"]
    if move_obj["name"] == "Hidden Power" and is_fast:
        hp_variant_id = 1000
        for type in HIDDEN_POWER_TYPES:
            hp_variant_id += 1
            hidden_power_move_obj = copy.copy(move_obj)
            hidden_power_move_obj["name"] += " " + type
            hidden_power_move_obj["type"] = type
            hidden_power_move_obj["id"] = hp_variant_id
            pogo_fm.append(hidden_power_move_obj)
            move_name_to_id[hidden_power_move_obj["name"]] = hp_variant_id

def CleanType(type):
    return type[13:].capitalize()

def CleanMoves(moves, is_fast):
    clean_moves = []
    for move in moves:
        clean_moves.append(CleanMove(move, is_fast))
    return clean_moves

def CleanMove(move, is_fast):
    if move == "V0462_MOVE_FORCE_PALM_FAST":
        return "Force Palm"
    elif move == "SUPER_POWER": # Should be 1 word
        return "Superpower"
    elif move == "LOCK_ON_FAST": # Should be hyphenated
        return "Lock-On"
    elif move == "POWER_UP_PUNCH": # Should be hyphenated
        return "Power-Up Punch"
    elif move == "V_CREATE": # Should be hyphenated
        return "V-create"
    elif move == "X_SCISSOR": # Should be hyphenated
        return "X-Scissor"
    elif move == "MUD_SLAP_FAST": # Should be hyphenated
        return "Mud-Slap"
    elif move == "NATURES_MADNESS": # Should be possessive
        return "Nature's Madness"
    elif move == "PYROBALL": # Should be 2 words
        return "Pyro Ball"
    elif move == "FUTURESIGHT": # Should be 2 words
        return "Future Sight"
    elif move == "VICE_GRIP": # Should be Vise
        return "Vise Grip"
    elif isinstance(move, str):
        return (move[:-5] if is_fast else move).replace("_", " ").title()
    else: # if move isn't a string...
        if move == 387:
            return "Geomancy"
        elif move == 389:
            return "Oblivion Wing"
        elif move == 391:
            return "Triple Axel"
        elif move == 392:
            return "Trailblaze"
        elif move == 393:
            return "Scorching Sands"
        else:
            return str(move)

def ManualPatch(patch_fname):
    """
    Modifies 'pogo_pkm' values to match values in 'patch_fname'.
    """
    print("applying manual patch to objects...")

    pogo_pkm_manual = json.load(open(patch_fname))
    num_changes = 0

    for pkm_obj in pogo_pkm:
        for manual_obj in list(pogo_pkm_manual):
            if pkm_obj["id"] == manual_obj["id"] and pkm_obj["name"] == manual_obj["name"] and pkm_obj["form"] == manual_obj["form"]:
                for key in ["fm", "cm", "elite_fm", "elite_cm", "shadow", "released", "mega"]:
                    if key in manual_obj:
                        if key in pkm_obj and pkm_obj[key] == manual_obj[key]:
                            name = pkm_obj["name"] + ("(" + pkm_obj["form"] + ")" if (pkm_obj["form"] != "Normal") else "")
                            print(" " + name + "[" + key + "] -> manual change is redundant!")
                        else:
                            pkm_obj[key] = manual_obj[key]
                            num_changes += 1
                pogo_pkm_manual.remove(manual_obj)

    for manual_obj in pogo_pkm_manual: # not matched and consumed above
        pogo_pkm.append(manual_obj)
    
    print(" " + str(num_changes) + " changes done")

if __name__=="__main__":
    main()
