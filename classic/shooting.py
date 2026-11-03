class Shooting:
    """Refresh key-down edges without tying the release to exact modulo frames."""
    def __init__(self):self.reset()
    def reset(self):
        self.pressed_at=None;self.release_until=-1
    def wanted(self,frame,enabled):
        if not enabled:self.reset();return False
        if frame<self.release_until:return False
        if self.pressed_at is None or frame<self.pressed_at:
            self.pressed_at=frame
        if frame-self.pressed_at>=45:
            self.release_until=frame+2;self.pressed_at=None
            return False
        return True
