from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
                                               create_wheel_buttons
from selfdrive.car.chrysler.values import CAR, SteerLimitParams
from opendbc.can.packer import CANPacker
from common.dp_common import common_controller_ctrl

class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.apply_steer_last = 0
    self.ccframe = 0
    self.prev_frame = -1
    self.hud_count = 0
    self.car_fingerprint = CP.carFingerprint
    self.gone_fast_yet = False
    self.steer_rate_limited = False

    self.packer = CANPacker(dbc_name)

    # dp
    self.last_blinker_on = False
    self.blinker_end_frame = 0.

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, dragonconf):
    # this seems needed to avoid steering faults and to force the sync with the EPS counter
    frame = CS.lkas_counter
    if self.prev_frame == frame:
      return []

    # *** compute control surfaces ***
    # steer torque
    new_steer = actuators.steer * SteerLimitParams.STEER_MAX
    apply_steer = new_steer #, self.apply_steer_last, CS.out.steeringTorqueEps, SteerLimitParams
    self.steer_rate_limited = False
    moving_fast = True
    self.gone_fast_yet = True
    lkas_active = True

    if not lkas_active:
      apply_steer = 1 # Try, Stock = 0

    # dp
    blinker_on = CS.out.leftBlinker or CS.out.rightBlinker
    if not enabled:
      self.blinker_end_frame = 0
    if self.last_blinker_on and not blinker_on:
      self.blinker_end_frame = frame + dragonconf.dpSignalOffDelay
    apply_steer = common_controller_ctrl(enabled,
                                         dragonconf,
                                         blinker_on or frame < self.blinker_end_frame,
                                         apply_steer, CS.out.vEgo)
    self.last_blinker_on = blinker_on

    self.apply_steer_last = apply_steer

    can_sends = []

    #*** control msgs ***

    if pcm_cancel_cmd:
      # TODO: would be better to start from frame_2b3
      new_msg = create_wheel_buttons(self.packer, self.ccframe, cancel=True)
      can_sends.append(new_msg)

    # LKAS_HEARTBIT is forwarded by Panda so no need to send it here.
    # frame is 100Hz (0.01s period)
    if (self.ccframe % 25 == 0):  # 0.25s period
      if (CS.lkas_car_model != -1):
        new_msg = create_lkas_hud(
            self.packer, CS.out.gearShifter, lkas_active, hud_alert,
            self.hud_count, CS.lkas_car_model)
        can_sends.append(new_msg)
        self.hud_count += 1

    new_msg = create_lkas_command(self.packer, int(apply_steer), self.gone_fast_yet, frame)
    can_sends.append(new_msg)

    self.ccframe += 1
    self.prev_frame = frame

    return can_sends
