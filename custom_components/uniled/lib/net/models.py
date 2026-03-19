"""UniLED Supported NET(work) Models."""
from typing import Final
from .device import UNILED_TRANSPORT_NET
from .banlanx_sp541e import SP541E

##
## Supported NET Models
##
UNILED_NET_MODELS: Final = [
    SP541E,
]