import pygame
import pygame_gui
import pymunk
import yaml
import numpy as np
from ev3sim.file_helper import find_abs
from ev3sim.objects.base import STATIC_CATEGORY
from ev3sim.robot import add_devices
from ev3sim.simulation.randomisation import Randomiser
from ev3sim.visual.menus.base_menu import BaseMenu
from ev3sim.visual.manager import ScreenObjectManager
from ev3sim.visual.utils import screenspace_to_worldspace
from ev3sim.search_locations import asset_locations


class BotEditMenu(BaseMenu):

    onSave = None

    MODE_DEVICE_DIALOG = "DEVICE_SELECT"
    MODE_NORMAL = "NORMAL"
    MODE_COLOUR_DIALOG = "COLOUR"
    MODE_BASEPLATE_DIALOG = "BASEPLATE"

    SELECTED_CIRCLE = "CIRCLE"
    SELECTED_POLYGON = "POLYGON"
    SELECTED_NOTHING = "NOTHING"
    SELECTED_DEVICE = "DEVICE"

    BASE_ZPOS = 1
    OBJ_ZPOS = 2
    DEV_ZPOS = 3
    HOLD_ZPOS = 4

    def clearEvents(self):
        self.onSave = None

    def initWithKwargs(self, **kwargs):
        self.current_mpos = (0, 0)
        self.selected_index = None
        self.selected_type = self.SELECTED_NOTHING
        self.lock_grid = True
        self.grid_size = 1
        self.dragging = False
        self.bot_dir_file = kwargs.get("bot_dir_file", None)
        self.bot_file = kwargs.get("bot_file", None)
        self.current_holding = None
        if self.bot_dir_file is None or self.bot_file is None:
            if (self.bot_dir_file is not None) or (self.bot_dir_file is not None):
                raise ValueError(
                    f"bot_dir_file and bot_file are required here. Got {self.bot_dir_file} and {self.bot_file}."
                )
            self.creating = True
            self.mode = self.MODE_BASEPLATE_DIALOG
            self.previous_info = {}
            self.current_object = {}
            self.current_devices = []
        else:
            self.creating = False
            self.mode = self.MODE_NORMAL
            with open(self.bot_file, "r") as f:
                bot = yaml.safe_load(f)
            self.previous_info = bot
            self.current_object = bot["base_plate"]
            self.current_object["type"] = "object"
            self.current_object["physics"] = True
            self.current_devices = bot["devices"]
        super().initWithKwargs(**kwargs)
        self.resetBotVisual()
        if self.mode == self.MODE_BASEPLATE_DIALOG:
            self.addBaseplatePicker()

    def getSelectedAttribute(self, attr, fallback=None):
        if self.selected_index is None:
            raise ValueError("Nothing selected.")
        elif self.selected_index == "Holding":
            return self.current_holding_kwargs.get(attr, fallback)
        elif self.selected_index == "Baseplate":
            return self.current_object["visual"].get(attr, fallback)
        elif self.selected_index[0] == "Children":
            return self.current_object["children"][self.selected_index[1]]["visual"].get(attr, fallback)
        elif self.selected_index[0] == "Devices":
            # Just one key in this dict.
            for key in self.current_devices[self.selected_index[1]]:
                return self.current_devices[self.selected_index[1]][key].get(attr, fallback)
        raise ValueError(f"Unknown selection {self.selected_index}")

    def setSelectedAttribute(self, attr, val):
        if self.selected_index is None:
            raise ValueError("Nothing selected.")
        elif self.selected_index == "Holding":
            self.current_holding_kwargs[attr] = val
        elif self.selected_index == "Baseplate":
            self.current_object["visual"][attr] = val
        elif self.selected_index[0] == "Children":
            self.current_object["children"][self.selected_index[1]]["visual"][attr] = val
        elif self.selected_index[0] == "Devices":
            # Just one key in this dict.
            for key in self.current_devices[self.selected_index[1]]:
                self.current_devices[self.selected_index[1]][key][attr] = val
        else:
            raise ValueError(f"Unknown selection {self.selected_index}")

    def resetBotVisual(self):
        from ev3sim.visual.manager import ScreenObjectManager
        from ev3sim.simulation.loader import ScriptLoader
        from ev3sim.simulation.world import World
        from ev3sim.visual.objects import visualFactory

        ScriptLoader.instance.reset()
        ScriptLoader.instance.startUp()
        ScreenObjectManager.instance.resetVisualElements()
        World.instance.resetWorld()
        mSize = min(*self.surf_size)
        self.customMap = {
            "SCREEN_WIDTH": self.surf_size[0],
            "SCREEN_HEIGHT": self.surf_size[1],
            "MAP_WIDTH": int(self.surf_size[0] / mSize * 24),
            "MAP_HEIGHT": int(self.surf_size[1] / mSize * 24),
        }
        bg_circ = visualFactory(
            name="Circle",
            radius=11,
            position=(0, 0),
            zPos=-1,
            fill="#404040",
            stroke_width=0,
        )
        bg_circ.customMap = self.customMap
        bg_circ.calculatePoints()
        ScreenObjectManager.instance.registerVisual(bg_circ, key="bg_circle")
        if self.current_object:
            copy_obj = self.current_object.copy()
            copy_obj["children"] = self.current_object["children"].copy()
            add_devices(copy_obj, self.current_devices)
            elems = ScriptLoader.instance.loadElements([copy_obj], preview_mode=True)
            self.robot = elems[0]
            self.robot.identifier = "Baseplate"
            for i, child in enumerate(self.robot.children):
                child.identifier = ("Children", i)
            # Just create it so we can use it.
            r = Randomiser(seed=0)
            for i, interactor in enumerate(ScriptLoader.instance.active_scripts):
                interactor.port_key = str(i)
                Randomiser.createPortRandomiserWithSeed(interactor.port_key)
                interactor.startUp()
                interactor.device_class.generateBias()
                interactor.tick(0)
                interactor.afterPhysics()
                for gen in interactor.generated:
                    gen.identifier = ("Devices", i)
            World.instance.registerObject(self.robot)
            while elems:
                new_elems = []
                for elem in elems:
                    elem.visual.customMap = self.customMap
                    elem.visual.calculatePoints()
                    new_elems.extend(elem.children)
                elems = new_elems
            # We need this for the device positions to be correctly set.
            World.instance.tick(1 / 60)

    def updateZpos(self):
        for i in range(len(self.current_devices)):
            for key in self.current_devices[i]:
                self.current_devices[i][key]["zPos"] = self.DEV_ZPOS + 1 - pow(2, -i)
        for i in range(len(self.current_object["children"])):
            self.current_object["children"][i]["visual"]["zPos"] = self.OBJ_ZPOS + 1 - pow(2, -i)
        self.current_object["visual"]["zPos"] = self.BASE_ZPOS

    def placeHolding(self, pos):
        if self.current_holding_kwargs["type"] == "device":
            dev_name = self.current_holding_kwargs["name"]
            rest = self.current_holding_kwargs.copy()
            rest["position"] = [float(self.current_mpos[0]), float(self.current_mpos[1])]
            del rest["type"]
            del rest["name"]
            self.current_devices.append({dev_name: rest})
        else:
            obj = {
                "physics": True,
                "type": "object",
                "visual": self.current_holding_kwargs.copy(),
                "position": pos,
                "restitution": 0.2,
                "friction": 0.8,
            }
            self.current_object["children"].append(obj)
        self.updateZpos()
        self.resetBotVisual()
        self.generateHoldingItem()

    def removeSelected(self):
        if self.selected_index in ["Holding", None, "Baseplate"]:
            raise ValueError("The remove button should not be visible at the moment.")
        if self.selected_index[0] == "Children":
            del self.current_object["children"][self.selected_index[1]]
        elif self.selected_index[0] == "Devices":
            del self.current_devices[self.selected_index[1]]
        self.updateZpos()
        self.selected_index = None
        self.selected_type = self.SELECTED_NOTHING
        self.clearOptions()
        self.resetBotVisual()

    def selectObj(self, pos):
        from ev3sim.simulation.world import World

        shapes = World.instance.space.point_query(
            [float(v) for v in pos], 0.0, pymunk.ShapeFilter(mask=pymunk.ShapeFilter.ALL_MASKS ^ STATIC_CATEGORY)
        )
        if shapes:
            top_shape_z = max(map(lambda x: x.shape.actual_obj.visual.zPos, shapes))
            top_shape = list(filter(lambda x: x.shape.actual_obj.visual.zPos == top_shape_z, shapes))
            assert len(top_shape) == 1
            self.selected_index = top_shape[0].shape.actual_obj.identifier
            name = self.getSelectedAttribute("name", None)
            if name == "Circle":
                self.selected_type = self.SELECTED_CIRCLE
            elif name == "Polygon":
                self.selected_type = self.SELECTED_POLYGON
            else:
                self.selected_type = self.SELECTED_DEVICE
            self.drawOptions()
        else:
            self.selected_index = None

    def sizeObjects(self):
        # Bg
        self.side_width = self._size[0] / 6
        self.bot_height = self._size[1] / 6
        self.sidebar.set_dimensions((self.side_width, self._size[1] + 10))
        self.sidebar.set_position((-5, -5))
        self.bot_bar.set_dimensions((self._size[0] - self.side_width + 20, self.bot_height))
        self.bot_bar.set_position((-10 + self.side_width, self._size[1] - self.bot_height + 5))

        # Clickies
        icon_size = self.side_width / 2
        self.select_icon.set_dimensions((icon_size, icon_size))
        self.select_icon.set_position((self.side_width / 2 - icon_size / 2, 50))
        self.select_button.set_dimensions((icon_size, icon_size))
        self.select_button.set_position((self.side_width / 2 - icon_size / 2, 50))
        self.circle_icon.set_dimensions((icon_size, icon_size))
        self.circle_icon.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 1.5))
        self.circle_button.set_dimensions((icon_size, icon_size))
        self.circle_button.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 1.5))
        self.polygon_icon.set_dimensions((icon_size, icon_size))
        self.polygon_icon.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 3))
        self.polygon_button.set_dimensions((icon_size, icon_size))
        self.polygon_button.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 3))
        self.device_icon.set_dimensions((icon_size, icon_size))
        self.device_icon.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 4.5))
        self.device_button.set_dimensions((icon_size, icon_size))
        self.device_button.set_position((self.side_width / 2 - icon_size / 2, 50 + icon_size * 4.5))

        # Other options
        lock_size = self.side_width / 4
        self.lock_grid_label.set_dimensions(((self.side_width - 30) - lock_size - 5, lock_size))
        self.lock_grid_label.set_position((10, self._size[1] - lock_size - 60))
        self.lock_grid_image.set_dimensions((lock_size, lock_size))
        self.lock_grid_image.set_position((self.side_width - lock_size - 20, self._size[1] - lock_size - 60))
        self.lock_grid_button.set_dimensions((lock_size, lock_size))
        self.lock_grid_button.set_position((self.side_width - lock_size - 20, self._size[1] - lock_size - 60))
        self.updateCheckbox()
        self.grid_size_label.set_dimensions(((self.side_width - 30) - lock_size - 5, lock_size))
        self.grid_size_label.set_position((10, self._size[1] - lock_size - 15))
        self.grid_size_entry.set_dimensions((lock_size, lock_size))
        self.grid_size_entry.set_position((self.side_width - lock_size - 20, self._size[1] - lock_size - 15))

        self.save_button.set_dimensions((self.side_width * 0.8, self.bot_height * 0.35))
        self.save_button.set_position((self._size[0] - self.side_width * 0.9, self._size[1] - self.bot_height * 0.9))
        self.cancel_button.set_dimensions((self.side_width * 0.8, self.bot_height * 0.4))
        self.cancel_button.set_position((self._size[0] - self.side_width * 0.9, self._size[1] - self.bot_height * 0.45))

        # Simulator objects
        self.surf_size = (self._size[0] - self.side_width + 5, self._size[1] - self.bot_height + 5)
        self.bot_screen = pygame.Surface(self.surf_size)

    def generateObjects(self):
        dummy_rect = pygame.Rect(0, 0, *self._size)

        # Bg
        self.sidebar = pygame_gui.elements.UIPanel(
            relative_rect=dummy_rect,
            starting_layer_height=-0.5,
            manager=self,
            object_id=pygame_gui.core.ObjectID("sidebar-bot-edit", "bot_edit_bar"),
        )
        self._all_objs.append(self.sidebar)
        self.bot_bar = pygame_gui.elements.UIPanel(
            relative_rect=dummy_rect,
            starting_layer_height=-0.5,
            manager=self,
            object_id=pygame_gui.core.ObjectID("botbar-bot-edit", "bot_edit_bar"),
        )
        self._all_objs.append(self.bot_bar)

        # Clickies
        self.select_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("select-button", "invis_button"),
        )
        select_icon_path = find_abs("ui/icon_select.png", allowed_areas=asset_locations())
        self.select_icon = pygame_gui.elements.UIImage(
            relative_rect=dummy_rect,
            image_surface=pygame.image.load(select_icon_path),
            manager=self,
            object_id=pygame_gui.core.ObjectID("select-icon"),
        )
        self._all_objs.append(self.select_button)
        self._all_objs.append(self.select_icon)
        self.circle_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("circle-button", "invis_button"),
        )
        circ_icon_path = find_abs("ui/icon_circle.png", allowed_areas=asset_locations())
        self.circle_icon = pygame_gui.elements.UIImage(
            relative_rect=dummy_rect,
            image_surface=pygame.image.load(circ_icon_path),
            manager=self,
            object_id=pygame_gui.core.ObjectID("circle-icon"),
        )
        self._all_objs.append(self.circle_button)
        self._all_objs.append(self.circle_icon)
        self.polygon_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("polygon-button", "invis_button"),
        )
        polygon_icon_path = find_abs("ui/icon_polygon.png", allowed_areas=asset_locations())
        self.polygon_icon = pygame_gui.elements.UIImage(
            relative_rect=dummy_rect,
            image_surface=pygame.image.load(polygon_icon_path),
            manager=self,
            object_id=pygame_gui.core.ObjectID("polygon-icon"),
        )
        self._all_objs.append(self.polygon_button)
        self._all_objs.append(self.polygon_icon)
        self.device_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("device-button", "invis_button"),
        )
        device_icon_path = find_abs("ui/icon_device.png", allowed_areas=asset_locations())
        self.device_icon = pygame_gui.elements.UIImage(
            relative_rect=dummy_rect,
            image_surface=pygame.image.load(device_icon_path),
            manager=self,
            object_id=pygame_gui.core.ObjectID("device-icon"),
        )
        self._all_objs.append(self.device_button)
        self._all_objs.append(self.device_icon)

        # Other options
        self.lock_grid_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Lock Grid",
            manager=self,
            object_id=pygame_gui.core.ObjectID("lock_grid-label", "bot_edit_label"),
        )
        self.lock_grid_image = pygame_gui.elements.UIImage(
            relative_rect=dummy_rect,
            manager=self,
            image_surface=pygame.Surface((dummy_rect.width, dummy_rect.height)),
            object_id=pygame_gui.core.ObjectID("lock_grid-image"),
        )
        self.lock_grid_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID(f"lock_grid-button", "checkbox-button"),
            text="",
        )
        self._all_objs.append(self.lock_grid_label)
        self._all_objs.append(self.lock_grid_image)
        self._all_objs.append(self.lock_grid_button)
        self.grid_size_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Grid Size",
            manager=self,
            object_id=pygame_gui.core.ObjectID("grid_size-label", "bot_edit_label"),
        )
        self.grid_size_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("grid_size-entry", "num_entry"),
        )
        self.grid_size_entry.set_text(str(self.grid_size))
        self._all_objs.append(self.grid_size_label)
        self._all_objs.append(self.grid_size_entry)

        # Save/Cancel
        self.save_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="Create" if self.creating else "Save",
            manager=self,
            object_id=pygame_gui.core.ObjectID("save-changes", "action_button"),
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            relative_rect=dummy_rect,
            text="Cancel",
            manager=self,
            object_id=pygame_gui.core.ObjectID("cancel-changes", "action_button"),
        )
        self._all_objs.append(self.save_button)
        self._all_objs.append(self.cancel_button)

    def generateHoldingItem(self):
        from ev3sim.visual.objects import visualFactory

        if "holding" in ScreenObjectManager.instance.objects:
            ScreenObjectManager.instance.unregisterVisual("holding")

        if self.current_holding_kwargs["type"] == "device":
            from ev3sim.simulation.loader import ScriptLoader

            if "holding_bot" in ScriptLoader.instance.object_map:
                ScreenObjectManager.instance.unregisterVisual("holding_bot")
                for child in ScriptLoader.instance.object_map["holding_bot"].children:
                    ScreenObjectManager.instance.unregisterVisual(child.key)
                del ScriptLoader.instance.object_map["holding_bot"]
                to_remove = []
                for i, interactor in enumerate(ScriptLoader.instance.active_scripts):
                    if interactor.physical_object.key == "holding_bot":
                        to_remove.append(i)
                for index in to_remove[::-1]:
                    del ScriptLoader.instance.active_scripts[index]
            ScriptLoader.instance.loadElements(
                [
                    {
                        "type": "object",
                        "physics": True,
                        "visual": {
                            "name": "Circle",
                            "stroke": None,
                            "fill": None,
                            "stroke_width": 0,
                            "radius": 0,
                            "zPos": 20,
                        },
                        "children": [self.current_holding_kwargs],
                        "key": "holding_bot",
                    }
                ],
                preview_mode=True,
            )
            for interactor in ScriptLoader.instance.active_scripts:
                if interactor.physical_object.key == "holding_bot":
                    interactor.port_key = "holding"
                    if "holding" not in Randomiser.instance.port_randomisers:
                        Randomiser.createPortRandomiserWithSeed(interactor.port_key)
                    interactor.startUp()
                    interactor.device_class.generateBias()
                    interactor.tick(0)
                    interactor.afterPhysics()
                    self.current_holding = interactor.generated
                    for i, obj in enumerate(self.current_holding):
                        obj.visual.customMap = self.customMap
                        obj.visual.offset_position = interactor.relative_positions[i]
                        obj.visual.position = [
                            self.current_mpos[0] + obj.visual.offset_position[0],
                            self.current_mpos[1] + obj.visual.offset_position[1],
                        ]
                    break
        else:
            self.current_holding = visualFactory(**self.current_holding_kwargs)
            self.current_holding.customMap = self.customMap
            self.current_holding.position = self.current_mpos
            ScreenObjectManager.instance.registerVisual(self.current_holding, "holding")

    def clickSelect(self):
        from ev3sim.simulation.loader import ScriptLoader

        if "holding" in ScreenObjectManager.instance.objects:
            ScreenObjectManager.instance.unregisterVisual("holding")
        if "holding_bot" in ScreenObjectManager.instance.objects:
            ScreenObjectManager.instance.unregisterVisual("holding_bot")
            for child in ScriptLoader.instance.object_map["holding_bot"].children:
                ScreenObjectManager.instance.unregisterVisual(child.key)
            del ScriptLoader.instance.object_map["holding_bot"]
            to_remove = []
            for i, interactor in enumerate(ScriptLoader.instance.active_scripts):
                if interactor.physical_object.key == "holding_bot":
                    to_remove.append(i)
            for index in to_remove[::-1]:
                del ScriptLoader.instance.active_scripts[index]
        self.current_holding = None
        self.selected_type = self.SELECTED_NOTHING
        self.selected_index = None
        self.clearOptions()

    def clickCircle(self):
        self.current_holding_kwargs = {
            "type": "visual",
            "name": "Circle",
            "radius": 1,
            "fill": "#878E88",
            "stroke_width": 0.1,
            "stroke": "#ffffff",
            "zPos": self.HOLD_ZPOS,
        }
        self.selected_index = "Holding"
        self.selected_type = self.SELECTED_CIRCLE
        self.drawOptions()
        self.generateHoldingItem()

    def clickPolygon(self):
        self.current_holding_kwargs = {
            "type": "visual",
            "name": "Polygon",
            "fill": "#878E88",
            "stroke_width": 0.1,
            "stroke": "#ffffff",
            "verts": [
                [np.sin(0), np.cos(0)],
                [np.sin(2 * np.pi / 5), np.cos(2 * np.pi / 5)],
                [np.sin(4 * np.pi / 5), np.cos(4 * np.pi / 5)],
                [np.sin(6 * np.pi / 5), np.cos(6 * np.pi / 5)],
                [np.sin(8 * np.pi / 5), np.cos(8 * np.pi / 5)],
            ],
            "zPos": self.HOLD_ZPOS,
        }
        self.selected_index = "Holding"
        self.selected_type = self.SELECTED_POLYGON
        self.drawOptions()
        self.generateHoldingItem()

    def clickDevice(self):
        self.addDevicePicker()

    def updateCheckbox(self):
        img = pygame.image.load(
            find_abs("ui/box_check.png" if self.lock_grid else "ui/box_clear.png", allowed_areas=asset_locations())
        )
        if img.get_size() != self.lock_grid_image.rect.size:
            img = pygame.transform.smoothscale(img, (self.lock_grid_image.rect.width, self.lock_grid_image.rect.height))
        self.lock_grid_image.set_image(img)

    def saveBot(self):
        self.previous_info["base_plate"] = self.current_object
        del self.previous_info["base_plate"]["type"]
        del self.previous_info["base_plate"]["physics"]
        verts = [[float(v2) for v2 in v1] for v1 in self.previous_info["base_plate"].get("visual", {}).get("verts", [])]
        if verts:
            self.previous_info["base_plate"]["visual"]["verts"] = verts
        for child in self.previous_info["base_plate"]["children"]:
            child["position"] = [float(v) for v in child["position"]]
            verts = [[float(v2) for v2 in v1] for v1 in child.get("verts", [])]
            if verts:
                child["verts"] = verts
            verts = [[float(v2) for v2 in v1] for v1 in child.get("visual", {}).get("verts", [])]
            if verts:
                child["visual"]["verts"] = verts

        self.previous_info["devices"] = self.current_devices
        with open(self.bot_file, "w") as f:
            f.write(yaml.dump(self.previous_info))
        ScreenObjectManager.instance.captureBotImage(*self.bot_dir_file)
        if self.onSave is not None:
            self.onSave(self.bot_dir_file[1])

    def handleEvent(self, event):
        if self.mode == self.MODE_NORMAL:
            if event.type == pygame.USEREVENT and event.user_type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_object_id.startswith("select-button"):
                    self.clickSelect()
                elif event.ui_object_id.startswith("circle-button"):
                    self.clickCircle()
                elif event.ui_object_id.startswith("polygon-button"):
                    self.clickPolygon()
                elif event.ui_object_id.startswith("device-button"):
                    self.clickDevice()
                elif event.ui_object_id.startswith("lock_grid-button"):
                    self.lock_grid = not self.lock_grid
                    self.updateCheckbox()
                # Colour
                elif event.ui_object_id.startswith("stroke_colour-button"):
                    self.colour_field = "stroke"
                    start_colour = self.getSelectedAttribute("stroke", "")
                    self.addColourPicker("Pick Stroke", start_colour)
                elif event.ui_object_id.startswith("fill_colour-button"):
                    self.colour_field = "fill"
                    start_colour = self.getSelectedAttribute("fill", "")
                    self.addColourPicker("Pick Fill", start_colour)
                # Removing
                elif event.ui_object_id.startswith("remove_button"):
                    self.removeSelected()
                # Saving
                elif event.ui_object_id.startswith("save-changes"):
                    from ev3sim.robot import visual_settings

                    if self.creating:
                        ScreenObjectManager.instance.pushScreen(
                            ScreenObjectManager.SCREEN_SETTINGS,
                            settings=visual_settings,
                            creating=True,
                            creation_area="workspace/robots/",
                            starting_data={},
                            extension="bot",
                        )

                        def onSave(filename):
                            self.bot_file = find_abs(filename, ["workspace/robots/"])
                            self.bot_dir_file = ["workspace/robots/", filename]
                            self.saveBot()
                            ScreenObjectManager.instance.popScreen()

                        ScreenObjectManager.instance.screens[ScreenObjectManager.SCREEN_SETTINGS].clearEvents()
                        ScreenObjectManager.instance.screens[ScreenObjectManager.SCREEN_SETTINGS].onSave = onSave
                    else:
                        self.saveBot()
                        ScreenObjectManager.instance.popScreen()
                elif event.ui_object_id.startswith("cancel-changes"):
                    ScreenObjectManager.instance.popScreen()
            elif event.type == pygame.MOUSEMOTION:
                self.actual_mpos = event.pos
                self.current_mpos = screenspace_to_worldspace(
                    (event.pos[0] - self.side_width, event.pos[1]), customScreen=self.customMap
                )
                if self.lock_grid and not self.dragging:
                    self.current_mpos = [
                        ((self.current_mpos[0] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                        ((self.current_mpos[1] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                    ]
                if self.current_holding is not None:
                    if self.current_holding_kwargs["type"] == "device":
                        for obj in self.current_holding:
                            obj.visual.position = [
                                self.current_mpos[0] + obj.visual.offset_position[0],
                                self.current_mpos[1] + obj.visual.offset_position[1],
                            ]
                    else:
                        self.current_holding.position = self.current_mpos
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mpos = screenspace_to_worldspace(
                    (event.pos[0] - self.side_width, event.pos[1]), customScreen=self.customMap
                )
                if (
                    -self.customMap["MAP_WIDTH"] / 2 <= mpos[0] <= self.customMap["MAP_WIDTH"] / 2
                    and -self.customMap["MAP_HEIGHT"] / 2 <= mpos[1] <= self.customMap["MAP_HEIGHT"] / 2
                ):
                    if self.current_holding is None:
                        self.selectObj(mpos)
                        if self.selected_index is not None:
                            self.dragging = True
                            pos = self.getSelectedAttribute("position", [0, 0])
                            if isinstance(self.selected_index, (tuple, list)) and self.selected_index[0] == "Children":
                                pos = self.current_object["children"][self.selected_index[1]]["position"]
                            self.offset_position = [pos[0] - mpos[0], pos[1] - mpos[1]]
                    else:
                        if self.lock_grid:
                            mpos = [
                                ((mpos[0] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                                ((mpos[1] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                            ]
                        self.placeHolding(mpos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = False
            elif event.type == pygame.MOUSEWHEEL:
                for attr, conv, inc in [
                    ("rotation_entry", float, 1),
                    ("radius_entry", float, 0.1),
                    ("size_entry", float, 0.1),
                    ("stroke_entry", float, 0.05),
                    ("sides_entry", int, 1),
                ]:
                    if hasattr(self, attr):
                        rect = getattr(self, attr).get_relative_rect()
                        if (
                            rect.left <= self.actual_mpos[0] <= rect.right
                            and rect.top <= self.actual_mpos[1] <= rect.bottom
                        ):
                            try:
                                val = conv(getattr(self, attr).text)
                                val += event.y * inc
                                getattr(self, attr).set_text(str(val))
                            except:
                                pass
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE:
                    if self.selected_type not in [None, "Holding", "Baseplate"]:
                        self.removeSelected()

    def drawOptions(self):
        self.clearOptions()
        name = self.getSelectedAttribute("name", None)
        if name == "Circle":
            self.drawCircleOptions()
        elif name == "Polygon":
            self.drawPolygonOptions()
        else:
            self.drawDeviceOptions()
        if self.selected_index not in ["Holding", "Baseplate", None]:
            self.drawRemove()

    def drawRemove(self):
        icon_size = self.side_width / 2
        self.remove_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(
                self.side_width * 0.2, 50 + icon_size * 5.8, self.side_width * 0.6, self.side_width * 0.4
            ),
            text="Remove",
            manager=self,
            object_id=pygame_gui.core.ObjectID("remove_button", "cancel-changes"),
        )

    def drawCircleOptions(self):
        dummy_rect = pygame.Rect(0, 0, *self._size)

        # Radius
        self.radius_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Radius",
            manager=self,
            object_id=pygame_gui.core.ObjectID("radius-label", "bot_edit_label"),
        )
        self.radius_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("radius-entry", "num_entry"),
        )
        self.radius_entry.set_text(str(self.getSelectedAttribute("radius")))
        entry_size = self.side_width / 3
        self.radius_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.radius_label.set_position((self.side_width + 20, self._size[1] - self.bot_height + 15))
        self.radius_entry.set_dimensions((entry_size, entry_size))
        self.radius_entry.set_position((2 * self.side_width - 10, self._size[1] - self.bot_height + 20))

        # Stroke width
        self.stroke_num_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Stroke",
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke-label", "bot_edit_label"),
        )
        self.stroke_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke-entry", "num_entry"),
        )
        self.stroke_entry.set_text(str(self.getSelectedAttribute("stroke_width")))
        self.stroke_num_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.stroke_num_label.set_position((self.side_width + 20, self._size[1] - entry_size))
        self.stroke_entry.set_dimensions((entry_size, entry_size))
        self.stroke_entry.set_position((2 * self.side_width - 10, self._size[1] - entry_size + 5))

        self.generateColourPickers()
        button_size = entry_size * 0.9
        self.fill_label.set_dimensions((self.side_width - entry_size + 5, entry_size))
        self.fill_label.set_position((2 * self.side_width + 60, self._size[1] - entry_size))
        self.fill_img.set_dimensions((button_size, button_size))
        self.fill_img.set_position(
            (3 * self.side_width + 30, self._size[1] - button_size - (entry_size - button_size) / 2)
        )
        self.stroke_label.set_dimensions((self.side_width - entry_size + 5, entry_size))
        self.stroke_label.set_position((2 * self.side_width + 60, self._size[1] - self.bot_height + 15))
        self.stroke_img.set_dimensions((button_size, button_size))
        self.stroke_img.set_position(
            (3 * self.side_width + 30, self._size[1] - self.bot_height + 15 + (entry_size - button_size) / 2)
        )

    def drawPolygonOptions(self):
        dummy_rect = pygame.Rect(0, 0, *self._size)

        # Sides
        self.sides_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Sides",
            manager=self,
            object_id=pygame_gui.core.ObjectID("sides-label", "bot_edit_label"),
        )
        self.sides_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("sides-entry", "num_entry"),
        )
        self.sides_entry.set_text(str(len(self.getSelectedAttribute("verts"))))
        entry_size = self.side_width / 3
        self.sides_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.sides_label.set_position((self.side_width + 20, self._size[1] - self.bot_height + 15))
        self.sides_entry.set_dimensions((entry_size, entry_size))
        self.sides_entry.set_position((2 * self.side_width - 10, self._size[1] - self.bot_height + 20))

        # Size
        self.size_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Size",
            manager=self,
            object_id=pygame_gui.core.ObjectID("size-label", "bot_edit_label"),
        )
        self.size_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("size-entry", "num_entry"),
        )

        self.size_entry.set_text(str(np.linalg.norm(self.getSelectedAttribute("verts")[0], 2)))
        self.size_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.size_label.set_position((self.side_width + 20, self._size[1] - entry_size))
        self.size_entry.set_dimensions((entry_size, entry_size))
        self.size_entry.set_position((2 * self.side_width - 10, self._size[1] - entry_size + 5))

        self.generateColourPickers()
        button_size = entry_size * 0.9
        self.fill_label.set_dimensions((self.side_width - entry_size + 5, entry_size))
        self.fill_label.set_position((2 * self.side_width + 60, self._size[1] - entry_size))
        self.fill_img.set_dimensions((button_size, button_size))
        self.fill_img.set_position(
            (3 * self.side_width + 30, self._size[1] - button_size - (entry_size - button_size) / 2)
        )
        self.stroke_label.set_dimensions((self.side_width - entry_size + 5, entry_size))
        self.stroke_label.set_position((2 * self.side_width + 60, self._size[1] - self.bot_height + 15))
        self.stroke_img.set_dimensions((button_size, button_size))
        self.stroke_img.set_position(
            (3 * self.side_width + 30, self._size[1] - self.bot_height + 15 + (entry_size - button_size) / 2)
        )

        # Rotation
        self.rotation_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Rotation",
            manager=self,
            object_id=pygame_gui.core.ObjectID("rotation-label", "bot_edit_label"),
        )
        self.rotation_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("rotation-entry", "num_entry"),
        )
        # Takeaway pi/2, so that pointing up is rotation 0.
        cur_rotation = (
            np.arctan2(self.getSelectedAttribute("verts")[0][1], self.getSelectedAttribute("verts")[0][0]) - np.pi / 2
        )
        while cur_rotation < 0:
            cur_rotation += np.pi
        self.rotation_entry.set_text(str(180 / np.pi * cur_rotation))
        self.rotation_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.rotation_label.set_position((3 * self.side_width + 100, self._size[1] - self.bot_height + 15))
        self.rotation_entry.set_dimensions((entry_size, entry_size))
        self.rotation_entry.set_position((4 * self.side_width + 70, self._size[1] - self.bot_height + 20))
        # Stroke width
        self.stroke_num_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Stroke",
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke-label", "bot_edit_label"),
        )
        self.stroke_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke-entry", "num_entry"),
        )
        self.stroke_entry.set_text(str(self.getSelectedAttribute("stroke_width")))
        self.stroke_num_label.set_dimensions(((self.side_width - 30) - entry_size - 5, entry_size))
        self.stroke_num_label.set_position((3 * self.side_width + 100, self._size[1] - entry_size))
        self.stroke_entry.set_dimensions((entry_size, entry_size))
        self.stroke_entry.set_position((4 * self.side_width + 70, self._size[1] - entry_size + 5))

    def drawDeviceOptions(self):
        dummy_rect = pygame.Rect(0, 0, *self._size)
        entry_size = self.side_width / 2
        entry_height = self.bot_height * 0.3

        # Rotation
        self.rotation_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Rotation",
            manager=self,
            object_id=pygame_gui.core.ObjectID("rotation-label", "bot_edit_label"),
        )
        self.rotation_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("rotation-entry", "num_entry"),
        )
        # Takeaway pi/2, so that pointing up is rotation 0.
        cur_rotation = self.getSelectedAttribute("rotation", 0)
        self.rotation_entry.set_text(str(cur_rotation))
        self.rotation_label.set_dimensions(((self.side_width * 1.5 - 30) - entry_size - 5, entry_height))
        self.rotation_label.set_position((self.side_width + 20, self._size[1] - self.bot_height + 20))
        self.rotation_entry.set_dimensions((entry_size, entry_height))
        self.rotation_entry.set_position((2 * self.side_width - 10, self._size[1] - self.bot_height + 20))

        # Port
        self.port_label = pygame_gui.elements.UILabel(
            relative_rect=dummy_rect,
            text="Port",
            manager=self,
            object_id=pygame_gui.core.ObjectID("port-label", "bot_edit_label"),
        )
        self.port_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=dummy_rect,
            manager=self,
            object_id=pygame_gui.core.ObjectID("port-entry", "num_entry"),
        )
        self.port_entry.set_text(self.getSelectedAttribute("port"))
        self.port_label.set_dimensions(((self.side_width * 1.5 - 30) - entry_size - 5, entry_height))
        self.port_label.set_position((self.side_width + 20, self._size[1] - entry_height - 10))
        self.port_entry.set_dimensions((entry_size, entry_height))
        self.port_entry.set_position((2 * self.side_width - 10, self._size[1] - entry_height - 10))

    def generateColourPickers(self):
        # Colour pickers
        self.stroke_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(0, 0, *self._size),
            text="Stroke Colour",
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke_colour-label", "bot_edit_label"),
        )
        self.stroke_img = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(0, 0, *self._size),
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("stroke_colour-button"),
        )
        self.fill_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(0, 0, *self._size),
            text="Fill Colour",
            manager=self,
            object_id=pygame_gui.core.ObjectID("fill_colour-label", "bot_edit_label"),
        )
        self.fill_img = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(0, 0, *self._size),
            text="",
            manager=self,
            object_id=pygame_gui.core.ObjectID("fill_colour-button"),
        )
        data = {
            "fill_colour-button": {
                "colours": {
                    "normal_bg": self.getSelectedAttribute("fill"),
                    "hovered_bg": self.getSelectedAttribute("fill"),
                    "active_bg": self.getSelectedAttribute("fill"),
                }
            },
            "stroke_colour-button": {
                "colours": {
                    "normal_bg": self.getSelectedAttribute("stroke"),
                    "hovered_bg": self.getSelectedAttribute("stroke"),
                    "active_bg": self.getSelectedAttribute("stroke"),
                }
            },
        }
        self.ui_theme._load_element_colour_data_from_theme("colours", "fill_colour-button", data)
        self.fill_img.rebuild_from_changed_theme_data()
        self.ui_theme._load_element_colour_data_from_theme("colours", "stroke_colour-button", data)
        self.stroke_img.rebuild_from_changed_theme_data()

    def addColourPicker(self, title, start_colour):
        from ev3sim.visual.utils import rgb_to_hex

        self.mode = self.MODE_COLOUR_DIALOG

        class ColourPicker(pygame_gui.windows.UIColourPickerDialog):
            def process_event(self2, event: pygame.event.Event) -> bool:
                consumed_event = pygame_gui.elements.UIWindow.process_event(self2, event)
                if (
                    event.type == pygame.USEREVENT
                    and event.user_type == pygame_gui.UI_BUTTON_PRESSED
                    and event.ui_element == self2.cancel_button
                ):
                    self2.kill()
                    return consumed_event

                if (
                    event.type == pygame.USEREVENT
                    and event.user_type == pygame_gui.UI_BUTTON_PRESSED
                    and event.ui_element == self2.ok_button
                ):
                    new_col = rgb_to_hex(
                        self2.red_channel.current_value,
                        self2.green_channel.current_value,
                        self2.blue_channel.current_value,
                    )
                    self.setSelectedAttribute(self.colour_field, new_col)
                    self.resetBotVisual()
                    if self.selected_index == "Holding":
                        self.generateHoldingItem()
                    self2.kill()
                    return consumed_event

                return super().process_event(event)

            def kill(self2):
                super().kill()
                self.removeColourPicker()

        self.picker = ColourPicker(
            rect=pygame.Rect(self._size[0] * 0.15, self._size[1] * 0.15, self._size[0] * 0.7, self._size[1] * 0.7),
            manager=self,
            initial_colour=pygame.Color(start_colour),
            window_title=title,
            object_id=pygame_gui.core.ObjectID("colour_dialog"),
        )

    def addDevicePicker(self):

        self.mode = self.MODE_DEVICE_DIALOG

        device_data = [
            ("Ultrasonic", "ultrasonic", "ultrasonic", "UltrasonicSensor"),
            ("Colour", "colour", "colour", "ColorSensor"),
            ("Infrared", "infrared", "infrared", "InfraredSensor"),
            ("Compass", "compass", "compass", "CompassSensor"),
            ("Large Motor", "large_motor", "motor", "LargeMotor"),
            ("Medium Motor", "medium_motor", "motor", "MediumMotor"),
            ("Button", "button", "button", "Button"),
        ]

        class DevicePicker(pygame_gui.elements.UIWindow):
            def kill(self2):
                super().kill()
                self.removeDevicePicker()

            def process_event(self2, event: pygame.event.Event):
                if event.type == pygame.USEREVENT and event.user_type == pygame_gui.UI_BUTTON_PRESSED:
                    for device in device_data:
                        if f"{device[1]}_button" in event.ui_object_id:
                            # Select that device.
                            self.current_holding_kwargs = {
                                "type": "device",
                                "name": device[3],
                                "port": "in1" if device[2] != "motor" else "outA",
                                "rotation": 0,
                            }
                            self.selected_type = self.SELECTED_DEVICE
                            self.selected_index = "Holding"
                            self.generateHoldingItem()
                            self2.kill()
                return super().process_event(event)

        picker_size = (self._size[0] * 0.7, self._size[1] * 0.7)

        self.picker = DevicePicker(
            rect=pygame.Rect(self._size[0] * 0.15, self._size[1] * 0.15, *picker_size),
            manager=self,
            window_display_title="Pick Device",
            object_id=pygame_gui.core.ObjectID("device_dialog"),
        )

        for i, (show, device, file, sensor_name) in enumerate(device_data):
            setattr(
                self,
                f"{device}_label",
                pygame_gui.elements.UILabel(
                    relative_rect=pygame.Rect(
                        30 + ((i % 3) + (i // 6)) * ((picker_size[0] - 150) / 3 + 30),
                        20 + ((picker_size[1] - 160) / 3 + 20) * (i // 3),
                        (picker_size[0] - 150) / 3,
                        25,
                    ),
                    text=show,
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{device}_label", "device_label"),
                ),
            )
            img = pygame.image.load(find_abs(f"ui/devices/{file}.png", asset_locations()))
            img.set_colorkey((0, 255, 0))
            but_rect = pygame.Rect(
                30 + ((i % 3) + (i // 6)) * ((picker_size[0] - 150) / 3 + 30),
                50 + ((picker_size[1] - 160) / 3 + 20) * (i // 3),
                (picker_size[0] - 150) / 3,
                (picker_size[1] - 160) / 3 - 30,
            )
            setattr(
                self,
                f"{device}_img",
                pygame_gui.elements.UIImage(
                    relative_rect=but_rect,
                    image_surface=img,
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{device}_img", "device_img"),
                ),
            )
            setattr(
                self,
                f"{device}_button",
                pygame_gui.elements.UIButton(
                    relative_rect=but_rect,
                    text="",
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{device}_button", "invis_button"),
                ),
            )

    def addBaseplatePicker(self):
        self.mode = self.MODE_BASEPLATE_DIALOG

        baseplate_options = [
            (
                "Circle",
                {
                    "name": "Circle",
                    "radius": 1,
                    "fill": "#878E88",
                    "stroke_width": 0.1,
                    "stroke": "#ffffff",
                    "zPos": self.BASE_ZPOS,
                },
                "circle",
                self.SELECTED_CIRCLE,
            ),
            (
                "Polygon",
                {
                    "name": "Polygon",
                    "fill": "#878E88",
                    "stroke_width": 0.1,
                    "stroke": "#ffffff",
                    "verts": [
                        [np.sin(0), np.cos(0)],
                        [np.sin(2 * np.pi / 5), np.cos(2 * np.pi / 5)],
                        [np.sin(4 * np.pi / 5), np.cos(4 * np.pi / 5)],
                        [np.sin(6 * np.pi / 5), np.cos(6 * np.pi / 5)],
                        [np.sin(8 * np.pi / 5), np.cos(8 * np.pi / 5)],
                    ],
                    "zPos": self.BASE_ZPOS,
                },
                "polygon",
                self.SELECTED_POLYGON,
            ),
        ]

        class BaseplatePicker(pygame_gui.elements.UIWindow):
            def kill(self2):
                if self.selected_index != "Baseplate":
                    # We cannot close this until a baseplate has been selected.
                    return
                super().kill()
                self.removeBaseplatePicker()

            def process_event(self2, event: pygame.event.Event):
                if event.type == pygame.USEREVENT and event.user_type == pygame_gui.UI_BUTTON_PRESSED:
                    for show, obj, name, select in baseplate_options:
                        if f"{name}_button" in event.ui_object_id:
                            # Select that baseplate
                            self.selected_type = select
                            self.selected_index = "Baseplate"
                            self.current_object = {
                                "type": "object",
                                "physics": True,
                                "visual": obj,
                                "mass": 5,
                                "restitution": 0.2,
                                "friction": 0.8,
                                "children": [],
                                "key": "phys_obj",
                            }
                            self.updateZpos()
                            self2.kill()
                return super().process_event(event)

        picker_size = (self._size[0] * 0.7, self._size[1] * 0.7)

        self.picker = BaseplatePicker(
            rect=pygame.Rect(self._size[0] * 0.15, self._size[1] * 0.15, *picker_size),
            manager=self,
            window_display_title="Pick Device",
            object_id=pygame_gui.core.ObjectID("device_dialog"),
        )

        self.text = pygame_gui.elements.UITextBox(
            html_text="""\
All bots require a <font color="#06d6a0">baseplate</font>.<br><br>\
All other objects are placed on this baseplate. After creating it, the baseplate type <font color="#e63946">cannot</font> be changed. (Although it's characteristics can).\
""",
            relative_rect=pygame.Rect(30, 10, picker_size[0] - 60, 140),
            manager=self,
            container=self.picker,
            object_id=pygame_gui.core.ObjectID("text_dialog_baseplate", "text_dialog"),
        )

        for i, (show, obj, name, select) in enumerate(baseplate_options):
            setattr(
                self,
                f"{name}_label",
                pygame_gui.elements.UILabel(
                    relative_rect=pygame.Rect(
                        30 + (i % 2) * ((picker_size[0] - 120) / 2 + 30),
                        150 + (picker_size[1] - 250 + 20) * (i // 2),
                        (picker_size[0] - 120) / 2,
                        25,
                    ),
                    text=show,
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{name}_label", "baseplate_label"),
                ),
            )
            img = pygame.image.load(find_abs(f"ui/icon_{name}.png", allowed_areas=asset_locations()))
            img.set_colorkey((0, 255, 0))
            but_rect = pygame.Rect(
                30 + (i % 2) * ((picker_size[0] - 120) / 2 + 30),
                180 + (picker_size[1] - 250 + 20) * (i // 2),
                (picker_size[0] - 120) / 2,
                picker_size[1] - 250 - 30,
            )
            setattr(
                self,
                f"{name}_img",
                pygame_gui.elements.UIImage(
                    relative_rect=but_rect,
                    image_surface=img,
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{name}_img", "baseplate_img"),
                ),
            )
            setattr(
                self,
                f"{name}_button",
                pygame_gui.elements.UIButton(
                    relative_rect=but_rect,
                    text="",
                    manager=self,
                    container=self.picker,
                    object_id=pygame_gui.core.ObjectID(f"{name}_button", "invis_button"),
                ),
            )

    def removeBaseplatePicker(self):
        try:
            self.mode = self.MODE_NORMAL
            self.drawOptions()
            self.resetBotVisual()
        except:
            pass

    def removeDevicePicker(self):
        try:
            self.mode = self.MODE_NORMAL
            self.drawOptions()
        except:
            pass

    def removeColourPicker(self):
        try:
            self.mode = self.MODE_NORMAL
            self.drawOptions()
        except:
            pass

    def removeColourOptions(self):
        try:
            self.fill_label.kill()
            self.fill_img.kill()
            self.stroke_label.kill()
            self.stroke_img.kill()
        except:
            pass

    def removeCircleOptions(self):
        try:
            self.radius_label.kill()
            self.radius_entry.kill()
            self.stroke_num_label.kill()
            self.stroke_entry.kill()
        except:
            pass

    def removePolygonOptions(self):
        try:
            self.sides_label.kill()
            self.sides_entry.kill()
            self.size_label.kill()
            self.size_entry.kill()
            self.stroke_num_label.kill()
            self.stroke_entry.kill()
            self.rotation_label.kill()
            self.rotation_entry.kill()
        except:
            pass

    def removeDeviceOptions(self):
        try:
            self.rotation_label.kill()
            self.rotation_entry.kill()
            self.port_label.kill()
            self.port_entry.kill()
        except:
            pass

    def clearOptions(self):
        try:
            self.remove_button.kill()
        except:
            pass
        self.removeColourOptions()
        self.removeCircleOptions()
        self.removePolygonOptions()
        self.removeDeviceOptions()

    def clearObjects(self):
        super().clearObjects()
        self.clearOptions()

    def draw_ui(self, window_surface: pygame.surface.Surface):
        if self.selected_index is not None:
            if self.selected_index == "Holding":
                generate = lambda: self.generateHoldingItem()
            else:
                generate = lambda: self.resetBotVisual()
            if self.mode == self.MODE_NORMAL and self.selected_type == self.SELECTED_CIRCLE:
                old_radius = self.getSelectedAttribute("radius")
                try:
                    new_radius = float(self.radius_entry.text)
                    if old_radius != new_radius:
                        self.setSelectedAttribute("radius", new_radius)
                        generate()
                except:
                    self.setSelectedAttribute("radius", old_radius)

                old_stroke_width = self.getSelectedAttribute("stroke_width")
                try:
                    new_stroke_width = float(self.stroke_entry.text)
                    if old_stroke_width != new_stroke_width:
                        self.setSelectedAttribute("stroke_width", new_stroke_width)
                        generate()
                except:
                    self.setSelectedAttribute("stroke_width", old_stroke_width)
            if self.mode == self.MODE_NORMAL and self.selected_type == self.SELECTED_POLYGON:
                old_sides = len(self.getSelectedAttribute("verts"))
                old_size = np.linalg.norm(self.getSelectedAttribute("verts")[0], 2)
                cur_rotation = (
                    np.arctan2(self.getSelectedAttribute("verts")[0][1], self.getSelectedAttribute("verts")[0][0])
                    - np.pi / 2
                )
                while cur_rotation < 0:
                    cur_rotation += np.pi
                cur_rotation *= 180 / np.pi
                try:
                    new_sides = int(self.sides_entry.text)
                    new_size = float(self.size_entry.text)
                    new_rot = float(self.rotation_entry.text)
                    assert new_sides > 2
                    if old_sides != new_sides or old_size != new_size or new_rot != cur_rotation:
                        self.setSelectedAttribute(
                            "verts",
                            [
                                [
                                    new_size * np.sin(i * 2 * np.pi / new_sides + new_rot * np.pi / 180),
                                    new_size * np.cos(i * 2 * np.pi / new_sides + new_rot * np.pi / 180),
                                ]
                                for i in range(new_sides)
                            ],
                        )
                    generate()
                except:
                    pass

                old_stroke_width = self.getSelectedAttribute("stroke_width")
                try:
                    new_stroke_width = float(self.stroke_entry.text)
                    if old_stroke_width != new_stroke_width:
                        self.setSelectedAttribute("stroke_width", new_stroke_width)
                        generate()
                except:
                    self.setSelectedAttribute("stroke_width", old_stroke_width)
            if self.mode == self.MODE_NORMAL and self.selected_type == self.SELECTED_DEVICE:
                old_rot = self.getSelectedAttribute("rotation", 0)
                try:
                    new_rot = float(self.rotation_entry.text)
                    if new_rot != old_rot:
                        self.setSelectedAttribute("rotation", new_rot)
                        generate()
                except:
                    pass
                self.setSelectedAttribute("port", self.port_entry.text)
            if self.mode == self.MODE_NORMAL:
                try:
                    self.grid_size = float(self.grid_size_entry.text)
                except:
                    pass
            if self.dragging:
                if not isinstance(self.selected_index, str):
                    new_pos = [
                        self.current_mpos[0] + self.offset_position[0],
                        self.current_mpos[1] + self.offset_position[1],
                    ]
                    # We need to relock position.
                    if self.lock_grid:
                        new_pos = [
                            ((new_pos[0] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                            ((new_pos[1] + self.grid_size / 2) // self.grid_size) * self.grid_size,
                        ]
                    if self.selected_index[0] == "Children":
                        old_pos = self.current_object["children"][self.selected_index[1]]["position"]
                        if old_pos[0] != new_pos[0] or old_pos[1] != new_pos[1]:
                            self.current_object["children"][self.selected_index[1]]["position"] = [
                                float(v) for v in new_pos
                            ]
                            generate()
                    elif self.selected_index[0] == "Devices":
                        old_pos = self.getSelectedAttribute("position", [0, 0])
                        if old_pos[0] != new_pos[0] or old_pos[1] != new_pos[1]:
                            self.setSelectedAttribute("position", [float(v) for v in new_pos])
                            generate()

        ScreenObjectManager.instance.applyToScreen(to_screen=self.bot_screen)
        ScreenObjectManager.instance.screen.blit(self.bot_screen, pygame.Rect(self.side_width - 5, 0, *self.surf_size))
        super().draw_ui(window_surface)

    def changeMode(self, value):
        # Remove/Add dialog components if necessary.
        self.mode = value

    def onPop(self):
        from ev3sim.simulation.loader import ScriptLoader
        from ev3sim.visual.manager import ScreenObjectManager
        from ev3sim.simulation.world import World

        ScreenObjectManager.instance.resetVisualElements()
        World.instance.resetWorld()
        ScriptLoader.instance.reset()
