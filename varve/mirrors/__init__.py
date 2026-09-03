from varve.state.models import DestinationRecord
from .base import Mirror, MirrorSizeError
from .dryad import DryadMirror
from .s3 import S3Mirror
from .source_coop import SourceCoopMirror


def get_mirror(destination: DestinationRecord, credentials: dict) -> Mirror:
    match destination.type:
        case "dryad":
            return DryadMirror(credentials)
        case "s3":
            return S3Mirror(credentials)
        case "source_coop":
            return SourceCoopMirror(credentials)
        case _:
            raise NotImplementedError(f"Mirror type '{destination.type}' not yet implemented")
