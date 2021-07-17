preset_locations = lambda: ["workspace/presets/", "workspace", "package/presets/"]
device_locations = lambda: ["workspace/devices/", "package/devices/"]
theme_locations = lambda: ["workspace/assets/", "workspace", "package/assets"]
asset_locations = lambda: ["workspace/assets/", "workspace", "package/assets/"]

def config_locations():
    import os
    import platform
    from pathlib import Path

    if platform.system() == "Linux":
        home_dir = os.path.expanduser("~")
        xdg_config_dir = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home_dir, ".config")
        config_dir = os.path.join(xdg_config_dir, "ev3sim")
        # Ensure config dir exists
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        return ["workspace", "local|" + config_dir]

    return ["workspace", "package"]

def code_locations(bot_path):
    from ev3sim.file_helper import find_abs_directory

    # First, match the bot path to a bot_location.
    for location in bot_locations():
        actual_dir = find_abs_directory(location)
        if bot_path.startswith(actual_dir):
            break
    else:
        raise ValueError(f"Bot path {bot_path} does not appear in any valid bot location.")
    relative = location + bot_path[len(actual_dir) :]
    return [relative]


def batch_locations():
    """Batch files can also be in the custom folders."""
    import os
    from ev3sim.file_helper import find_abs_directory
    from ev3sim.simulation.loader import StateHandler

    locations = ["package/presets/"]
    if StateHandler.WORKSPACE_FOLDER:
        custom_path = find_abs_directory("workspace/custom/", create=True)
        for name in os.listdir(custom_path):
            if os.path.isdir(os.path.join(custom_path, name)):
                locations.append(f"workspace/custom/{name}/")
    return locations


def bot_locations():
    import os
    from ev3sim.file_helper import find_abs_directory
    from ev3sim.simulation.loader import StateHandler

    locations = ["workspace/robots/", "package/examples/robots/", "workspace"]
    if StateHandler.WORKSPACE_FOLDER:
        custom_path = find_abs_directory("workspace/custom/", create=True)
        for name in os.listdir(custom_path):
            if os.path.isdir(os.path.join(custom_path, name)):
                # Favour custom locations over the catch-all workspace entry.
                locations.insert(2, f"workspace/custom/{name}/")
    return locations
