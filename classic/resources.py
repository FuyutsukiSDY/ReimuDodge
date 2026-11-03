"""Version-locked resource supply, independent of collision bypass.

Replace only the resource loads in consumption handlers with 8. The game's
own decrement/store produces 7, while hit, respawn, bomb input/cooldown and
usage counters still run. Restore instructions on switch-off/exit.
"""
from invincibility import Trainer

def patch(rva,original,register):
    return (rva,bytes.fromhex(original),bytes.fromhex(register+'080000009090'))

PATCHES={
 'classic':{
  'lives':[patch(0x4aa48,'0fb605b53d3a00','b8')],
  'bombs':[patch(0x4a661,'0fb60d9d413a00','b9')],
 },
 'new':{
  'lives':[patch(0x6a576,'0fb605c3f74d00','b8')],
  'bombs':[patch(0x6a0ee,'0fb60d4cfc4d00','b9'),patch(0x6a173,'0fb60dc7fb4d00','b9')],
 },
}
COUNTS={'classic':{'lives':0x3ee804,'bombs':0x3ee805},'new':{'lives':0x549d40,'bombs':0x549d41}}

class ResourceTrainer(Trainer):
    def __init__(self,edition,kind):
        self.kind=kind
        super().__init__(edition,PATCHES[edition][kind])

    def set_enabled(self,enabled):
        previous=self.status()
        super().set_enabled(enabled)
        # Auto Bomb needs a visible stock to request its first release. Only
        # seed an empty stock; never overwrite negative menu/game-over values.
        try:
            if enabled and self.kind=='bombs':
                rva=COUNTS[self.edition][self.kind]
                if self.read(rva,1)==b'\x00':self.write(rva,b'\x01')
        except Exception:
            super().set_enabled(previous=='ON')
            raise
