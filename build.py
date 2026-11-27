"""Build a standalone mod ZIP from original code and optional local mod donors."""

from argparse import ArgumentParser
from pathlib import Path
from re import search
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
COMMON = "unholy_npc_rescue.script"
MONOLITH = "zzz_unholy_npc_rescue_monolith.script"


def replace_once(text, anchor, replacement, filename):
    if text.count(anchor) != 1:
        raise ValueError(f"{filename} has a different revision or is already patched. Use the original supported donor.")
    return text.replace(anchor, replacement, 1)


def read_script(path):
    data = path.read_bytes()
    # Lua scripts may use legacy encodings. Latin-1 preserves untouched bytes.
    return data.decode("latin-1"), "\r\n" if b"\r\n" in data else "\n"


def patch_gbo(path):
    source, newline = read_script(path)
    source = source.replace("\r\n", "\n")
    if source.count("function npc_on_before_hit(npc,shit,bone_id)") != 1:
        raise ValueError(f"{path.name} has no supported NPC damage handler")
    anchor = (
        "\tif surrender_bonus == 1 then\n"
        "\t\tnpc:set_health_ex(0.0)\n"
        "\telse\n"
        "\t\tnpc:set_health_ex(npc.health - life_remove)\n"
        "\tend"
    )
    replacement = (
        "\tif surrender_bonus == 1 then\n"
        "\t\tnpc:set_health_ex(0.0)\n"
        "\telse\n"
        "\t\tlocal remaining = unholy_npc_rescue.remaining_health(npc, bone_id, npc.health - life_remove)\n"
        "\t\tnpc:set_health_ex(remaining)\n"
        "\tend"
    )
    source = replace_once(source, anchor, replacement, path.name)
    return source.replace("\n", newline).encode("latin-1")


def patch_companion(path):
    source, newline = read_script(path)
    source = source.replace("\r\n", "\n")
    function = (
        'function CB_npc_on_before_hit(npc, shit, bone_id, flags)\n'
        '\tif not npc:has_info("npcx_is_companion") then return end'
    )
    guard = (
        'function CB_npc_on_before_hit(npc, shit, bone_id, flags)\n'
        '\tif unholy_npc_rescue.is_head_hit(npc, bone_id) or unholy_npc_rescue.is_player_replica(npc)\n'
        '\t\tor not npc:has_info("npcx_is_companion") then return end'
    )
    source = replace_once(source, function, guard, path.name)
    source = replace_once(source, '\tlocal headshot = is_head_bone(bone_id)\n', '', path.name)
    source = replace_once(source, '\tif headshot or lethal then', '\tif lethal then', path.name)
    anchor = (
        '\tlocal base = m.npc_on_before_hit\n'
        '\tlocal function wrapped(npc, shit, bone_id, flags)\n'
        '\t\tif npc and downed_companions[npc:id()] then return end'
    )
    replacement = (
        '\tlocal base = m.npc_on_before_hit\n'
        '\tlocal function wrapped(npc, shit, bone_id, flags)\n'
        '\t\tif npc and (unholy_npc_rescue.is_head_hit(npc, bone_id) or unholy_npc_rescue.is_player_replica(npc)) then\n'
        '\t\t\treturn base(npc, shit, bone_id, flags)\n'
        '\t\tend\n'
        '\t\tif npc and downed_companions[npc:id()] then return end'
    )
    source = replace_once(source, anchor, replacement, path.name)
    head_helper = '\treturn bone_id == 15 or bone_id == 16 or bone_id == 17 or bone_id == 18 or bone_id == 19\n'
    # Drop the donor helper if it has no remaining references after these edits.
    if not search(r"(?m)^(?!local function is_head_bone\().*\bis_head_bone\(", source):
        source = replace_once(source, 'local function is_head_bone(bone_id)\n' + head_helper + 'end\n\n', '', path.name)
    return source.replace("\n", newline).encode("latin-1")


def build(output, gbo=None, companion=None):
    if companion and not gbo:
        raise ValueError("The Romeo companion patch also requires its active GBO donor")
    scripts = {COMMON: (ROOT / "gamedata/scripts" / COMMON).read_bytes()}
    if gbo:
        scripts["grok_bo.script"] = patch_gbo(gbo)
    else:
        scripts[MONOLITH] = (ROOT / "gamedata/scripts" / MONOLITH).read_bytes()
    if companion:
        scripts["companion_dbno.script"] = patch_companion(companion)

    with ZipFile(output, "x", ZIP_DEFLATED) as archive:
        for name, data in scripts.items():
            archive.writestr("gamedata/scripts/" + name, data)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP verification failed")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--gbo", type=Path, help="Winning unmodified grok_bo.script")
    parser.add_argument("--companion", type=Path, help="Winning unmodified Romeo companion_dbno.script")
    args = parser.parse_args()
    try:
        build(**vars(args))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
