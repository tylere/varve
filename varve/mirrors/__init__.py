from varve.state.models import DestinationRecord
from .base import Mirror, MirrorSizeError
from .dryad import DryadMirror


def get_mirror(destination: DestinationRecord, credentials: dict) -> Mirror:
    match destination.type:
        case "dryad":
            return DryadMirror(credentials)
        case _:
            raise NotImplementedError(f"Mirror type '{destination.type}' not yet implemented")
