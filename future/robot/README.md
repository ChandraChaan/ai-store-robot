# Moving robot (parked for now)

`robot_control.py` and `arduino/robot_firmware.ino` drive a small cart that
fetches items from shelves (simulated by default, Arduino + L298N over USB
serial for real hardware). It worked in v1.0 and is kept here, not wired into
the shop flow, until the "bring items to the counter" feature returns (see
ROADMAP.md, v1.5).

To try the simulator:

```python
from future.robot.robot_control import SimulatedRobot
robot = SimulatedRobot({"A1": {"route": ["F 1200", "L 600", "F 400"]}}, on_event=print)
robot.fetch("A1", "Coca-Cola", wait=True)
```
