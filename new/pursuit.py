from pursuit_p12 import Pursuit as Previous
from diagonal_escape import Detour
class Pursuit(Previous):
    def reset(self):
        super().reset();self.detour=Detour()
    def choose(self,s,previous,baseline,enabled):
        result,info=super().choose(s,previous,baseline,enabled)
        if not enabled:self.detour.reset();return result,info
        if info.get('active') and self.detour.target is None:return result,info
        candidate=self.detour.choose(s,previous,baseline)
        return candidate if candidate is not None else (result,info)
