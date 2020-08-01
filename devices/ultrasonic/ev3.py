import numpy as np
from objects.base import objectFactory
from devices.base import Device, IDeviceInteractor
from objects.utils import local_space_to_world_space
from devices.ultrasonic.base import UltrasonicSensorMixin
from simulation.loader import ScriptLoader
from visual.manager import ScreenObjectManager

class UltrasonicInteractor(IDeviceInteractor):

    UPDATE_PER_SECOND = 5
    DRAW_RAYCAST = False

    def startUp(self):
        super().startUp()
        if self.DRAW_RAYCAST:
            key = self.getPrefix() + '_US_RAYCAST'
            ScreenObjectManager.instance.registerVisual(self.device_class.raycast.visual, key)


    def tick(self, tick):
        if tick % (ScriptLoader.instance.GAME_TICK_RATE // self.UPDATE_PER_SECOND) == 0:
            self.device_class._calc()
            ScriptLoader.instance.object_map[self.getPrefix() + 'light_up'].visual.fill = (
                min(max((self.device_class.MAX_RAYCAST - self.device_class.distance_centimeters) * 255 / self.device_class.MAX_RAYCAST, 0), 255),
                0,
                0,
            )
        return False

class UltrasonicSensor(Device, UltrasonicSensorMixin):
    """
    Ultrasonic sensor, reads the distance between the sensor and the closest physics object (directly in front of the sensor).

    This measurement is done from the light on the sensor, so a reading of 5cm means the closest object is 5cm away from the light.
    """

    name = 'Ultrasonic'

    def __init__(self, parent, relativePos, relativeRot, **kwargs):
        super().__init__(parent, relativePos, relativeRot, **kwargs)
        self._SetIgnoredObjects([parent])
        self._InitialiseRaycast()

    def _calc(self):
        self.saved = self._DistanceFromSensor(ScriptLoader.instance.object_map[self._interactor.getPrefix() + 'light_up'].position, self.parent.rotation + self.relativeRot)
    
    @property
    def distance_centimeters(self):
        """
        Get the distance between the ultrasonic sensor and the object, in centimeters.
        """
        return self.saved
    
    @property
    def distance_inches(self):
        """
        Get the distance between the ultrasonic sensor and the object, in inches.
        """
        return self.distance_centimeters * 0.3937008