"""Non-overwriting publication for application-generated stills."""
import os
import shutil
from pathlib import Path


def publish_new_file(source, destination):
    source, destination = Path(source), Path(destination)
    created = None
    try:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            created = os.fstat(output_file.fileno())
            shutil.copyfileobj(input_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
    except Exception:
        if created is not None:
            try:
                current = destination.lstat()
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise
    return destination
